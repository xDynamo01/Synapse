from __future__ import annotations

from dataclasses import replace

import pytest

from acceptance.intelligence_boundary_support import asset, boundary_runtime, trust_external
from synapse.intelligence_boundary.errors import (
    BoundaryConflict,
    BoundaryValidationError,
    EgressApprovalRequired,
    EgressDenied,
    StaleEgressManifest,
)
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressDecisionStatus,
    EgressRequest,
    OperatingProfile,
    ProcessingBoundary,
    ProcessingPurpose,
)
from synapse.models.router import ModelRouter
from synapse.models.types import ModelRequest, ModelResponse


def request_for(
    asset_ids: tuple[str, ...],
    *,
    boundary: ProcessingBoundary = ProcessingBoundary.EXTERNAL_PROVIDER,
    provider: str = "external",
    checksum: str = "payload-v1",
    approval: str | None = None,
    constraints: tuple[str, ...] = (),
) -> EgressRequest:
    return EgressRequest(
        asset_ids,
        "user-a",
        "https://provider.example",
        boundary,
        ProcessingPurpose.MODEL_INFERENCE,
        provider_id=provider,
        payload_checksum=checksum,
        estimated_size=100,
        estimated_tokens=20,
        correlation_id="corr-a",
        approval_reference=approval,
        constraints=constraints,
    )


def test_asset_classification_category_and_metadata_are_canonical(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    saved = asset(runtime, "asset-a")
    assert saved.checksum
    assert runtime.get_asset("asset-a") == saved
    with pytest.raises(BoundaryConflict):
        asset(runtime, "asset-a")
    with pytest.raises(BoundaryValidationError):
        asset(runtime, "bad-category", category="invalid")


def test_derived_asset_inherits_most_restrictive_classification_and_training(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "public", DataClassification.PUBLIC)
    asset(runtime, "restricted", DataClassification.RESTRICTED)
    derived = runtime.register_derived_asset(
        asset_id="derived",
        input_asset_ids=("public", "restricted"),
        source_reference="model:result",
        content_type="text/plain",
        output_checksum="out",
        purpose=ProcessingPurpose.MODEL_INFERENCE,
    )
    assert derived.classification == DataClassification.RESTRICTED
    assert derived.provenance["classification_rule"] == "most-restrictive-input"


def test_downgrade_requires_justification_approval_and_validated_redaction(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "secret", DataClassification.SECRET)
    with pytest.raises(BoundaryValidationError):
        runtime.reclassify_asset(
            "secret", DataClassification.INTERNAL, actor_id="admin", justification="reviewed"
        )
    updated = runtime.reclassify_asset(
        "secret",
        DataClassification.INTERNAL,
        actor_id="admin",
        justification="verified removal",
        approval_id="approval-a",
        redaction_validated=True,
    )
    assert updated.classification == DataClassification.INTERNAL


def test_deny_precedence_and_missing_or_expired_trust(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "internal")
    denied = runtime.preview_egress(request_for(("internal",)))
    assert denied.decision.status == EgressDecisionStatus.DENIED
    trust_external(runtime)
    asset(runtime, "blocked", external_policy="denied")
    denied = runtime.preview_egress(request_for(("blocked",)))
    assert denied.decision.status == EgressDecisionStatus.DENIED


def test_local_processing_allowed_and_sovereign_external_is_local_only(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "asset")
    local = runtime.authorize_egress(
        request_for(
            ("asset",),
            boundary=ProcessingBoundary.LOCAL_MODEL,
            provider="local",
        )
    )
    assert local.allowed
    runtime.set_operating_profile(OperatingProfile.LOCAL_SOVEREIGN, actor_id="admin")
    with pytest.raises(EgressDenied):
        runtime.authorize_egress(request_for(("asset",)))


def test_minimization_omits_irrelevant_assets(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "relevant")
    asset(runtime, "irrelevant", relevant=False)
    result = runtime.preview_egress(request_for(("relevant", "irrelevant")))
    assert result.decision.minimization_plan.included_assets == ("relevant",)
    assert result.decision.minimization_plan.omitted_assets == ("irrelevant",)


def test_redaction_failure_blocks_external_processing(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "confidential", DataClassification.CONFIDENTIAL)
    result = runtime.preview_egress(
        request_for(("confidential",), constraints=("redaction_failure",))
    )
    assert result.decision.status == EgressDecisionStatus.DENIED


def test_scoped_approval_allows_unchanged_payload_and_rejects_change(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "confidential", DataClassification.CONFIDENTIAL)
    request = request_for(("confidential",))
    preview = runtime.preview_egress(request)
    assert preview.decision.approval_required and preview.manifest
    with pytest.raises(EgressApprovalRequired):
        runtime.authorize_egress(request)
    approval = runtime.grant_approval(
        preview.decision.decision_id,
        preview.manifest.manifest_id,
        approver="admin",
    )
    assert runtime.authorize_egress(
        replace(request, approval_reference=approval.approval_id)
    ).allowed
    with pytest.raises(StaleEgressManifest):
        runtime.authorize_egress(
            replace(request, payload_checksum="changed", approval_reference=approval.approval_id)
        )


def test_ephemeral_agent_cannot_approve(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "confidential", DataClassification.CONFIDENTIAL)
    preview = runtime.preview_egress(request_for(("confidential",)))
    assert preview.manifest
    with pytest.raises(EgressDenied):
        runtime.grant_approval(
            preview.decision.decision_id,
            preview.manifest.manifest_id,
            approver="ephemeral-a",
            actor_type="ephemeral_agent",
        )


def test_ledger_is_redacted_append_only_and_restart_safe(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    asset(runtime, "asset")
    authorization = runtime.authorize_egress(
        request_for(
            ("asset",), boundary=ProcessingBoundary.LOCAL_MODEL, provider="local"
        )
    )
    assert authorization.allowed
    before = runtime.ledger_history()
    restarted = boundary_runtime(tmp_path)
    assert restarted.ledger_history() == before
    assert all("payload" not in item.__dict__ for item in before)


def test_model_router_external_call_is_gated_and_output_gets_provenance(tmp_path) -> None:
    class Adapter:
        provider = "external"
        called = False

        def generate(self, request: ModelRequest) -> ModelResponse:
            self.called = True
            return ModelResponse("result", "external", request.model)

    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    adapter = Adapter()
    router = ModelRouter({}, adapters={"external": adapter})
    router.egress_gate = runtime
    response = router.generate_request(
        ModelRequest("agent-a", "external", "model-a", "hello", {}, base_url="https://x")
    )
    assert adapter.called
    assert response.metadata["egress_manifest_id"]
    assert runtime.get_asset(response.metadata["derived_asset_id"]).provenance["provider_id"] == (
        "external"
    )


def test_model_router_fails_closed_before_untrusted_external_adapter(tmp_path) -> None:
    class Adapter:
        provider = "untrusted"
        called = False

        def generate(self, request: ModelRequest) -> ModelResponse:
            self.called = True
            return ModelResponse("unsafe", "untrusted", request.model)

    runtime = boundary_runtime(tmp_path)
    adapter = Adapter()
    router = ModelRouter({}, adapters={"untrusted": adapter})
    router.egress_gate = runtime
    with pytest.raises(EgressDenied):
        router.generate_request(
            ModelRequest(
                "agent-a", "untrusted", "model-a", "secret", {}, base_url="https://x"
            )
        )
    assert not adapter.called
