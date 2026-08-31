from __future__ import annotations

import shutil
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.project_governance.contracts import ProjectContextReadPort
from synapse.skills.contracts import SkillRecordStore
from synapse.skills.errors import (
    SkillAssignmentInvalid,
    SkillConflict,
    SkillContextBudgetExceeded,
    SkillDependencyCycle,
    SkillDependencyMissing,
    SkillIdConflict,
    SkillInUse,
    SkillLeaseInvalid,
    SkillNotFound,
    SkillPackageInvalid,
    SkillResourceNotFound,
    SkillScriptNotAllowed,
    SkillUninstallBlocked,
    SkillVersionNotFound,
)
from synapse.skills.models import (
    LOAD_LEVELS,
    SCOPE_PRECEDENCE,
    SkillAssignment,
    SkillDescriptor,
    SkillLease,
    SkillLoadRequest,
    SkillLoadResult,
    SkillPackage,
    SkillResolutionRequest,
    SkillResolutionResult,
    SkillScope,
    now_iso,
)
from synapse.skills.package import inspect_package, version_matches


class SkillRegistry:
    def __init__(self) -> None:
        self._packages: dict[str, dict[str, SkillPackage]] = {}

    def register(self, package: SkillPackage) -> None:
        versions = self._packages.setdefault(package.manifest.skill_id, {})
        existing = versions.get(package.manifest.version)
        if existing and existing.checksum != package.checksum:
            raise SkillIdConflict("Skill ID/version already has different content")
        versions[package.manifest.version] = package

    def get(self, skill_id: str, version: str | None = None) -> SkillPackage:
        versions = self._packages.get(skill_id)
        if not versions:
            raise SkillNotFound("Skill was not found", details={"skill_id": skill_id})
        if version is None:
            active = [p for p in versions.values() if p.manifest.status == "active"]
            if len(active) != 1:
                raise SkillVersionNotFound("An explicit version is required")
            return active[0]
        try:
            return versions[version]
        except KeyError as exc:
            raise SkillVersionNotFound("Skill version was not found") from exc

    def resolve_version(self, skill_id: str, constraint: str = "*") -> SkillPackage:
        versions = self._packages.get(skill_id, {})
        matches = [p for p in versions.values() if version_matches(p.manifest.version, constraint)]
        matches = [p for p in matches if p.manifest.status not in {"disabled", "draft"}]
        if not matches:
            raise SkillVersionNotFound("No compatible skill version was found")
        return sorted(
            matches,
            key=lambda p: tuple(int(x) for x in p.manifest.version.split("-", 1)[0].split(".")),
            reverse=True,
        )[0]

    def packages(self) -> tuple[SkillPackage, ...]:
        return tuple(p for versions in self._packages.values() for p in versions.values())

    def remove(self, skill_id: str, version: str) -> None:
        package = self.get(skill_id, version)
        del self._packages[skill_id][package.manifest.version]
        if not self._packages[skill_id]:
            del self._packages[skill_id]


class SkillDiscovery:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def search(self, query: str = "", **filters: Any) -> tuple[SkillDescriptor, ...]:
        generic = {"help", "work", "task", "use", "review", "skill"}
        terms = {
            term.lower() for term in query.split() if len(term) > 2 and term.lower() not in generic
        }
        found: list[SkillDescriptor] = []
        for package in self.registry.packages():
            manifest = package.manifest
            if filters.get("status") and manifest.status != filters["status"]:
                continue
            if (
                filters.get("agent_kind")
                and filters["agent_kind"] not in manifest.supported_agent_kinds
            ):
                continue
            haystack = " ".join(
                (
                    manifest.name,
                    manifest.summary,
                    manifest.description,
                    *manifest.activation.get("keywords", []),
                )
            ).lower()
            matches = sum(1 for term in terms if term in haystack)
            if terms and not matches:
                continue
            found.append(_descriptor(package, matches / max(len(terms), 1)))
        return tuple(sorted(found, key=lambda item: (-item.relevance, item.skill_id, item.version)))


