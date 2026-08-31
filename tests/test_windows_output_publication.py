from __future__ import annotations

from dataclasses import replace

import pytest
from tests.factories.windows_authority import authority
from tests.test_windows_process_driver import Fencing
from tests.test_windows_workspace_driver import _file_fingerprint

from synapse.sandbox import OpaqueReference, SandboxWorkspaceId
from synapse.sandbox_drivers import (
    SandboxFencingDecision,
    WindowsArtifactPublicationRequestV1,
    WindowsArtifactPublicationState,
    WindowsCleanupCampaign,
    WindowsCleanupState,
    WindowsDeclaredOutputV1,
    WindowsOutputPublicationAdapter,
)

CAPABILITY = OpaqueReference("capability:artifact-publication")


def _setup(tmp_path, fencing=None, content=b"artifact-bytes"):
    workspace = SandboxWorkspaceId("workspace:publication")
    workspace_root = tmp_path / "workspaces"
    output_root = workspace_root / "workspace-publication" / "output"
    output_root.mkdir(parents=True)
    source = output_root / "report.bin"
    source.write_bytes(content)
    guard, contexts = authority(fencing or Fencing())
    context = contexts(workspace)
    context = replace(
        context,
        grant=replace(context.grant, capabilities=(CAPABILITY,)),
    )
    declared = WindowsDeclaredOutputV1(
        "report.bin",
        _file_fingerprint(content),
        OpaqueReference("output-binding:report"),
        OpaqueReference("execution:one"),
    )
    adapter = WindowsOutputPublicationAdapter(
        workspace_root,
        tmp_path / "custody",
        guard,
        ((workspace, declared),),
    )
    candidate, diagnostics = adapter.inspect(
        execution_reference=OpaqueReference("execution:one"),
        attempt_reference=context.attempt_reference,
        workspace_id=workspace,
        declared=declared,
        occurrence_reference=OpaqueReference("occurrence:publication"),
    )
    assert candidate is not None and diagnostics == ()
    request = WindowsArtifactPublicationRequestV1(
        candidate,
        candidate.fingerprint,
        OpaqueReference("publication:one"),
        CAPABILITY,
        context,
    )
    return adapter, source, tmp_path / "custody", request, guard, context


def test_declared_output_becomes_verified_candidate_but_not_automatic_publication(tmp_path) -> None:
    adapter, source, custody, request, _, _ = _setup(tmp_path)
    candidate = request.candidate
    assert candidate.state is WindowsArtifactPublicationState.VERIFIED
    assert candidate.logical_path == "report.bin"
    assert candidate.size_bytes == source.stat().st_size
    assert candidate.observed_type == "file"
    assert not custody.exists()
    assert adapter.health().local_custody_available
    assert not adapter.health().external_publication_available


def test_undeclared_unsafe_outside_and_reparse_outputs_are_rejected(tmp_path, monkeypatch) -> None:
    adapter, _, _, request, guard, _ = _setup(tmp_path)
    undeclared = replace(
        WindowsDeclaredOutputV1(
            "missing.bin",
            request.expected_fingerprint,
            OpaqueReference("output-binding:missing"),
            OpaqueReference("execution:one"),
        )
    )
    candidate, diagnostics = adapter.inspect(
        execution_reference=OpaqueReference("execution:one"),
        attempt_reference=request.candidate.attempt_reference,
        workspace_id=request.candidate.workspace_id,
        declared=undeclared,
        occurrence_reference=OpaqueReference("occurrence:missing"),
    )
    assert candidate is None and diagnostics == ("output_undeclared",)
    for path in ("../escape", "C:/escape", "//server/share", "bad\\path"):
        with pytest.raises(ValueError, match="output_path_invalid"):
            WindowsOutputPublicationAdapter(
                tmp_path / "workspaces",
                tmp_path / "other-custody",
                guard,
                ((request.candidate.workspace_id, replace(undeclared, logical_path=path)),),
            )
    monkeypatch.setattr(
        type(adapter),
        "_is_reparse",
        staticmethod(lambda path: path.name == "report.bin"),
    )
    candidate, diagnostics = adapter.inspect(
        execution_reference=request.candidate.execution_reference,
        attempt_reference=request.candidate.attempt_reference,
        workspace_id=request.candidate.workspace_id,
        declared=WindowsDeclaredOutputV1(
            "report.bin",
            request.expected_fingerprint,
            request.candidate.binding_reference,
            request.candidate.provenance_reference,
        ),
        occurrence_reference=OpaqueReference("occurrence:reparse"),
    )
    assert candidate is None and diagnostics == ("unsafe_reparse",)


def test_valid_publication_is_atomic_idempotent_verified_and_preserves_source(tmp_path) -> None:
    adapter, source, custody, request, _, _ = _setup(tmp_path)
    first = adapter.publish(request)
    second = adapter.publish(request)
    assert first.state is second.state is WindowsArtifactPublicationState.PUBLISHED
    assert first.publication_verified and first.source_preserved
    assert source.exists()
    published = [item for item in custody.iterdir() if not item.name.endswith(".publishing")]
    assert len(published) == 1
    assert published[0].read_bytes() == source.read_bytes()
    assert not any(item.name.endswith(".publishing") for item in custody.iterdir())


