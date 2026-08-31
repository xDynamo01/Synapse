from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import pytest
from tests.factories.windows_authority import authority

from synapse.coding_sessions import (
    FENCING_AUTHORITY_VERSION,
    CodingSessionIdentity,
    CodingSessionLeaseFactIdentity,
    CodingSessionRepositoryReference,
    FencingAuthority,
    FencingScope,
    FencingTransitionRequest,
)
from synapse.coding_sessions.fencing_sqlite import (
    FencingSQLiteConfig,
    SQLiteFencingGenerationStore,
)
from synapse.sandbox import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxArtifactInspectionRequest,
    SandboxFilesystemResource,
    SandboxLogicalPath,
    SandboxLogicalWorkspaceRoot,
    SandboxMaterializationAction,
    SandboxMaterializationCleanupPolicy,
    SandboxMaterializationOperation,
    SandboxMaterializationStepOutcome,
    SandboxMaterializationStepRequest,
    SandboxMaterializedFingerprintRequest,
    SandboxWorkspaceCleanupRequest,
    SandboxWorkspaceId,
    SandboxWorkspacePreparationRequest,
    SandboxWorkspaceVerificationRequest,
)
from synapse.sandbox_drivers import (
    SandboxFencingDecision,
    SandboxFencingValidationPort,
    WindowsWorkspaceConfig,
    WindowsWorkspaceDriver,
)
from synapse.sandbox_integrations.fencing import (
    CodingSessionsWorkspaceFencingValidator,
)


@dataclass
class Fencing:
    decision: SandboxFencingDecision = SandboxFencingDecision.VALID
    calls: int = 0

    def validate(self, workspace_id: SandboxWorkspaceId, operation: str) -> SandboxFencingDecision:
        self.calls += 1
        return self.decision


def _driver(
    config: WindowsWorkspaceConfig, fencing: SandboxFencingValidationPort
) -> WindowsWorkspaceDriver:
    guard, context = authority(fencing)
    return WindowsWorkspaceDriver(config, guard, context)


def _prepare(driver: WindowsWorkspaceDriver, workspace: SandboxWorkspaceId):
    return driver.prepare(SandboxWorkspacePreparationRequest(workspace, SandboxLogicalWorkspaceRoot("workspace"), SandboxMaterializationCleanupPolicy.AFTER_USE))


def _operation(workspace, source, fingerprint, logical="payload.txt"):
    return SandboxMaterializationStepRequest(workspace, SandboxMaterializationOperation(1, SandboxMaterializationAction.BIND_READONLY_INPUT, SandboxFilesystemResource.INPUT, SandboxLogicalPath.parse(logical, case_sensitive=False), source, fingerprint))


def _file_fingerprint(content: bytes) -> SandboxArtifactFingerprint:
    return SandboxArtifactFingerprint.from_content(
        ("file", len(content), hashlib.sha256(content).hexdigest())
    )