class SkillLoader:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def load(self, request: SkillLoadRequest) -> SkillLoadResult:
        if request.level not in LOAD_LEVELS:
            raise SkillPackageInvalid("Skill load level is invalid")
        package = self.registry.get(request.skill_id, request.version)
        instructions = ""
        refs: dict[str, str] = {}
        resources: dict[str, str] = {}
        loaded: list[str] = ["manifest"]
        omissions: list[str] = []
        level = LOAD_LEVELS.index(request.level)
        if level >= 1:
            instructions = package.instructions_path.read_text(encoding="utf-8")
            loaded.append("SKILL.md")
        if level >= 2:
            names = request.references or package.manifest.references
            refs = self._read(package, names, package.manifest.references)
            loaded.extend(f"reference:{name}" for name in refs)
        elif package.manifest.references:
            omissions.append("references")
        if level >= 3:
            names = request.resources or package.manifest.resources
            resources = self._read(package, names, package.manifest.resources)
            loaded.extend(f"resource:{name}" for name in resources)
        elif package.manifest.resources:
            omissions.append("resources")
        scripts = package.manifest.scripts if level >= 4 else ()
        if package.manifest.scripts and level < 4:
            omissions.append("scripts_metadata")
        size = len(instructions.encode()) + sum(
            len(v.encode()) for v in (*refs.values(), *resources.values())
        )
        tokens = (size + 3) // 4
        if tokens > request.context_budget:
            raise SkillContextBudgetExceeded(
                "Skill context budget exceeded",
                details={"estimated": tokens, "budget": request.context_budget},
            )
        return SkillLoadResult(
            request.skill_id,
            request.version,
            request.level,
            instructions,
            refs,
            resources,
            scripts,
            tuple(loaded),
            tuple(omissions),
            size,
            tokens,
            package.checksum,
            {"package_root": package.root.name, "loaded_at": now_iso()},
        )

    @staticmethod
    def _read(
        package: SkillPackage, names: tuple[str, ...], allowed: tuple[str, ...]
    ) -> dict[str, str]:
        result = {}
        for name in names:
            if name not in allowed:
                raise SkillResourceNotFound("Skill resource was not declared")
            path = (package.root / name).resolve(strict=False)
            try:
                path.relative_to(package.root)
            except ValueError as exc:
                raise SkillResourceNotFound("Skill resource path is unsafe") from exc
            result[name] = path.read_text(encoding="utf-8")
        return result


class SkillValidationRuntime:
    MODES = {
        "validate_package",
        "validate_installation",
        "validate_resolution",
        "validate_assignment",
        "validate_lease",
    }

    def validate_package(self, path: Path) -> SkillPackage:
        return inspect_package(path)


class SkillResourceRuntime:
    def __init__(self, loader: SkillLoader) -> None:
        self.loader = loader

    def load(self, request: SkillLoadRequest) -> SkillLoadResult:
        return self.loader.load(request)


class SkillVersionStore:
    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def versions(self, skill_id: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                package.manifest.version
                for package in self.registry.packages()
                if package.manifest.skill_id == skill_id
            )
        )

    def resolve(self, skill_id: str, constraint: str) -> SkillPackage:
        return self.registry.resolve_version(skill_id, constraint)


