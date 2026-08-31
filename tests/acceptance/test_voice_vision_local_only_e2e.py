import pytest

from synapse.intelligence_boundary.errors import EgressDenied
from synapse.intelligence_boundary.models import DataClassification, ProcessingBoundary

from .intelligence_boundary_support import (
    asset,
    boundary_runtime,
    egress_request,
    trust_external,
)


def test_voice_vision_local_only_e2e(tmp_path) -> None:
    runtime = boundary_runtime(tmp_path)
    trust_external(runtime)
    asset(runtime, "audio", DataClassification.RESTRICTED, category="media.audio")
    asset(runtime, "image", DataClassification.RESTRICTED, category="media.image")
    with pytest.raises(EgressDenied):
        runtime.authorize_egress(egress_request(("audio", "image")))
    local = runtime.authorize_egress(
        egress_request(
            ("audio", "image"),
            boundary=ProcessingBoundary.LOCAL_PROCESS,
            provider_id="local-media",
        )
    )
    assert local.allowed and local.manifest
