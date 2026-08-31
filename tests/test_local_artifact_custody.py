from __future__ import annotations

import os
from dataclasses import dataclass

import pytest
from tests.factories.windows_authority import authority

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
)
from synapse.sandbox_drivers import (
    GovernedArtifactBinding,
    LocalArtifactCustody,
    LocalArtifactCustodyConfig,
    LocalArtifactMaterializationAdapter,
    LocalArtifactRegistration,
    SandboxFencingDecision,
    WindowsWorkspaceConfig,
    WindowsWorkspaceDriver,
    fingerprint_local_artifact,
)


@dataclass
class Fencing:
    decision: SandboxFencingDecision = SandboxFencingDecision.VALID

    def validate(
        self, workspace_id: SandboxWorkspaceId, operation: str
    ) -> SandboxFencingDecision:
        return self.decision


@dataclass
class TransferringFencing:
    valid_calls_remaining: int

    def validate(
        self, workspace_id: SandboxWorkspaceId, operation: str
    ) -> SandboxFencingDecision:
        if self.valid_calls_remaining <= 0:
            return SandboxFencingDecision.STALE
        self.valid_calls_remaining -= 1
        return SandboxFencingDecision.VALID


def _driver(config: WindowsWorkspaceConfig, fencing) -> WindowsWorkspaceDriver:
    guard, context = authority(fencing)
    return WindowsWorkspaceDriver(config, guard, context)


def _custody(tmp_path, reference, logical="payload.txt"):
    root = tmp_path / "custody"
    root.mkdir(parents=True, exist_ok=True)
    custody = LocalArtifactCustody(
        LocalArtifactCustodyConfig(
            (("approved", root),),
            (
                LocalArtifactRegistration(
                    reference,
                    "approved",
                    logical,
                    OpaqueReference("provenance:fixture"),
                ),
            ),
        )
    )
    return root, custody


def _prepare(driver, workspace):
    return driver.prepare(
        SandboxWorkspacePreparationRequest(
            workspace,
            SandboxLogicalWorkspaceRoot("workspace"),
            SandboxMaterializationCleanupPolicy.AFTER_USE,
        )
    )


def _apply(driver, workspace, reference, fingerprint, logical="payload.txt"):
    return driver.apply(
        SandboxMaterializationStepRequest(
            workspace,
            SandboxMaterializationOperation(
                1,
                SandboxMaterializationAction.BIND_READONLY_INPUT,
                SandboxFilesystemResource.INPUT,
                SandboxLogicalPath.parse(logical, case_sensitive=False),
                reference,
                fingerprint,
            ),
        )
    )


def test_file_custody_is_deterministic_and_stale_is_not_promoted(tmp_path) -> None:
    reference = OpaqueReference("artifact:file")
    root, custody = _custody(tmp_path, reference)
    source = root / "payload.txt"
    source.write_bytes(b"payload")
    expected = fingerprint_local_artifact(source)
    assert expected == fingerprint_local_artifact(source)
    assert custody.inspect(
        SandboxArtifactInspectionRequest(reference, expected)
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    source.write_bytes(b"changed")
    stale = custody.inspect(SandboxArtifactInspectionRequest(reference, expected))
    assert stale.stale and stale.diagnostic_codes == ("artifact_stale",)


def test_tree_fingerprint_tracks_structure_content_and_nested_copy(tmp_path) -> None:
    reference = OpaqueReference("artifact:tree")
    root, custody = _custody(tmp_path, reference, "tree")
    source = root / "tree"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "data.txt").write_text("one")
    first = fingerprint_local_artifact(source)
    (source / "nested" / "data.txt").write_text("two")
    assert fingerprint_local_artifact(source) != first
    (source / "nested" / "data.txt").write_text("one")
    expected = fingerprint_local_artifact(source)
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", custody=custody), Fencing()
    )
    workspace = SandboxWorkspaceId("workspace:tree")
    assert _prepare(driver, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert _apply(driver, workspace, reference, expected, "tree").outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert (
        tmp_path / "workspaces" / "workspace-tree" / "input" / "tree" / "nested" / "data.txt"
    ).read_text() == "one"


@pytest.mark.parametrize("logical", ["../escape", "C:/escape", "//server/share", "bad\\path"])
def test_custody_rejects_source_escape_without_host_path_diagnostic(tmp_path, logical) -> None:
    reference = OpaqueReference("artifact:escape")
    _, custody = _custody(tmp_path, reference, logical)
    result = custody.inspect(
        SandboxArtifactInspectionRequest(
            reference, SandboxArtifactFingerprint.from_content("expected")
        )
    )
    assert result.diagnostic_codes == ("artifact_outside_custody",)
    assert str(tmp_path) not in repr(result)


def test_missing_reparse_and_hardlink_are_factual(tmp_path) -> None:
    missing = OpaqueReference("artifact:missing")
    root, custody = _custody(tmp_path, missing, "missing.txt")
    assert custody.inspect(
        SandboxArtifactInspectionRequest(
            missing, SandboxArtifactFingerprint.from_content("expected")
        )
    ).outcome is SandboxMaterializationStepOutcome.UNAVAILABLE
    source = root / "source.txt"
    source.write_text("data")
    hard = root / "missing.txt"
    os.link(source, hard)
    assert custody.inspect(
        SandboxArtifactInspectionRequest(
            missing, SandboxArtifactFingerprint.from_content("expected")
        )
    ).diagnostic_codes == ("hardlink_unsupported",)


def test_symlink_escape_is_rejected_when_host_permits(tmp_path) -> None:
    reference = OpaqueReference("artifact:symlink")
    root, custody = _custody(tmp_path, reference, "linked.txt")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    try:
        (root / "linked.txt").symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit symlink creation")
    result = custody.inspect(
        SandboxArtifactInspectionRequest(
            reference, SandboxArtifactFingerprint.from_content("expected")
        )
    )
    assert result.diagnostic_codes == ("unsafe_reparse",)


def test_source_change_after_inspection_blocks_materialization(tmp_path) -> None:
    reference = OpaqueReference("artifact:changing")
    root, custody = _custody(tmp_path, reference)
    source = root / "payload.txt"
    source.write_bytes(b"before")
    expected = fingerprint_local_artifact(source)
    assert custody.inspect(
        SandboxArtifactInspectionRequest(reference, expected)
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    source.write_bytes(b"after")
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", custody=custody), Fencing()
    )
    workspace = SandboxWorkspaceId("workspace:changing")
    _prepare(driver, workspace)
    assert _apply(driver, workspace, reference, expected).diagnostic_codes == (
        "source_artifact_unavailable",
    )
    assert not (tmp_path / "workspaces" / "workspace-changing" / "input" / "payload.txt").exists()


def test_stale_fencing_has_zero_destination_effect_and_cleanup_preserves_source(tmp_path) -> None:
    reference = OpaqueReference("artifact:data")
    root, custody = _custody(tmp_path, reference)
    source = root / "payload.txt"
    source.write_bytes(b"data")
    expected = fingerprint_local_artifact(source)
    fencing = Fencing()
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", custody=custody), fencing
    )
    workspace = SandboxWorkspaceId("workspace:fenced")
    _prepare(driver, workspace)
    fencing.decision = SandboxFencingDecision.STALE
    assert _apply(driver, workspace, reference, expected).diagnostic_codes == (
        "fencing_stale",
    )
    destination = tmp_path / "workspaces" / "workspace-fenced" / "input" / "payload.txt"
    assert not destination.exists()
    fencing.decision = SandboxFencingDecision.VALID
    assert driver.cleanup(
        SandboxWorkspaceCleanupRequest(
            workspace, SandboxArtifactFingerprint.from_content("plan")
        )
    ).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert source.read_bytes() == b"data"