class SkillResolver:
    def __init__(self, registry: SkillRegistry, discovery: SkillDiscovery) -> None:
        self.registry, self.discovery = registry, discovery

    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult:
        selected: dict[str, SkillPackage] = {}
        unavailable: list[str] = []
        missing_tools: set[str] = set()
        missing_capabilities: set[str] = set()
        reasons: list[str] = []
        candidates = list(request.explicit_skill_ids)
        if not candidates and len(request.objective.strip()) >= 4:
            candidates = [
                item.skill_id
                for item in self.discovery.search(request.objective, agent_kind=request.agent_kind)
                if item.relevance > 0
            ]
        for skill_id in candidates:
            try:
                package = self.registry.resolve_version(skill_id)
            except (SkillNotFound, SkillVersionNotFound):
                unavailable.append(skill_id)
                continue
            if request.agent_kind not in package.manifest.supported_agent_kinds:
                unavailable.append(skill_id)
                continue
            if package.manifest.requires_project and not request.project_id:
                unavailable.append(skill_id)
                continue
            if (
                request.change_class in package.manifest.requires_rfc_for_change_classes
                and not request.rfc_id
            ):
                unavailable.append(skill_id)
                continue
            self._dependencies(package, selected, set())
            selected[skill_id] = package
            reasons.append(
                f"{skill_id}:{'explicit' if skill_id in request.explicit_skill_ids else 'metadata_match'}"
            )
        conflicts: list[dict[str, Any]] = []
        for package in selected.values():
            for conflict in package.manifest.conflicts:
                if conflict.skill_id in selected and conflict.severity == "critical":
                    conflicts.append(asdict(conflict))
            missing_tools.update(set(package.manifest.tools) - set(request.available_tools))
            missing_capabilities.update(
                set(package.manifest.capabilities) - set(request.capabilities)
            )
        if conflicts:
            raise SkillConflict("Selected skills conflict", details={"conflicts": conflicts})
        rejected = tuple(
            {"skill_id": p.manifest.skill_id, "reason": "requirements_unavailable"}
            for p in selected.values()
            if set(p.manifest.tools) - set(request.available_tools)
            or set(p.manifest.capabilities) - set(request.capabilities)
            or set(p.manifest.providers) - set(request.providers)
        )
        rejected_ids = {item["skill_id"] for item in rejected}
        ordered = self._topological(
            tuple(p for key, p in selected.items() if key not in rejected_ids)
        )
        descriptors = tuple(_descriptor(p) for p in ordered)
        cost = sum(max(1, p.instructions_path.stat().st_size // 4) for p in ordered)
        if cost > request.context_budget:
            raise SkillContextBudgetExceeded(
                "Resolved skill context exceeds budget", details={"estimated": cost}
            )
        return SkillResolutionResult(
            descriptors,
            rejected,
            tuple(unavailable),
            (),
            (),
            tuple(sorted(missing_tools)),
            tuple(sorted(missing_capabilities)),
            tuple(reasons),
            tuple(item.skill_id for item in descriptors),
            cost,
            ("no_match",) if not descriptors and not unavailable else (),
            {
                "correlation_id": request.correlation_id,
                "resolved_at": now_iso(),
                "selection": "explicit" if request.explicit_skill_ids else "automatic",
            },
        )

    def _dependencies(
        self, package: SkillPackage, selected: dict[str, SkillPackage], visiting: set[str]
    ) -> None:
        skill_id = package.manifest.skill_id
        if skill_id in visiting:
            raise SkillDependencyCycle("Skill dependency cycle detected")
        visiting.add(skill_id)
        for dependency in package.manifest.dependencies:
            try:
                child = self.registry.resolve_version(
                    dependency.skill_id, dependency.version_constraint
                )
            except SkillVersionNotFound as exc:
                if dependency.optional:
                    continue
                raise SkillDependencyMissing(
                    "Required skill dependency is missing",
                    details={"skill_id": dependency.skill_id},
                ) from exc
            self._dependencies(child, selected, visiting)
            selected[child.manifest.skill_id] = child
        visiting.remove(skill_id)

    @staticmethod
    def _topological(packages: tuple[SkillPackage, ...]) -> tuple[SkillPackage, ...]:
        by_id = {p.manifest.skill_id: p for p in packages}
        result = []
        seen = set()

        def visit(p: SkillPackage) -> None:
            if p.manifest.skill_id in seen:
                return
            for dep in p.manifest.dependencies:
                if dep.skill_id in by_id:
                    visit(by_id[dep.skill_id])
            seen.add(p.manifest.skill_id)
            result.append(p)

        for p in sorted(packages, key=lambda x: x.manifest.skill_id):
            visit(p)
        return tuple(result)


class SkillsRuntime:
    def __init__(
        self,
        data_dir: Any,
        events: Any,
        *,
        assignments: SkillRecordStore,
        leases: SkillRecordStore,
        installations: SkillRecordStore,
        script_execution: Any = None,
        project_context: ProjectContextReadPort | None = None,
    ) -> None:
        self.data_dir, self.events, self.script_execution = data_dir, events, script_execution
        self.root = data_dir.resolve("skills")
        self.packages_root = self.root / "packages"
        self.packages_root.mkdir(parents=True, exist_ok=True)
        self.registry = SkillRegistry()
        self.discovery = SkillDiscovery(self.registry)
        self.resolver = SkillResolver(self.registry, self.discovery)
        self.loader = SkillLoader(self.registry)
        self.validation = SkillValidationRuntime()
        self.resources = SkillResourceRuntime(self.loader)
        self.version_store = SkillVersionStore(self.registry)
        self.assignments = assignments
        self.leases = leases
        self.installations = installations
        self.invalid_packages: list[dict[str, Any]] = []
        self.project_context = project_context
        self._load_installed()

    def inspect(self, path: str | Path) -> SkillPackage:
        return self.validation.validate_package(self._safe_source(path))

    def validate(self, path: str | Path) -> dict[str, Any]:
        package = self.inspect(path)
        self._emit("skill.validated", package, {"checksum": package.checksum})
        return {
            "valid": True,
            "skill_id": package.manifest.skill_id,
            "version": package.manifest.version,
            "checksum": package.checksum,
        }

    def install(self, path: str | Path, *, actor_id: str = "system") -> SkillPackage:
        package = self.inspect(path)
        target = self.packages_root / package.manifest.skill_id / package.manifest.version
        if target.exists():
            raise SkillIdConflict("Skill version is already installed")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(package.root, target)
        installed = inspect_package(target, installed=True)
        self.registry.register(installed)
        payload = {
            "schema_version": 1,
            "revision": 1,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "skill_id": installed.manifest.skill_id,
            "version": installed.manifest.version,
            "checksum": installed.checksum,
            "status": installed.manifest.status,
            "source": "local_package",
        }
        self.installations.put(
            f"{installed.manifest.skill_id}--{installed.manifest.version}",
            payload,
            create_only=True,
        )
        self._emit("skill.installed", installed, {"actor_id": actor_id})
        return installed

    def list(self, query: str = "", **filters: Any) -> tuple[SkillDescriptor, ...]:
        return self.discovery.search(query, **filters)

    def get(self, skill_id: str, version: str | None = None) -> SkillPackage:
        return self.registry.get(skill_id, version)

    def versions(self, skill_id: str) -> tuple[str, ...]:
        return self.version_store.versions(skill_id)

    def resolve(self, request: SkillResolutionRequest) -> SkillResolutionResult:
        if request.project_id and self.project_context:
            context = self.project_context.read_project_context(
                request.project_id, budget=min(request.context_budget, 2000)
            )
            request = replace(
                request,
                policy_context={
                    **request.policy_context,
                    "project_revision": context.project_revision,
                    "project_classification": context.classification,
                    "active_rfcs": context.active_rfcs,
                },
            )
        result = self.resolver.resolve(request)
        self.events.emit(
            "skill.resolved",
            request.agent_id or "system",
            {
                "selected": list(result.ordering),
                "reason": list(result.reasons),
                "correlation_id": request.correlation_id,
            },
        )
        return result

    def load(self, request: SkillLoadRequest) -> SkillLoadResult:
        result = self.loader.load(request)
        self.events.emit(
            "skill.loaded",
            "system",
            {
                "skill_id": result.skill_id,
                "version": result.version,
                "level": result.level,
                "tokens_estimated": result.token_estimate,
            },
        )
        return result

    def preview_script(
        self,
        skill_id: str,
        version: str,
        script_id: str,
        inputs: dict[str, Any],
        *,
        actor_id: str,
    ) -> Any:
        descriptor = self._script(skill_id, version, script_id)
        result = self.script_execution.preview(descriptor, inputs, actor_id=actor_id)
        self.events.emit(
            "skill.script_previewed",
            actor_id,
            {"skill_id": skill_id, "version": version, "script_id": script_id},
        )
        return result

    def execute_script(
        self,
        skill_id: str,
        version: str,
        script_id: str,
        inputs: dict[str, Any],
        *,
        actor_id: str,
        approval_id: str | None = None,
    ) -> Any:
        descriptor = self._script(skill_id, version, script_id)
        result = self.script_execution.execute(
            descriptor,
            inputs,
            actor_id=actor_id,
            approval_id=approval_id,
        )
        self.events.emit(
            "skill.script_executed",
            actor_id,
            {"skill_id": skill_id, "version": version, "script_id": script_id},
        )
        return result

    def _script(self, skill_id: str, version: str, script_id: str) -> Any:
        if self.script_execution is None:
            raise SkillScriptNotAllowed("Skill script execution boundary is unavailable")
        package = self.registry.get(skill_id, version)
        for descriptor in package.manifest.scripts:
            if descriptor.script_id == script_id:
                return descriptor
        raise SkillScriptNotAllowed("Skill script is not declared")

    def assign(self, assignment: SkillAssignment) -> SkillAssignment:
        self.registry.resolve_version(assignment.skill_id, assignment.version_constraint)
        if assignment.scope not in {
            SkillScope.AGENT,
            SkillScope.PROJECT,
            SkillScope.WORKSPACE,
            SkillScope.USER,
            SkillScope.SYSTEM,
        }:
            raise SkillAssignmentInvalid("Persistent assignment scope is invalid")
        self.assignments.put(
            assignment.assignment_id, _record(asdict(assignment)), create_only=True
        )
        self.events.emit(
            "skill.assigned",
            assignment.assigned_by,
            {
                "skill_id": assignment.skill_id,
                "agent_id": assignment.agent_id,
                "scope": assignment.scope.value,
            },
        )
        return assignment

    def unassign(self, assignment_id: str) -> None:
        self.assignments.delete(assignment_id)
        self.events.emit("skill.unassigned", "system", {"assignment_id": assignment_id})

    def list_assignments(self, agent_id: str | None = None) -> tuple[dict[str, Any], ...]:
        filters = {"agent_id": agent_id} if agent_id else {}
        return self.assignments.list(filters)

    def assignment_summaries(self, agent_id: str) -> tuple[dict[str, Any], ...]:
        return tuple(
            {
                "assignment_id": item["assignment_id"],
                "skill_id": item["skill_id"],
                "version_constraint": item["version_constraint"],
                "scope": str(item["scope"]),
                "enabled": bool(item.get("enabled", True)),
            }
            for item in self.list_assignments(agent_id)
        )

    def load_assigned(
        self,
        agent_id: str,
        *,
        project_id: str | None = None,
        context_budget: int = 8000,
    ) -> tuple[SkillLoadResult, ...]:
        candidates = [
            item
            for item in self.list_assignments(agent_id)
            if item.get("enabled", True)
            and (
                str(item.get("scope")) != SkillScope.PROJECT.value
                or item.get("metadata", {}).get("project_id") == project_id
            )
        ]
        rank = {scope.value: index for index, scope in enumerate(SCOPE_PRECEDENCE)}
        selected: dict[str, dict[str, Any]] = {}
        for item in sorted(
            candidates,
            key=lambda value: (
                rank.get(str(value.get("scope")), -1),
                int(value.get("priority", 0)),
            ),
            reverse=True,
        ):
            selected.setdefault(str(item["skill_id"]), item)
        results: list[SkillLoadResult] = []
        remaining = context_budget
        for skill_id, item in selected.items():
            package = self.registry.resolve_version(
                skill_id, str(item.get("version_constraint", "*"))
            )
            loaded = self.load(
                SkillLoadRequest(
                    skill_id,
                    package.manifest.version,
                    "instructions",
                    context_budget=remaining,
                )
            )
            remaining -= loaded.token_estimate
            results.append(loaded)
        return tuple(results)

    def grant_lease(self, lease: SkillLease) -> SkillLease:
        self.registry.get(lease.skill_id, lease.resolved_version)
        if not lease.ephemeral_agent_id or datetime.fromisoformat(lease.expires_at) <= datetime.now(
            UTC
        ):
            raise SkillLeaseInvalid("Skill lease must target an ephemeral agent and future expiry")
        self.leases.put(lease.lease_id, _record(asdict(lease)), create_only=True)
        self.events.emit(
            "skill.lease_granted",
            lease.ephemeral_agent_id,
            {
                "skill_id": lease.skill_id,
                "lease_id": lease.lease_id,
                "correlation_id": lease.correlation_id,
            },
        )
        return lease

    def grant_for_ephemeral(
        self,
        ephemeral_agent_id: str,
        skill_ids: tuple[str, ...],
        *,
        mission_id: str,
        task_id: str | None,
        expires_at: str,
        context_budget: int,
        allowed_tools: tuple[str, ...],
        correlation_id: str | None,
    ) -> tuple[dict[str, Any], ...]:
        granted: list[dict[str, Any]] = []
        for skill_id in skill_ids:
            try:
                package = self.registry.resolve_version(skill_id)
            except SkillVersionNotFound:
                self.events.emit(
                    "skill.gap",
                    ephemeral_agent_id,
                    {"skill_id": skill_id, "mission_id": mission_id, "task_id": task_id},
                )
                continue
            manifest = package.manifest
            lease = SkillLease(
                ephemeral_agent_id=ephemeral_agent_id,
                skill_id=skill_id,
                resolved_version=manifest.version,
                mission_id=mission_id,
                task_id=task_id,
                expires_at=expires_at,
                context_budget=context_budget,
                allowed_resources=manifest.resources,
                allowed_scripts=tuple(script.script_id for script in manifest.scripts),
                tool_scope=tuple(sorted(set(manifest.tools) & set(allowed_tools))),
                correlation_id=correlation_id,
            )
            granted.append(asdict(self.grant_lease(lease)))
        return tuple(granted)

    def list_leases(self, ephemeral_agent_id: str | None = None) -> tuple[dict[str, Any], ...]:
        filters = {"ephemeral_agent_id": ephemeral_agent_id} if ephemeral_agent_id else {}
        return self.leases.list(filters)

    def cleanup_leases(self, ephemeral_agent_id: str, *, audit_only: bool = False) -> int:
        leases = self.list_leases(ephemeral_agent_id)
        count = 0
        for lease in leases:
            if not audit_only:
                self.leases.delete(str(lease["lease_id"]))
                count += 1
                self.events.emit(
                    "skill.lease_expired",
                    ephemeral_agent_id,
                    {"lease_id": lease["lease_id"], "skill_id": lease["skill_id"]},
                )
        return count

    def set_status(self, skill_id: str, version: str, status: str) -> SkillPackage:
        if status not in {"active", "disabled", "deprecated"}:
            raise SkillPackageInvalid("Unsupported status transition")
        package = self.registry.get(skill_id, version)
        if status == "active":
            for other in self.registry.packages():
                if other.manifest.skill_id == skill_id and other.manifest.version != version:
                    self._persist_status(other, "disabled")
        updated = self._persist_status(package, status)
        self.events.emit(f"skill.{status}", "system", {"skill_id": skill_id, "version": version})
        return updated

    def _persist_status(self, package: SkillPackage, status: str) -> SkillPackage:
        path = package.root / "manifest.yaml"
        raw = load_structured_file(path)
        raw["status"] = status
        dump_structured_file(path, raw)
        self.registry.remove(package.manifest.skill_id, package.manifest.version)
        updated = inspect_package(package.root, installed=package.installed)
        self.registry.register(updated)
        return updated

    def uninstall(self, skill_id: str, version: str) -> None:
        if any(
            x.get("skill_id") == skill_id for x in (*self.list_assignments(), *self.list_leases())
        ):
            raise SkillInUse("Skill has assignments or leases")
        for p in self.registry.packages():
            if any(d.skill_id == skill_id and not d.optional for d in p.manifest.dependencies):
                raise SkillUninstallBlocked("Another skill depends on this skill")
        package = self.registry.get(skill_id, version)
        shutil.rmtree(package.root)
        self.registry.remove(skill_id, version)
        self.installations.delete(f"{skill_id}--{version}")
        self.events.emit("skill.uninstalled", "system", {"skill_id": skill_id, "version": version})

    def status(self) -> dict[str, Any]:
        packages = self.registry.packages()
        return {
            "status": "ready",
            "registry": True,
            "packages": len(packages),
            "active_versions": sum(p.manifest.status == "active" for p in packages),
            "invalid_packages": len(self.invalid_packages),
            "assignments": len(self.list_assignments()),
            "leases": len(self.list_leases()),
            "storage": True,
            "loader": True,
            "script_boundary": self.script_execution is not None,
        }

    def _load_installed(self) -> None:
        for path in sorted(self.packages_root.glob("*/*")):
            if not path.is_dir():
                continue
            try:
                self.registry.register(inspect_package(path, installed=True))
            except Exception as exc:
                self.invalid_packages.append(
                    {"path": path.name, "error_code": getattr(exc, "code", "skill_package_invalid")}
                )

    def _safe_source(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            allowed = self.data_dir.root.resolve(strict=False)
            resolved = path.resolve(strict=False)
            try:
                resolved.relative_to(allowed)
            except ValueError as exc:
                raise SkillPackageInvalid("Package source must be inside DATA_DIR") from exc
            return resolved
        return self.data_dir.resolve(str(path))

    def _emit(self, event_type: str, package: SkillPackage, payload: dict[str, Any]) -> None:
        self.events.emit(
            event_type,
            "system",
            {"skill_id": package.manifest.skill_id, "version": package.manifest.version, **payload},
        )


def _descriptor(package: SkillPackage, relevance: float = 0.0) -> SkillDescriptor:
    m = package.manifest
    activation = tuple(str(x) for x in m.activation.get("keywords", []))
    tags = tuple(str(x) for x in m.metadata.get("tags", []))
    return SkillDescriptor(
        m.skill_id,
        m.version,
        m.name,
        m.summary,
        tuple(x.value for x in m.scopes),
        tags,
        m.supported_agent_kinds,
        activation,
        {"tools": m.tools, "capabilities": m.capabilities, "providers": m.providers},
        m.status,
        relevance,
    )


def _record(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "created_at": payload.get("assigned_at") or payload.get("granted_at") or now_iso(),
        "updated_at": now_iso(),
        **payload,
    }