def test_stale_or_invalid_authority_has_zero_publication_effect(tmp_path) -> None:
    adapter, source, custody, request, _, _ = _setup(
        tmp_path, Fencing([SandboxFencingDecision.VALID, SandboxFencingDecision.STALE])
    )
    result = adapter.publish(request)
    assert result.state is WindowsArtifactPublicationState.PUBLICATION_FAILED
    assert result.diagnostic_codes == ("fencing_stale",)
    assert source.exists()
    assert not any(item.is_file() for item in custody.iterdir())

    adapter2, _, custody2, request2, _, _ = _setup(tmp_path / "invalid")
    invalid = replace(
        request2,
        publication_capability=OpaqueReference("capability:missing"),
    )
    result2 = adapter2.publish(invalid)
    assert result2.diagnostic_codes == ("publication_capability_missing",)
    assert not custody2.exists()


def test_stale_fingerprint_and_contradictory_duplicate_are_rejected(tmp_path) -> None:
    adapter, source, _, request, _, _ = _setup(tmp_path)
    source.write_bytes(b"changed-after-inspection")
    assert adapter.publish(request).diagnostic_codes == ("output_fingerprint_stale",)

    duplicate_root = tmp_path / "duplicate"
    adapter2, source2, _, request2, guard2, _ = _setup(duplicate_root)
    assert adapter2.publish(request2).state is WindowsArtifactPublicationState.PUBLISHED
    source2.write_bytes(b"other-content")
    declared = replace(
        WindowsDeclaredOutputV1(
            "report.bin",
            _file_fingerprint(b"other-content"),
            request2.candidate.binding_reference,
            request2.candidate.provenance_reference,
        )
    )
    changed_adapter = WindowsOutputPublicationAdapter(
        duplicate_root / "workspaces",
        duplicate_root / "custody",
        guard2,
        ((request2.candidate.workspace_id, declared),),
    )
    candidate, _ = changed_adapter.inspect(
        execution_reference=request2.candidate.execution_reference,
        attempt_reference=request2.candidate.attempt_reference,
        workspace_id=request2.candidate.workspace_id,
        declared=declared,
        occurrence_reference=OpaqueReference("occurrence:contradiction"),
    )
    assert candidate is not None
    conflict = changed_adapter.publish(
        replace(request2, candidate=candidate, expected_fingerprint=candidate.fingerprint)
    )
    assert conflict.diagnostic_codes == ("publication_idempotency_conflict",)


def test_partial_publication_and_replay_are_reconciliation_facts(tmp_path, monkeypatch) -> None:
    adapter, source, custody, request, _, _ = _setup(tmp_path)
    monkeypatch.setattr(
        "synapse.sandbox_drivers.windows_publication.os.replace",
        lambda source, target: (_ for _ in ()).throw(OSError()),
    )
    failed = adapter.publish(request)
    assert failed.state is WindowsArtifactPublicationState.PUBLICATION_FAILED
    assert source.exists() and not any(custody.iterdir())
    replayed = adapter.replay(failed)
    assert replayed.state is WindowsArtifactPublicationState.PUBLICATION_UNVERIFIED
    assert replayed.reconciliation_required
    assert not custody.exists() or not any(custody.iterdir())


def test_cleanup_order_partial_failure_stale_block_and_replay(tmp_path) -> None:
    adapter, source, _, request, guard, context = _setup(tmp_path)
    published = adapter.publish(request)
    events = []
    campaign = WindowsCleanupCampaign(guard)
    fact = campaign.run(
        request.candidate.attempt_reference,
        request.candidate.workspace_id,
        (
            ("handle_resources", lambda: events.append("handles") is None),
            ("output_finalization", lambda: events.append("output") is None),
            ("secret_revocation", lambda: False),
            ("publication_completion", lambda: published.publication_verified),
            ("workspace_cleanup", lambda: events.append("workspace") is None),
        ),
        context,
    )
    assert events == ["output", "handles", "workspace"]
    assert fact.state is WindowsCleanupState.PARTIAL
    assert fact.failed_steps == ("secret_revocation",)
    assert source.exists()
    assert campaign.replay(fact).state is WindowsCleanupState.RECONCILIATION_REQUIRED

    stale_guard, stale_contexts = authority(Fencing([SandboxFencingDecision.STALE]))
    called = []
    stale = WindowsCleanupCampaign(stale_guard).run(
        request.candidate.attempt_reference,
        request.candidate.workspace_id,
        (("workspace_cleanup", lambda: called.append(True) is None),),
        stale_contexts(request.candidate.workspace_id),
    )
    assert called == []
    assert stale.state is WindowsCleanupState.FAILED
    assert stale.reconciliation_required
