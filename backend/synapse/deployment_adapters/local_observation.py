"""Read-only observation of controlled local active state."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from synapse.deployment import (
    DeploymentFingerprint,
    LocalObservationOutcome,
    LocalObservationRequestV1,
    LocalObservationV1,
    LocalProcessObservationFactV1,
    LocalProcessObservationPort,
    LocalProcessState,
    LocalTargetFactsV1,
    ObservationReference,
    ObservedRevisionV1,
    RevisionId,
    content_fingerprint,
)


@dataclass(frozen=True, slots=True)
class LocalObservationConfigV1:
    active_state_root: Path


class LocalTargetObserver:
    def __init__(
        self,
        config: LocalObservationConfigV1,
        runtime: LocalProcessObservationPort,
        clock: Callable[[], datetime],
    ) -> None:
        self._root = config.active_state_root.resolve(strict=False)
        self._runtime = runtime
        self._clock = clock

    def current_fingerprint(self) -> DeploymentFingerprint | None:
        path = self._root / "active.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        return DeploymentFingerprint(content_fingerprint(payload))

    def observe(self, request: LocalObservationRequestV1) -> LocalObservationV1:
        observed_at = self._clock()
        path = self._root / "active.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return self._empty(request, observed_at, LocalObservationOutcome.UNAVAILABLE, "active-revision-unreadable")
        except (OSError, ValueError, TypeError):
            return self._empty(request, observed_at, LocalObservationOutcome.INDETERMINATE, "active-state-unreadable")
        required = {
            "desired_revision", "revision_fingerprint", "target_reference",
            "environment_reference", "semantic_fingerprint",
        }
        if not required.issubset(payload):
            return self._empty(request, observed_at, LocalObservationOutcome.INDETERMINATE, "revision-evidence-incomplete")
        try:
            active_revision = RevisionId(payload["desired_revision"])
            revision_fingerprint = DeploymentFingerprint(payload["revision_fingerprint"])
            active_fingerprint = DeploymentFingerprint(content_fingerprint(payload))
            runtime = self._runtime.observe(request.sandbox_execution_reference)
        except OSError:
            return self._empty(
                request,
                observed_at,
                LocalObservationOutcome.UNAVAILABLE,
                "observer-unavailable",
            )
        except (ValueError, TypeError):
            return self._empty(request, observed_at, LocalObservationOutcome.INCONSISTENT, "target-state-inconsistent")
        semantic = DeploymentFingerprint(content_fingerprint((
            request.release_reference, request.attempt_reference, request.target_reference,
            request.environment_reference, request.evidence_policy_reference,
            observed_at.isoformat(), active_fingerprint, runtime,
        )))
        reference = ObservationReference(f"observation:local-{semantic.value[7:39]}")
        facts = LocalTargetFactsV1(
            active_revision, revision_fingerprint, payload["target_reference"],
            payload["environment_reference"], payload.get("slot_reference"),
            active_fingerprint, runtime,
        )
        observed_revision = ObservedRevisionV1(active_revision, reference)
        limitations = runtime.limitations
        outcome = (
            LocalObservationOutcome.OBSERVED
            if runtime.state is not LocalProcessState.INDETERMINATE
            else LocalObservationOutcome.INDETERMINATE
        )
        return LocalObservationV1(
            outcome, reference, request.release_reference, request.attempt_reference,
            request.target_reference, request.environment_reference, observed_at,
            facts, observed_revision, limitations, semantic, request.evidence_policy_reference,
        )

    @staticmethod
    def _empty(
        request: LocalObservationRequestV1,
        observed_at: datetime,
        outcome: LocalObservationOutcome,
        reason: str,
    ) -> LocalObservationV1:
        semantic = DeploymentFingerprint(content_fingerprint((
            request.release_reference, request.attempt_reference, request.target_reference,
            request.environment_reference, request.evidence_policy_reference,
            observed_at.isoformat(), outcome, reason,
        )))
        return LocalObservationV1(
            outcome, None, request.release_reference, request.attempt_reference,
            request.target_reference, request.environment_reference, observed_at,
            None, None, (reason,), semantic, request.evidence_policy_reference,
        )


class UnavailableLocalRuntimeObserver:
    def observe(self, execution_reference: str | None) -> LocalProcessObservationFactV1:
        del execution_reference
        return LocalProcessObservationFactV1(
            LocalProcessState.UNAVAILABLE,
            limitations=("process-state-unavailable",),
        )
