from dataclasses import replace

import pytest

from synapse.intelligence_boundary.errors import StaleEgressManifest
from synapse.intelligence_boundary.models import DataClassification

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_external_provider_approval_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "confidential", DataClassification.CONFIDENTIAL)
    request = egress_request(("confidential",))
    preview = runtime.preview_egress(request)
    assert preview.manifest
    approval = runtime.grant_approval(
        preview.decision.decision_id, preview.manifest.manifest_id, approver="admin"
    )
    approved = replace(request, approval_reference=approval.approval_id)
    assert runtime.authorize_egress(approved).allowed
    with pytest.raises(StaleEgressManifest):
        runtime.authorize_egress(replace(approved, payload_checksum="changed"))