def test_prepare_layout_materialize_seal_and_cleanup(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"payload")
    reference = OpaqueReference("artifact:one")
    fingerprint = _file_fingerprint(b"payload")
    fencing = Fencing()
    driver = _driver(WindowsWorkspaceConfig(tmp_path / "root", ((reference, source),)), fencing)
    workspace = SandboxWorkspaceId("workspace:one")
    assert _prepare(driver, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    physical = tmp_path / "root" / "workspace-one"
    assert {item.name for item in physical.iterdir()} == {"input", "work", "output", "temp", "state"}
    assert driver.apply(_operation(workspace, reference, fingerprint)).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert (physical / "input" / "payload.txt").read_bytes() == b"payload"
    seal = SandboxMaterializationStepRequest(workspace, SandboxMaterializationOperation(2, SandboxMaterializationAction.SEAL_WORKSPACE, None, None, None, None))
    assert driver.seal(seal).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert driver.cleanup(SandboxWorkspaceCleanupRequest(workspace, SandboxArtifactFingerprint.from_content("plan"))).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert not physical.exists()
    assert fencing.calls >= 8


@pytest.mark.parametrize("logical", ["../escape", "C:/escape", "//server/share", "con/file", "bad\\path"])
def test_unsafe_paths_have_no_effect(tmp_path, logical) -> None:
    source = tmp_path / "source.txt"
    source.write_text("x")
    ref = OpaqueReference("artifact:x")
    driver = _driver(WindowsWorkspaceConfig(tmp_path / "root", ((ref, source),)), Fencing())
    workspace = SandboxWorkspaceId("workspace:path")
    _prepare(driver, workspace)
    try:
        path = SandboxLogicalPath.parse(logical, case_sensitive=False)
    except Exception:
        assert not (tmp_path / "escape").exists()
        return
    result = driver.apply(SandboxMaterializationStepRequest(workspace, SandboxMaterializationOperation(1, SandboxMaterializationAction.BIND_READONLY_INPUT, SandboxFilesystemResource.INPUT, path, ref, SandboxArtifactFingerprint.from_content(("file", b"x")))))
    assert result.outcome is SandboxMaterializationStepOutcome.FAILED
    assert not (tmp_path / "escape").exists()


def test_stale_and_unavailable_fencing_block_create_write_and_cleanup(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"x")
    ref = OpaqueReference("artifact:x")
    fencing = Fencing(SandboxFencingDecision.STALE)
    driver = _driver(WindowsWorkspaceConfig(tmp_path / "root", ((ref, source),)), fencing)
    workspace = SandboxWorkspaceId("workspace:stale")
    assert _prepare(driver, workspace).diagnostic_codes == ("fencing_stale",)
    assert not (tmp_path / "root" / "workspace-stale").exists()
    fencing.decision = SandboxFencingDecision.VALID
    _prepare(driver, workspace)
    before = tuple((tmp_path / "root" / "workspace-stale" / "input").iterdir())
    fencing.decision = SandboxFencingDecision.STALE
    assert driver.apply(_operation(workspace, ref, _file_fingerprint(b"x"))).diagnostic_codes == ("fencing_stale",)
    assert tuple((tmp_path / "root" / "workspace-stale" / "input").iterdir()) == before
    assert driver.cleanup(SandboxWorkspaceCleanupRequest(workspace, SandboxArtifactFingerprint.from_content("plan"))).diagnostic_codes == ("fencing_stale",)
    assert (tmp_path / "root" / "workspace-stale").exists()
    fencing.decision = SandboxFencingDecision.UNAVAILABLE
    assert driver.cleanup(SandboxWorkspaceCleanupRequest(workspace, SandboxArtifactFingerprint.from_content("plan"))).diagnostic_codes == ("fencing_unavailable",)


def test_symlink_and_hardlink_sources_are_rejected(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"x")
    hard = tmp_path / "hard.txt"
    os.link(source, hard)
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(source)
    except OSError:
        link = None
    refs = ((OpaqueReference("artifact:hard"), hard),)
    driver = _driver(WindowsWorkspaceConfig(tmp_path / "root", refs), Fencing())
    workspace = SandboxWorkspaceId("workspace:links")
    _prepare(driver, workspace)
    result = driver.apply(_operation(workspace, refs[0][0], _file_fingerprint(b"x")))
    assert result.diagnostic_codes == ("link_policy_violation",)


def test_health_is_factual_and_no_execution_surface(tmp_path) -> None:
    health = _driver(WindowsWorkspaceConfig(tmp_path / "root"), Fencing()).health()
    assert health.driver_implemented and health.readonly_enforcement == "readonly-attribute"
    assert not hasattr(WindowsWorkspaceDriver, "execute")


def test_inspection_directory_refingerprint_and_verification_detect_change(tmp_path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "nested.txt").write_bytes(b"nested")
    reference = OpaqueReference("artifact:tree")
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "root", ((reference, source),)), Fencing()
    )
    fingerprint = driver._fingerprint(source)
    assert driver.inspect(
        SandboxArtifactInspectionRequest(reference, fingerprint)
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert driver.inspect(
        SandboxArtifactInspectionRequest(reference, _file_fingerprint(b"wrong"))
    ).diagnostic_codes == ("fingerprint_mismatch",)
    assert driver.inspect(
        SandboxArtifactInspectionRequest(
            OpaqueReference("artifact:missing"), fingerprint
        )
    ).outcome is SandboxMaterializationStepOutcome.UNAVAILABLE

    workspace = SandboxWorkspaceId("workspace:verify")
    assert _prepare(driver, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert driver.apply(
        _operation(workspace, reference, fingerprint, "tree")
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    refingerprinted = driver.refingerprint(
        SandboxMaterializedFingerprintRequest(
            workspace,
            SandboxFilesystemResource.INPUT,
            SandboxLogicalPath.parse("tree", case_sensitive=False),
        )
    )
    assert refingerprinted.observed_fingerprint == fingerprint
    physical = tmp_path / "root" / "workspace-verify"
    expected = driver._fingerprint(physical)
    request = SandboxWorkspaceVerificationRequest(
        workspace, SandboxArtifactFingerprint.from_content("plan"), expected
    )
    assert driver.verify(request).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    (physical / "output" / "unexpected.txt").write_text("unexpected")
    assert driver.verify(request).diagnostic_codes == ("workspace_mismatch",)


def test_generation_transfer_invalidates_old_writer_before_filesystem_effect(tmp_path) -> None:
    workspace = SandboxWorkspaceId("workspace:generation")
    scope = FencingScope(
        CodingSessionIdentity.from_stable_key("session:generation"),
        CodingSessionRepositoryReference(
            "repository-runtime", "repository", "v1", "repository:generation"
        ),
        workspace_reference=workspace.value,
    )
    store = SQLiteFencingGenerationStore(FencingSQLiteConfig(str(tmp_path / "fencing.sqlite3")))
    store.migrate()
    authority = FencingAuthority(store)

    def transition(owner: str, generation: int):
        return authority.transition(
            FencingTransitionRequest(
                scope=scope,
                ownership_identity=CodingSessionLeaseFactIdentity.from_stable_key(
                    "lease:" + owner
                ),
                authority_identity="coding-sessions:fencing",
                authority_version=FENCING_AUTHORITY_VERSION,
                occurrence_reference="occurrence:" + owner,
                idempotency_key="transition:" + owner,
                expected_generation=generation,
            )
        )

    token_a = transition("a", 0)
    validator_a = CodingSessionsWorkspaceFencingValidator(
        authority,
        token_a,
        scope,
        token_a.ownership_identity,
        token_a.authority_identity,
    )
    driver_a = _driver(
        WindowsWorkspaceConfig(tmp_path / "root"), validator_a
    )
    assert _prepare(driver_a, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    before = tuple((tmp_path / "root" / "workspace-generation").rglob("*"))
    transition("b", 1)

    cleanup = driver_a.cleanup(
        SandboxWorkspaceCleanupRequest(
            workspace, SandboxArtifactFingerprint.from_content("plan")
        )
    )
    assert cleanup.diagnostic_codes == ("fencing_stale",)
    assert tuple((tmp_path / "root" / "workspace-generation").rglob("*")) == before
