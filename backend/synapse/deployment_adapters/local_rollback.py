"""Concrete local rollback preparation and atomic active-state adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from synapse.deployment import (
    CapabilityReference,
    DeploymentFencingAuthority,
    DeploymentFencingValidationState,
    DeploymentFingerprint,
    DeploymentIdempotencyContradiction,
    LocalRollbackApplyRequestV1,
    LocalRollbackFailure,
    LocalRollbackMutationV1,
    LocalRollbackPreparationOutcome,
    LocalRollbackPreparationRequestV1,
    LocalRollbackPreparationResultV1,
    LocalRollbackReceiptV1,
    OccurrenceReference,
    RevisionId,
    RollbackReceiptReference,
    canonical_json,
    rollback_authorization_is_current,
    rollback_eligibility_is_current,
)


@dataclass(frozen=True, slots=True)
class LocalRollbackAdapterConfigV1:
    revision_root: Path
    active_state_root: Path
    artifact_sources: tuple[tuple[str, Path], ...]


class LocalRollbackPreparationAdapter:
    def __init__(self, config: LocalRollbackAdapterConfigV1, fencing: DeploymentFencingAuthority) -> None:
        self._root = config.revision_root.resolve(strict=False)
        self._sources = {key: value.resolve(strict=False) for key, value in config.artifact_sources}
        self._fencing = fencing

    def prepare(self, request: LocalRollbackPreparationRequestV1) -> LocalRollbackPreparationResultV1:
        failure = self._guard(request)
        if failure is not None:
            return self._result(LocalRollbackPreparationOutcome.FAILED, failure)
        source = self._sources.get(request.artifact.value)
        if source is None or not source.exists() or source.is_symlink():
            return self._result(
                LocalRollbackPreparationOutcome.UNAVAILABLE,
                LocalRollbackFailure.ARTIFACT_UNAVAILABLE,
            )
        try:
            accepted = self._fencing.accept_operation(
                request.idempotency,
                request.fencing_token,
                owner=request.authorization.requester,
                authority_identity=request.fencing_authority,
            )
        except DeploymentIdempotencyContradiction:
            return self._result(
                LocalRollbackPreparationOutcome.FAILED,
                LocalRollbackFailure.IDEMPOTENCY_CONTRADICTION,
            )
        if accepted.fencing.state is not DeploymentFencingValidationState.VALID:
            return self._result(LocalRollbackPreparationOutcome.FAILED, LocalRollbackFailure.FENCING_INVALID)
        name = request.rollback.intended_revision.value.split(":", 1)[1]
        prepared = self._root / "revisions" / name
        manifest = prepared / "rollback-preparation.json"
        expected = self._manifest(request)
        if prepared.exists():
            if self._matches(manifest, expected):
                return self._success(request, LocalRollbackPreparationOutcome.ALREADY_PREPARED)
            return self._result(LocalRollbackPreparationOutcome.FAILED, LocalRollbackFailure.ARTIFACT_MISMATCH)
        staging = self._root / "temporary" / f"rollback-{name}.preparing"
        if staging.exists():
            return self._result(
                LocalRollbackPreparationOutcome.OUTCOME_UNKNOWN,
                LocalRollbackFailure.RECONCILIATION_REQUIRED,
            )
        try:
            (staging / "content").mkdir(parents=True)
            destination = staging / "content" / "artifact"
            shutil.copy2(source, destination, follow_symlinks=False)
            if "sha256:" + hashlib.sha256(destination.read_bytes()).hexdigest() != request.artifact_fingerprint.value:
                return self._result(LocalRollbackPreparationOutcome.FAILED, LocalRollbackFailure.ARTIFACT_MISMATCH)
            (staging / "rollback-preparation.json").write_text(canonical_json(expected), encoding="utf-8")
            failure = self._guard(request)
            if failure is not None:
                return self._result(LocalRollbackPreparationOutcome.OUTCOME_UNKNOWN, failure)
            prepared.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, prepared)
        except OSError:
            return self._result(
                LocalRollbackPreparationOutcome.OUTCOME_UNKNOWN if staging.exists() else LocalRollbackPreparationOutcome.FAILED,
                LocalRollbackFailure.RECONCILIATION_REQUIRED if staging.exists() else LocalRollbackFailure.PREPARATION_FAILED,
            )
        return self._success(request, LocalRollbackPreparationOutcome.PREPARED)

    def _guard(self, request: LocalRollbackPreparationRequestV1) -> LocalRollbackFailure | None:
        if request.rollback.intended_revision == request.rollback.source_revision:
            return LocalRollbackFailure.TARGET_NOT_EXPLICIT
        if not rollback_eligibility_is_current(request):
            return LocalRollbackFailure.ELIGIBILITY_INVALID
        if not rollback_authorization_is_current(request):
            return LocalRollbackFailure.AUTHORIZATION_INVALID
        validation = self._fencing.validate(
            request.fencing_token,
            scope=request.idempotency.scope,
            owner=request.authorization.requester,
            authority_identity=request.fencing_authority,
            operation=request.idempotency.operation,
            semantic_binding_fingerprint=request.semantic_fingerprint,
        )
        return None if validation.state is DeploymentFencingValidationState.VALID else LocalRollbackFailure.FENCING_INVALID

    @staticmethod
    def _manifest(request: LocalRollbackPreparationRequestV1) -> dict[str, str]:
        return {
            "artifact_reference": request.artifact.value,
            "artifact_fingerprint": request.artifact_fingerprint.value,
            "revision_id": request.rollback.intended_revision.value,
            "revision_fingerprint": request.revision_fingerprint.value,
            "target_configuration_fingerprint": request.target_configuration_fingerprint.value,
            "rollback_preparation_fingerprint": request.semantic_fingerprint.value,
        }

    @staticmethod
    def _matches(path: Path, expected: dict[str, str]) -> bool:
        try:
            return json.loads(path.read_text(encoding="utf-8")) == expected
        except (OSError, ValueError):
            return False

    @staticmethod
    def _success(request: LocalRollbackPreparationRequestV1, outcome: LocalRollbackPreparationOutcome) -> LocalRollbackPreparationResultV1:
        digest = request.semantic_fingerprint.value[7:]
        return LocalRollbackPreparationResultV1(
            outcome,
            CapabilityReference(f"prepared-rollback-revision:{digest[:32]}"),
            CapabilityReference(f"rollback-preparation:{digest[:32]}"),
            request.revision_fingerprint,
            None,
            ("not-active", "not-verified"),
        )

    @staticmethod
    def _result(outcome: LocalRollbackPreparationOutcome, failure: LocalRollbackFailure) -> LocalRollbackPreparationResultV1:
        return LocalRollbackPreparationResultV1(outcome, None, None, None, failure)


class LocalRollbackStateAdapter:
    def __init__(self, config: LocalRollbackAdapterConfigV1) -> None:
        self._root = config.active_state_root.resolve(strict=False)

    def receipt(self, semantic: DeploymentFingerprint) -> LocalRollbackReceiptV1 | None:
        path = self._receipt_path(semantic)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LocalRollbackReceiptV1(
            RollbackReceiptReference(raw["receipt_reference"]), raw["rollback_attempt_reference"],
            raw["release_reference"], raw["target_reference"], raw["environment_reference"],
            RevisionId(raw["source_revision"]), RevisionId(raw["intended_revision"]),
            RevisionId(raw["applied_revision"]), CapabilityReference(raw["prepared_revision_reference"]),
            CapabilityReference(raw["sandbox_execution_reference"]) if raw["sandbox_execution_reference"] else None,
            CapabilityReference(raw["active_state_mutation_reference"]) if raw["active_state_mutation_reference"] else None,
            OccurrenceReference(raw["occurrence"]), tuple(raw["limitations"]),
            DeploymentFingerprint(raw["semantic_fingerprint"]),
        )

    def incomplete(self, semantic: DeploymentFingerprint) -> bool:
        return self._temporary(semantic).exists() and not self._receipt_path(semantic).exists()

    def stage(self, request: LocalRollbackApplyRequestV1) -> LocalRollbackMutationV1:
        prepared = request.preparation_result.prepared_revision_reference
        fingerprint = request.preparation_result.revision_fingerprint
        if prepared is None or fingerprint is None:
            raise ValueError("rollback preparation is incomplete")
        rollback = request.preparation_request.rollback
        mutation = LocalRollbackMutationV1(
            CapabilityReference(f"rollback-active-mutation:{request.semantic_fingerprint.value[7:39]}"),
            rollback.source_revision, rollback.intended_revision, prepared, fingerprint,
            rollback.target_id.value, request.preparation_request.environment_reference,
            request.semantic_fingerprint,
        )
        path = self._temporary(request.semantic_fingerprint)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical_json(self._mutation_payload(mutation)), encoding="utf-8")
        return mutation

    def promote(self, mutation: LocalRollbackMutationV1) -> CapabilityReference:
        active = self._root / "active.json"
        current = json.loads(active.read_text(encoding="utf-8"))
        if current.get("desired_revision") != mutation.source_revision.value:
            raise ValueError("rollback source revision is no longer active")
        history = self._root / "history" / f"{mutation.mutation_reference.value.split(':', 1)[1]}.json"
        history.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(active, history)
        payload = self._mutation_payload(mutation)
        os.replace(self._temporary(mutation.semantic_fingerprint), active)
        if json.loads(active.read_text(encoding="utf-8")) != payload:
            raise OSError("rollback active state promotion mismatch")
        return mutation.mutation_reference

    def record(self, receipt: LocalRollbackReceiptV1) -> None:
        path = self._receipt_path(receipt.semantic_fingerprint)
        payload = {
            "receipt_reference": receipt.receipt_reference.value,
            "rollback_attempt_reference": receipt.rollback_attempt_reference,
            "release_reference": receipt.release_reference,
            "target_reference": receipt.target_reference,
            "environment_reference": receipt.environment_reference,
            "source_revision": receipt.source_revision.value,
            "intended_revision": receipt.intended_revision.value,
            "applied_revision": receipt.applied_revision.value,
            "prepared_revision_reference": receipt.prepared_revision_reference.value,
            "sandbox_execution_reference": receipt.sandbox_execution_reference.value if receipt.sandbox_execution_reference else None,
            "active_state_mutation_reference": receipt.active_state_mutation_reference.value if receipt.active_state_mutation_reference else None,
            "occurrence": receipt.occurrence.value,
            "limitations": list(receipt.limitations),
            "semantic_fingerprint": receipt.semantic_fingerprint.value,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and json.loads(path.read_text(encoding="utf-8")) != payload:
            raise FileExistsError("rollback receipt contradiction")
        if not path.exists():
            path.write_text(canonical_json(payload), encoding="utf-8")

    @staticmethod
    def _mutation_payload(mutation: LocalRollbackMutationV1) -> dict[str, str | None]:
        return {
            "desired_revision": mutation.intended_revision.value,
            "prepared_revision_reference": mutation.prepared_revision_reference.value,
            "revision_fingerprint": mutation.revision_fingerprint.value,
            "target_reference": mutation.target_reference,
            "environment_reference": mutation.environment_reference,
            "slot_reference": None,
            "semantic_fingerprint": mutation.semantic_fingerprint.value,
            "mutation_reference": mutation.mutation_reference.value,
            "previous_active_revision": mutation.source_revision.value,
        }

    def _temporary(self, semantic: DeploymentFingerprint) -> Path:
        return self._root / "temporary" / f"rollback-{semantic.value[7:]}.json"

    def _receipt_path(self, semantic: DeploymentFingerprint) -> Path:
        return self._root / "rollback-receipts" / f"{semantic.value[7:]}.json"
