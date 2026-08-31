from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from synapse.core.serialization import load_structured_file
from synapse.skills.errors import SkillManifestInvalid, SkillPackageInvalid
from synapse.skills.models import (
    SKILL_STATUSES,
    SkillConflict,
    SkillDependency,
    SkillManifest,
    SkillPackage,
    SkillScope,
    SkillScriptDescriptor,
)

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")
_VERSION = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_MAX_FILE_BYTES = 1_000_000


def inspect_package(root: Path, *, installed: bool = False) -> SkillPackage:
    root = root.resolve(strict=False)
    if not root.is_dir():
        raise SkillPackageInvalid("Skill package directory does not exist")
    manifest_path = root / "manifest.yaml"
    instructions = root / "SKILL.md"
    if not manifest_path.is_file() or not instructions.is_file():
        raise SkillPackageInvalid("Skill package requires manifest.yaml and SKILL.md")
    try:
        raw = load_structured_file(manifest_path)
    except Exception as exc:
        raise SkillManifestInvalid("Skill manifest could not be parsed") from exc
    manifest = manifest_from_mapping(raw)
    validate_package_paths(root, manifest)
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        _safe_child(root, path)
        if path.stat().st_size > _MAX_FILE_BYTES:
            raise SkillPackageInvalid("Skill package file exceeds size limit")
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return SkillPackage(manifest, root, instructions, digest.hexdigest(), installed)


def manifest_from_mapping(raw: dict[str, Any]) -> SkillManifest:
    required = ("skill_id", "name", "version", "description", "summary", "authorship")
    missing = [field for field in required if not raw.get(field)]
    if missing:
        raise SkillManifestInvalid("Skill manifest has missing fields", details={"fields": missing})
    skill_id = str(raw["skill_id"])
    version = str(raw["version"])
    status = str(raw.get("status", "draft"))
    if not _ID.fullmatch(skill_id):
        raise SkillManifestInvalid("Skill ID is invalid", details={"skill_id": skill_id})
    if not _VERSION.fullmatch(version):
        raise SkillManifestInvalid("Skill version must be explicit SemVer")
    if status not in SKILL_STATUSES:
        raise SkillManifestInvalid("Skill status is invalid", details={"status": status})
    try:
        scopes = tuple(SkillScope(str(item)) for item in raw.get("scopes", ["system"]))
    except ValueError as exc:
        raise SkillManifestInvalid("Skill scope is invalid") from exc
    dependencies = tuple(
        SkillDependency(
            skill_id=str(item.get("skill_id", "")),
            version_constraint=str(item.get("version_constraint", "*")),
            optional=bool(item.get("optional", False)),
            reason=str(item.get("reason", "")),
        )
        for item in _mapping_list(raw.get("dependencies", []), "dependencies")
    )
    conflicts = tuple(
        SkillConflict(
            skill_id=str(item.get("skill_id", "")),
            version_constraint=(
                str(item["version_constraint"]) if item.get("version_constraint") else None
            ),
            reason=str(item.get("reason", "")),
            severity=str(item.get("severity", "critical")),
        )
        for item in _mapping_list(raw.get("conflicts", []), "conflicts")
    )
    scripts = tuple(_script(item) for item in _mapping_list(raw.get("scripts", []), "scripts"))
    return SkillManifest(
        skill_id=skill_id,
        name=str(raw["name"]),
        version=version,
        description=str(raw["description"]),
        summary=str(raw["summary"]),
        authorship=tuple(str(x) for x in _list(raw["authorship"])),
        status=status,
        scopes=scopes,
        supported_agent_kinds=tuple(
            str(x)
            for x in _list(raw.get("supported_agent_kinds", ["primary", "persistent", "ephemeral"]))
        ),
        activation=dict(raw.get("activation") or {}),
        requirements=dict(raw.get("requirements") or {}),
        dependencies=dependencies,
        conflicts=conflicts,
        tools=tuple(str(x) for x in _list(raw.get("tools", []))),
        capabilities=tuple(str(x) for x in _list(raw.get("capabilities", []))),
        providers=tuple(str(x) for x in _list(raw.get("providers", []))),
        resources=tuple(str(x) for x in _list(raw.get("resources", []))),
        references=tuple(str(x) for x in _list(raw.get("references", []))),
        examples=tuple(str(x) for x in _list(raw.get("examples", []))),
        scripts=scripts,
        context_policy=dict(raw.get("context_policy") or {}),
        permissions=tuple(str(x) for x in _list(raw.get("permissions", []))),
        output_contract=(
            dict(raw["output_contract"]) if isinstance(raw.get("output_contract"), dict) else None
        ),
        compatibility=dict(raw.get("compatibility") or {}),
        metadata=_redact_metadata(dict(raw.get("metadata") or {})),
        requires_project=bool(raw.get("requires_project", False)),
        requires_rfc_for_change_classes=tuple(
            str(x) for x in _list(raw.get("requires_rfc_for_change_classes", []))
        ),
        allowed_rfc_statuses=tuple(
            str(x) for x in _list(raw.get("allowed_rfc_statuses", ["approved", "implementing"]))
        ),
        consumes_rfc_sections=tuple(str(x) for x in _list(raw.get("consumes_rfc_sections", []))),
        produces_evidence_types=tuple(
            str(x) for x in _list(raw.get("produces_evidence_types", []))
        ),
        required_quality_gates=tuple(str(x) for x in _list(raw.get("required_quality_gates", []))),
        allowed_classifications=tuple(
            str(x) for x in _list(raw.get("allowed_classifications", []))
        ),
        external_processing_allowed=bool(raw.get("external_processing_allowed", False)),
        private_only=bool(raw.get("private_only", False)),
        data_categories_consumed=tuple(
            str(x) for x in _list(raw.get("data_categories_consumed", []))
        ),
        provider_trust_requirements=tuple(
            str(x) for x in _list(raw.get("provider_trust_requirements", []))
        ),
        telemetry_retention=str(raw.get("telemetry_retention", "local-only")),
        output_classification_rule=str(
            raw.get("output_classification_rule", "most-restrictive-input")
        ),
    )


