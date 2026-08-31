"""Consumer-owned translation from existing Sandbox custody facts."""

from __future__ import annotations

from synapse.deployment import (
    ArtifactAvailability,
    ArtifactFingerprintCorrespondence,
    ArtifactFingerprintReference,
    CustodyReference,
    DeploymentArtifactFactsRequestV1,
    DeploymentArtifactFactsResultV1,
    ProvenanceAvailability,
)
from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactCustodyPort,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionRequest,
    SandboxMaterializationStepOutcome,
)


class DeploymentCustodyFactsAdapter:
    def __init__(self, custody: SandboxArtifactCustodyPort | None) -> None:
        self._custody = custody

    def artifact_facts(
        self, request: DeploymentArtifactFactsRequestV1
    ) -> DeploymentArtifactFactsResultV1:
        if self._custody is None:
            return _unavailable()
        try:
            observed = self._custody.inspect(
                SandboxArtifactInspectionRequest(
                    OpaqueReference(request.artifact.artifact.value),
                    SandboxArtifactFingerprint(request.artifact.fingerprint.value),
                )
            )
        except (TypeError, ValueError):
            return _unavailable()
        observed_fingerprint = (
            ArtifactFingerprintReference(observed.observed_fingerprint.value)
            if observed.observed_fingerprint is not None
            else None
        )
        if observed.stale:
            return DeploymentArtifactFactsResultV1(
                ArtifactAvailability.AVAILABLE,
                ArtifactFingerprintCorrespondence.MISMATCH,
                ProvenanceAvailability.AVAILABLE,
                observed_fingerprint,
                CustodyReference(f"custody:{request.artifact.artifact.value}"),
            )
        if observed.outcome is SandboxMaterializationStepOutcome.SUCCEEDED:
            return DeploymentArtifactFactsResultV1(
                ArtifactAvailability.AVAILABLE,
                ArtifactFingerprintCorrespondence.MATCH,
                ProvenanceAvailability.AVAILABLE,
                observed_fingerprint,
                CustodyReference(f"custody:{request.artifact.artifact.value}"),
            )
        if observed.outcome is SandboxMaterializationStepOutcome.UNAVAILABLE:
            return _unavailable()
        return DeploymentArtifactFactsResultV1(
            ArtifactAvailability.UNKNOWN,
            ArtifactFingerprintCorrespondence.UNKNOWN,
            ProvenanceAvailability.UNKNOWN,
        )


def _unavailable() -> DeploymentArtifactFactsResultV1:
    return DeploymentArtifactFactsResultV1(
        ArtifactAvailability.UNAVAILABLE,
        ArtifactFingerprintCorrespondence.UNKNOWN,
        ProvenanceAvailability.UNKNOWN,
    )