def test_executable_and_archive_remain_regular_unexecuted_data(tmp_path) -> None:
    for name in ("payload.ps1", "payload.zip"):
        reference = OpaqueReference("artifact:" + name)
        root, custody = _custody(tmp_path / name.replace(".", "-"), reference, name)
        source = root / name
        source.write_bytes(b"not executable content")
        assert custody.verified_source(reference, fingerprint_local_artifact(source)) == source
        assert not (root / "extracted").exists()
    assert not hasattr(LocalArtifactCustody, "execute")


def test_controlled_journey_and_cross_workspace_binding_rejection(tmp_path) -> None:
    reference = OpaqueReference("artifact:journey")
    root, custody = _custody(tmp_path, reference)
    source = root / "payload.txt"
    source.write_bytes(b"journey")
    fingerprint = fingerprint_local_artifact(source)
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", custody=custody), Fencing()
    )
    workspace = SandboxWorkspaceId("workspace:journey")
    assert _prepare(driver, workspace).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    destination = SandboxLogicalPath.parse("payload.txt", case_sensitive=False)
    operation = SandboxMaterializationOperation(
        1,
        SandboxMaterializationAction.BIND_READONLY_INPUT,
        SandboxFilesystemResource.INPUT,
        destination,
        reference,
        fingerprint,
    )
    request = SandboxMaterializationStepRequest(workspace, operation)
    binding = GovernedArtifactBinding(
        workspace,
        reference,
        fingerprint,
        SandboxFilesystemResource.INPUT,
        destination,
        SandboxMaterializationAction.BIND_READONLY_INPUT,
        OpaqueReference("provenance:journey"),
    )
    adapter = LocalArtifactMaterializationAdapter(custody, driver)
    wrong = SandboxMaterializationStepRequest(
        SandboxWorkspaceId("workspace:other"), operation
    )
    assert adapter.materialize(binding, wrong).diagnostic_codes == (
        "materialization_binding_mismatch",
    )
    assert adapter.materialize(binding, request).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    observed = driver.refingerprint(
        SandboxMaterializedFingerprintRequest(
            workspace, SandboxFilesystemResource.INPUT, destination
        )
    )
    assert observed.observed_fingerprint == fingerprint
    seal_request = SandboxMaterializationStepRequest(
        workspace,
        SandboxMaterializationOperation(
            2,
            SandboxMaterializationAction.SEAL_WORKSPACE,
            None,
            None,
            None,
            None,
        ),
    )
    assert driver.seal(seal_request).outcome is SandboxMaterializationStepOutcome.SUCCEEDED
    assert source.read_bytes() == b"journey"


def test_generation_transfer_during_tree_copy_is_detected_as_partial(tmp_path) -> None:
    reference = OpaqueReference("artifact:transfer")
    root, custody = _custody(tmp_path, reference, "tree")
    source = root / "tree"
    source.mkdir()
    (source / "a.txt").write_text("a")
    (source / "b.txt").write_text("b")
    fingerprint = fingerprint_local_artifact(source)
    workspace = SandboxWorkspaceId("workspace:transfer")
    initial = Fencing()
    driver = _driver(
        WindowsWorkspaceConfig(tmp_path / "workspaces", custody=custody), initial
    )
    _prepare(driver, workspace)
    driver._authority._fencing = TransferringFencing(3)
    result = _apply(driver, workspace, reference, fingerprint, "tree")
    assert result.diagnostic_codes == ("fencing_stale", "materialization_partial")
    destination = tmp_path / "workspaces" / "workspace-transfer" / "input" / "tree"
    assert destination.exists()
    assert len(tuple(destination.iterdir())) < 2
