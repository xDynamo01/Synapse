"""Atomic local service/application revision preparation without activation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
from dataclasses import dataclass
from pathlib import Path

from synapse.deployment import (
    AdapterBindingReference,
    CapabilityReference,
    DeploymentAppendDisposition,
    DeploymentEventId,
    DeploymentFencingAuthority,
    DeploymentFencingValidationState,
    DeploymentIdempotencyContradiction,
    DeploymentJournalAppendRequest,
    DeploymentJournalStore,
    DeploymentLifecycleState,
    DeploymentMachineKey,
    DeploymentMachineKind,
    DeploymentPersistenceError,
    DeploymentSandboxHandoffDraftV1,
    DeploymentTargetKind,
    DeploymentTransitionEventV1,
    EnvironmentOperationalClass,
    LocalRevisionPreparationFailure,
    LocalRevisionPreparationOutcome,
    LocalRevisionPreparationRequestV1,
    LocalRevisionPreparationResultV1,
    PreparationReference,
    authorization_is_current,
    canonical_json,
    eligibility_is_current,
    validate_target_correspondence,
)


@dataclass(frozen=True, slots=True)
class LocalServiceAdapterBindingV1:
    reference: AdapterBindingReference
    revision_root: Path
    artifact_sources: tuple[tuple[str, Path], ...]
    command_entrypoint: CapabilityReference
    resource_profile: CapabilityReference
    available_network_profiles: tuple[CapabilityReference, ...] = ()


class LocalServicePreparationAdapter:
    def __init__(
        self,
        binding: LocalServiceAdapterBindingV1,
        fencing: DeploymentFencingAuthority,
        journal: DeploymentJournalStore,
    ) -> None:
        self._binding = binding
        self._root = binding.revision_root.resolve(strict=False)
        self._sources = {
            reference: path.resolve(strict=False) for reference, path in binding.artifact_sources
        }
        self._fencing = fencing
        self._journal = journal

    def prepare(
        self, request: LocalRevisionPreparationRequestV1
    ) -> LocalRevisionPreparationResultV1:
        blocked = self._preconditions(request)
        if blocked is not None:
            return blocked
        source = self._sources.get(request.correspondence.desired_revision.artifact.artifact.value)
        if source is None or not source.exists():
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.ADAPTER_BINDING_UNAVAILABLE,
            )
        if source.is_symlink() or (
            source.is_dir() and any(item.is_symlink() for item in source.rglob("*"))
        ):
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.FILESYSTEM_PREPARATION_FAILED,
            )
        try:
            acceptance = self._fencing.accept_operation(
                request.idempotency,
                request.fencing_token,
                owner=request.authorization.requester,
                authority_identity=request.fencing_authority,
            )
        except DeploymentIdempotencyContradiction:
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.PREPARATION_CONFLICT,
            )
        if acceptance.fencing.state is not DeploymentFencingValidationState.VALID:
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.FENCING_STALE_OR_UNAVAILABLE,
            )

        revision = request.correspondence.desired_revision
        revision_name = revision.desired_revision.revision_id.value.split(":", 1)[1]
        prepared = self._root / "revisions" / revision_name
        manifest = prepared / "preparation.json"
        expected_manifest = self._manifest(request)
        if prepared.exists():
            if self._manifest_matches(manifest, expected_manifest):
                return self._success(request, LocalRevisionPreparationOutcome.ALREADY_PREPARED)
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.PREPARATION_CONFLICT,
            )

        staging = self._root / "temporary" / f"{revision_name}.preparing"
        if staging.exists():
            return self._result(
                LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN,
                LocalRevisionPreparationFailure.RECONCILIATION_REQUIRED,
            )
        try:
            (staging / "content").mkdir(parents=True, exist_ok=False)
            destination = staging / "content" / "artifact"
            if source.is_dir():
                shutil.copytree(source, destination, symlinks=True)
            else:
                shutil.copy2(source, destination, follow_symlinks=False)
            observed = _fingerprint(destination)
            expected = revision.artifact.fingerprint.value
            if observed != expected:
                return self._partial(
                    LocalRevisionPreparationFailure.FINGERPRINT_VERIFICATION_FAILED
                )
            (staging / "preparation.json").write_text(
                canonical_json(expected_manifest), encoding="utf-8"
            )
            blocked = self._preconditions(request)
            if blocked is not None:
                return self._partial(
                    blocked.failure or LocalRevisionPreparationFailure.FENCING_STALE_OR_UNAVAILABLE
                )
            self._readonly_tree(staging / "content")
            prepared.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, prepared)
            for category in ("runtime-state", "logs"):
                (self._root / category / revision_name).mkdir(parents=True, exist_ok=True)
        except OSError:
            if staging.exists():
                return self._result(
                    LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN,
                    LocalRevisionPreparationFailure.RECONCILIATION_REQUIRED,
                )
            return self._result(
                LocalRevisionPreparationOutcome.FAILED,
                LocalRevisionPreparationFailure.FILESYSTEM_PREPARATION_FAILED,
            )

        result = self._success(request, LocalRevisionPreparationOutcome.PREPARED)
        try:
            event = self._prepared_event(request)
            machine = DeploymentMachineKey(
                DeploymentMachineKind.DEPLOYMENT,
                request.correspondence.attempt.attempt_id.value,
            )
            append = self._journal.append(
                DeploymentJournalAppendRequest(
                    machine, self._journal.latest_sequence(machine) + 1, event
                )
            )
            if append.disposition not in {
                DeploymentAppendDisposition.APPENDED,
                DeploymentAppendDisposition.IDEMPOTENT,
            }:
                raise RuntimeError("journal append unavailable")
        except (DeploymentPersistenceError, OSError, RuntimeError, ValueError):
            return self._result(
                LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN,
                LocalRevisionPreparationFailure.RECONCILIATION_REQUIRED,
            )
        return result

    def inspect(
        self, request: LocalRevisionPreparationRequestV1
    ) -> LocalRevisionPreparationResultV1:
        revision_name = (
            request.correspondence.desired_revision.desired_revision.revision_id.value.split(
                ":", 1
            )[1]
        )
        manifest = self._root / "revisions" / revision_name / "preparation.json"
        if self._manifest_matches(manifest, self._manifest(request)):
            return self._success(request, LocalRevisionPreparationOutcome.ALREADY_PREPARED)
        if (self._root / "temporary" / f"{revision_name}.preparing").exists():
            return self._result(
                LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN,
                LocalRevisionPreparationFailure.RECONCILIATION_REQUIRED,
            )
        return self._result(
            LocalRevisionPreparationOutcome.BLOCKED,
            LocalRevisionPreparationFailure.REVISION_MISMATCH,
        )

    def cleanup_temporary(self, request: LocalRevisionPreparationRequestV1) -> bool:
        if self._preconditions(request) is not None:
            return False
        revision_name = (
            request.correspondence.desired_revision.desired_revision.revision_id.value.split(
                ":", 1
            )[1]
        )
        staging = self._root / "temporary" / f"{revision_name}.preparing"
        if not staging.exists():
            return True
        shutil.rmtree(staging)
        return True

    def _preconditions(
        self, request: LocalRevisionPreparationRequestV1
    ) -> LocalRevisionPreparationResultV1 | None:
        target = request.correspondence.target
        if (
            target.kind
            not in {DeploymentTargetKind.LOCAL_SERVICE, DeploymentTargetKind.APPLICATION}
            or request.correspondence.environment.operational_class
            is not EnvironmentOperationalClass.LOCAL
        ):
            return self._result(
                LocalRevisionPreparationOutcome.UNSUPPORTED,
                LocalRevisionPreparationFailure.UNSUPPORTED_TARGET,
            )
        if target.target.adapter_binding != self._binding.reference:
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.ADAPTER_BINDING_UNAVAILABLE,
            )
        try:
            validate_target_correspondence(request.correspondence)
        except ValueError:
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.REVISION_MISMATCH,
            )
        if not eligibility_is_current(request):
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.ELIGIBILITY_STALE,
            )
        if not authorization_is_current(request):
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.AUTHORIZATION_INVALID,
            )
        if (
            request.command_entrypoint != self._binding.command_entrypoint
            or request.resource_profile != self._binding.resource_profile
        ):
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.ADAPTER_BINDING_UNAVAILABLE,
            )
        if request.network_profile is not None and (
            not request.network_profile_available
            or request.network_profile not in self._binding.available_network_profiles
        ):
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.NETWORK_PROFILE_UNAVAILABLE,
            )
        validation = self._fencing.validate(
            request.fencing_token,
            scope=request.idempotency.scope,
            owner=request.authorization.requester,
            authority_identity=request.fencing_authority,
            operation=request.idempotency.operation,
            semantic_binding_fingerprint=request.semantic_fingerprint,
        )
        if validation.state is not DeploymentFencingValidationState.VALID:
            return self._result(
                LocalRevisionPreparationOutcome.BLOCKED,
                LocalRevisionPreparationFailure.FENCING_STALE_OR_UNAVAILABLE,
            )
        return None

    def _success(
        self, request: LocalRevisionPreparationRequestV1, outcome: LocalRevisionPreparationOutcome
    ) -> LocalRevisionPreparationResultV1:
        digest = request.semantic_fingerprint.value.split(":", 1)[1]
        handoff = DeploymentSandboxHandoffDraftV1(
            CapabilityReference(f"sandbox-workspace:deployment-{digest[:24]}"),
            request.correspondence.desired_revision.artifact.artifact.value,
            request.correspondence.desired_revision.artifact.fingerprint.value,
            request.command_entrypoint,
            request.resource_profile,
            request.network_profile,
            request.correspondence.target.secret_requirements,
            request.correspondence.attempt.attempt_id.value,
            request.correspondence.attempt.release_id.value,
            request.authorization.authorization_reference,
            request.fencing_token.token_fingerprint
            if request.fencing_token
            else request.semantic_fingerprint,
        )
        return LocalRevisionPreparationResultV1(
            outcome,
            PreparationReference(f"preparation:local-{digest[:32]}"),
            CapabilityReference(f"prepared-revision:{digest[:32]}"),
            request.correspondence.desired_revision.revision_fingerprint,
            handoff,
            None,
            ("target-not-active", "sandbox-not-executed", "verification-not-complete"),
        )

    @staticmethod
    def _result(
        outcome: LocalRevisionPreparationOutcome, failure: LocalRevisionPreparationFailure
    ) -> LocalRevisionPreparationResultV1:
        return LocalRevisionPreparationResultV1(outcome, None, None, None, None, failure, ())

    def _partial(
        self, failure: LocalRevisionPreparationFailure
    ) -> LocalRevisionPreparationResultV1:
        return self._result(LocalRevisionPreparationOutcome.OUTCOME_UNKNOWN, failure)

    @staticmethod
    def _manifest(request: LocalRevisionPreparationRequestV1) -> dict[str, str]:
        desired = request.correspondence.desired_revision
        return {
            "artifact_fingerprint": desired.artifact.fingerprint.value,
            "artifact_reference": desired.artifact.artifact.value,
            "preparation_fingerprint": request.semantic_fingerprint.value,
            "revision_fingerprint": desired.revision_fingerprint.value,
            "revision_id": desired.desired_revision.revision_id.value,
            "target_configuration_fingerprint": desired.target_configuration_fingerprint.value,
        }

    @staticmethod
    def _manifest_matches(path: Path, expected: dict[str, str]) -> bool:
        try:
            return json.loads(path.read_text(encoding="utf-8")) == expected
        except (OSError, ValueError):
            return False

    @staticmethod
    def _readonly_tree(root: Path) -> None:
        for path in (root, *root.rglob("*")):
            path.chmod(path.stat().st_mode & ~stat.S_IWRITE)

    @staticmethod
    def _prepared_event(request: LocalRevisionPreparationRequestV1) -> DeploymentTransitionEventV1:
        digest = request.semantic_fingerprint.value.split(":", 1)[1]
        attempt = request.correspondence.attempt
        return DeploymentTransitionEventV1(
            DeploymentEventId(f"deployment-event:preparation-{digest[:32]}"),
            attempt.release_id,
            attempt.attempt_id,
            DeploymentLifecycleState.AUTHORIZED,
            DeploymentLifecycleState.PREPARED,
            attempt.correlation,
            None,
            request.occurrence,
            request.authorization.authorization_reference,
            failure_class=None,
        )


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    else:
        for item in sorted(
            path.rglob("*"), key=lambda candidate: candidate.relative_to(path).as_posix()
        ):
            relative = item.relative_to(path).as_posix().encode("utf-8")
            digest.update(relative + b"\0")
            if item.is_file():
                with item.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
    return "sha256:" + digest.hexdigest()
