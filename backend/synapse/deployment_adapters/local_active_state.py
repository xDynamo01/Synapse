"""Atomic local active-revision state and durable factual apply receipts."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from synapse.deployment import (
    ApplyReceiptReference,
    CapabilityReference,
    DeploymentFingerprint,
    LocalActiveStateMutationV1,
    LocalApplyReceiptV1,
    LocalApplyRequestV1,
    OccurrenceReference,
    RevisionId,
    canonical_json,
)


@dataclass(frozen=True, slots=True)
class LocalActiveStateConfigV1:
    root: Path


class LocalActiveStateAdapter:
    def __init__(self, config: LocalActiveStateConfigV1) -> None:
        self._root = config.root.resolve(strict=False)

    def staged_receipt(self, semantic: DeploymentFingerprint) -> LocalApplyReceiptV1 | None:
        path = self._receipt_path(semantic)
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        return LocalApplyReceiptV1(
            ApplyReceiptReference(raw["receipt_reference"]),
            raw["release_reference"],
            raw["attempt_reference"],
            raw["target_reference"],
            raw["environment_reference"],
            RevisionId(raw["applied_revision"]),
            CapabilityReference(raw["prepared_revision_reference"]),
            _optional_capability(raw["sandbox_execution_reference"]),
            _optional_capability(raw["active_state_mutation_reference"]),
            RevisionId(raw["previous_active_revision"])
            if raw["previous_active_revision"]
            else None,
            OccurrenceReference(raw["occurrence"]),
            tuple(raw["limitations"]),
            DeploymentFingerprint(raw["semantic_fingerprint"]),
        )

    def stage(self, request: LocalApplyRequestV1) -> LocalActiveStateMutationV1:
        semantic = request.semantic_fingerprint
        temporary = self._temporary_path(semantic)
        if temporary.exists():
            raise FileExistsError("local apply staging already exists")
        desired = request.preparation_request.correspondence.desired_revision
        prepared = request.preparation_result.prepared_revision_reference
        revision_fingerprint = request.preparation_result.revision_fingerprint
        if prepared is None or revision_fingerprint is None:
            raise ValueError("prepared revision reference and fingerprint are required")
        previous = self._current_revision()
        digest = semantic.value.split(":", 1)[1]
        mutation = LocalActiveStateMutationV1(
            CapabilityReference(f"active-state-mutation:{digest[:32]}"),
            desired.desired_revision.revision_id,
            prepared,
            revision_fingerprint,
            request.preparation_request.correspondence.target.target.target_id.value,
            request.preparation_request.correspondence.environment.environment.environment_id.value,
            (
                request.preparation_request.correspondence.target.target.slot_id.value
                if request.preparation_request.correspondence.target.target.slot_id
                else None
            ),
            previous,
            semantic,
        )
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(canonical_json(_mutation_payload(mutation)), encoding="utf-8")
        if json.loads(temporary.read_text(encoding="utf-8")) != _mutation_payload(mutation):
            raise OSError("active state staging verification failed")
        return mutation

    def promote(self, mutation: LocalActiveStateMutationV1) -> CapabilityReference:
        temporary = self._temporary_path(mutation.semantic_fingerprint)
        if json.loads(temporary.read_text(encoding="utf-8")) != _mutation_payload(mutation):
            raise OSError("active state staging mismatch")
        active = self._root / "active.json"
        active.parent.mkdir(parents=True, exist_ok=True)
        if active.exists():
            history = (
                self._root
                / "history"
                / f"{mutation.mutation_reference.value.split(':', 1)[1]}.json"
            )
            history.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(active, history)
        os.replace(temporary, active)
        return mutation.mutation_reference

    def record_receipt(self, receipt: LocalApplyReceiptV1) -> None:
        path = self._receipt_path(receipt.semantic_fingerprint)
        payload = _receipt_payload(receipt)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != payload:
                raise FileExistsError("apply receipt contradiction")
            return
        temporary = path.with_suffix(".preparing")
        temporary.write_text(canonical_json(payload), encoding="utf-8")
        os.replace(temporary, path)

    def incomplete(self, semantic: DeploymentFingerprint) -> bool:
        return self._temporary_path(semantic).exists() and not self._receipt_path(semantic).exists()

    def _current_revision(self) -> RevisionId | None:
        active = self._root / "active.json"
        if not active.exists():
            return None
        raw = json.loads(active.read_text(encoding="utf-8"))
        return RevisionId(raw["desired_revision"])

    def _temporary_path(self, semantic: DeploymentFingerprint) -> Path:
        digest = semantic.value.split(":", 1)[1]
        return self._root / "temporary" / f"{digest}.json"

    def _receipt_path(self, semantic: DeploymentFingerprint) -> Path:
        digest = semantic.value.split(":", 1)[1]
        return self._root / "receipts" / f"{digest}.json"


def _mutation_payload(mutation: LocalActiveStateMutationV1) -> dict[str, str | None]:
    return {
        "desired_revision": mutation.desired_revision.value,
        "mutation_reference": mutation.mutation_reference.value,
        "prepared_revision_reference": mutation.prepared_revision_reference.value,
        "revision_fingerprint": mutation.revision_fingerprint.value,
        "target_reference": mutation.target_reference,
        "environment_reference": mutation.environment_reference,
        "slot_reference": mutation.slot_reference,
        "previous_active_revision": (
            mutation.previous_active_revision.value if mutation.previous_active_revision else None
        ),
        "semantic_fingerprint": mutation.semantic_fingerprint.value,
    }


def _receipt_payload(receipt: LocalApplyReceiptV1) -> dict[str, object]:
    return {
        "active_state_mutation_reference": receipt.active_state_mutation_reference.value
        if receipt.active_state_mutation_reference
        else None,
        "applied_revision": receipt.applied_revision.value,
        "attempt_reference": receipt.attempt_reference,
        "environment_reference": receipt.environment_reference,
        "limitations": list(receipt.limitations),
        "occurrence": receipt.occurrence.value,
        "prepared_revision_reference": receipt.prepared_revision_reference.value,
        "previous_active_revision": (
            receipt.previous_active_revision.value if receipt.previous_active_revision else None
        ),
        "receipt_reference": receipt.receipt_reference.value,
        "release_reference": receipt.release_reference,
        "sandbox_execution_reference": receipt.sandbox_execution_reference.value
        if receipt.sandbox_execution_reference
        else None,
        "semantic_fingerprint": receipt.semantic_fingerprint.value,
        "target_reference": receipt.target_reference,
    }


def _optional_capability(value: str | None) -> CapabilityReference | None:
    return CapabilityReference(value) if value else None