def validate_package_paths(root: Path, manifest: SkillManifest) -> None:
    for relative in (*manifest.resources, *manifest.references, *manifest.examples):
        _validate_relative(root, relative)
    for script in manifest.scripts:
        path = _validate_relative(root, script.entrypoint)
        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum != script.checksum:
            raise SkillPackageInvalid(
                "Skill script checksum mismatch", details={"script_id": script.script_id}
            )


def version_matches(version: str, constraint: str) -> bool:
    if constraint in {"", "*"}:
        return True
    if constraint.startswith("^"):
        base = constraint[1:]
        if not _VERSION.fullmatch(base):
            return False
        current, wanted = _version_tuple(version), _version_tuple(base)
        return current >= wanted and current[0] == wanted[0]
    return version == constraint


def _script(raw: dict[str, Any]) -> SkillScriptDescriptor:
    required = ("script_id", "runtime", "entrypoint", "checksum")
    if any(not raw.get(key) for key in required):
        raise SkillManifestInvalid("Skill script descriptor is incomplete")
    return SkillScriptDescriptor(
        script_id=str(raw["script_id"]),
        runtime=str(raw["runtime"]),
        entrypoint=str(raw["entrypoint"]),
        checksum=str(raw["checksum"]),
        purpose=str(raw.get("purpose", "")),
        inputs=dict(raw.get("inputs") or {}),
        outputs=dict(raw.get("outputs") or {}),
        permissions=tuple(str(x) for x in _list(raw.get("permissions", []))),
        required_tools=tuple(str(x) for x in _list(raw.get("required_tools", []))),
        timeout=float(raw.get("timeout", 30)),
        deterministic=bool(raw.get("deterministic", False)),
        side_effects=tuple(str(x) for x in _list(raw.get("side_effects", []))),
        sandbox_required=bool(raw.get("sandbox_required", True)),
    )


def _validate_relative(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SkillPackageInvalid("Skill package path is unsafe")
    path = _safe_child(root, root / relative)
    if not path.is_file():
        raise SkillPackageInvalid("Declared skill package file is missing", details={"path": value})
    return path


def _safe_child(root: Path, path: Path) -> Path:
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SkillPackageInvalid("Skill package path escapes its root") from exc
    return resolved


def _mapping_list(value: Any, name: str) -> list[dict[str, Any]]:
    items = _list(value)
    if any(not isinstance(item, dict) for item in items):
        raise SkillManifestInvalid(f"Skill manifest {name} must contain mappings")
    return items


def _list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _version_tuple(value: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in value.split("-", 1)[0].split("."))  # type: ignore[return-value]


def _redact_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    blocked = {"secret", "token", "password", "authorization", "api_key"}
    return {
        key: value
        for key, value in metadata.items()
        if key.lower() not in blocked and not Path(str(value)).is_absolute()
    }
