from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import OperatingProfile, ProcessingBoundary
from synapse.private_evals import (
    ComponentKind,
    ContentChecksum,
    DecodingParameters,
    DefinitionStatus,
    DeterminismMode,
    EnvironmentSnapshot,
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalRecordNotFound,
    EvalRevisionConflict,
    EvalRun,
    EvalRunId,
    EvalRunManifest,
    EvalRunManifestBuilder,
    EvalRunManifestId,
    EvalRunRuntime,
    ExecutionProtocol,
    Fingerprint,
    IdempotencyKey,
    InvalidRunTransition,
    ManifestMismatch,
    ModelProviderSnapshot,
    PageRequest,
    Revision,
    RunCancellationNotAllowed,
    RunCompletionNotAllowed,
    RunLifecycleIdempotencyConflict,
    RunLifecycleReason,
    RunListFilter,
    RunManifestSpec,
    RunNotReady,
    RunProvenance,
    RunRevisionConflict,
    RunStatus,
    SecuritySnapshotRef,
    StorePage,
    StoreWriteOutcome,
    TerminalRunMutation,
    UnresolvedRunReference,
    UtcTimestamp,
    VersionedComponentRef,
    WriteDisposition,
    content_checksum,
)
from synapse.private_evals.errors import DuplicateReference
from test_private_evals_catalog_runtime import CatalogStoreFake, configured

NOW = UtcTimestamp("2026-07-17T18:00:00+00:00")
T1 = UtcTimestamp("2026-07-17T18:01:00+00:00")
T2 = UtcTimestamp("2026-07-17T18:02:00+00:00")
T3 = UtcTimestamp("2026-07-17T18:03:00+00:00")
T4 = UtcTimestamp("2026-07-17T18:04:00+00:00")
SHA_A = ContentChecksum("a" * 64)
SHA_B = ContentChecksum("b" * 64)
REASON = RunLifecycleReason("operator_cancelled", "reason://request/cancel-1")


class RunStoreFake:
    def __init__(self) -> None:
        self.runs: dict[EvalRunId, EvalRun] = {}
        self.manifests: dict[EvalRunManifestId, EvalRunManifest] = {}
        self.revisions: dict[EvalRunId, Revision] = {}
        self.replays: dict[tuple[str, IdempotencyKey], object] = {}

    def _create(
        self,
        operation: str,
        identity: object,
        value: object,
        records: dict,
        key: IdempotencyKey,
        checksum: ContentChecksum,
    ) -> StoreWriteOutcome:
        replay = (operation, key)
        if replay in self.replays:
            if self.replays[replay] != value:
                raise EvalIdempotencyConflict()
            return StoreWriteOutcome(operation, None, Revision(1), WriteDisposition.IDEMPOTENT_REPLAY, checksum)
        if identity in records:
            raise EvalDuplicateRecord()
        records[identity] = value
        self.replays[replay] = value
        return StoreWriteOutcome(operation, None, Revision(1), WriteDisposition.CREATED, checksum)

    def create_run(self, run: EvalRun, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        outcome = self._create("run", run.run_id, run, self.runs, idempotency_key, content_checksum(run))
        self.revisions.setdefault(run.run_id, Revision(1))
        return outcome

    def get_run(self, run_id: EvalRunId) -> EvalRun:
        try:
            return self.runs[run_id]
        except KeyError as error:
            raise EvalRecordNotFound() from error

    def update_run(self, run: EvalRun, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        replay = ("run-update", idempotency_key)
        if replay in self.replays:
            if self.replays[replay] != run:
                raise EvalIdempotencyConflict()
            return StoreWriteOutcome("run", expected_revision, self.revisions[run.run_id], WriteDisposition.IDEMPOTENT_REPLAY, content_checksum(run))
        actual = self.revisions[run.run_id]
        if actual != expected_revision:
            raise EvalRevisionConflict()
        self.runs[run.run_id] = run
        self.revisions[run.run_id] = run.revision
        self.replays[replay] = run
        return StoreWriteOutcome("run", actual, run.revision, WriteDisposition.UPDATED, content_checksum(run))

    def list_runs(self, filters: RunListFilter, page: PageRequest) -> StorePage[EvalRun]:
        values = sorted(self.runs.values(), key=lambda item: item.run_id.value)
        values = [item for item in values if filters.status is None or item.status is filters.status]
        return StorePage(tuple(values[: page.limit]), total=len(values))

    def save_manifest(self, manifest: EvalRunManifest, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create("manifest", manifest.manifest_id, manifest, self.manifests, idempotency_key, manifest.checksum)

    def get_manifest(self, manifest_id: EvalRunManifestId) -> EvalRunManifest:
        try:
            return self.manifests[manifest_id]
        except KeyError as error:
            raise EvalRecordNotFound() from error


def manifest_spec() -> tuple[RunManifestSpec, CatalogStoreFake]:
    catalog_runtime, catalog, case_model, binding_model, version = configured()
    frozen_case = catalog_runtime.freeze_case_version(
        case_model.suite_id,
        case_model.case_id,
        case_model.version,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("case-freeze-run"),
    )
    frozen_version = catalog_runtime.freeze_suite_version(
        version.suite_id,
        version.version,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("suite-freeze-run"),
    )
    spec = RunManifestSpec(
        EvalRunManifestId("manifest-run-1"),
        frozen_version.suite_id,
        frozen_version.version,
        frozen_version.checksum,
        (frozen_case.reference,),
        binding_model.reference,
        frozen_case.evaluator,
        "model",
        Fingerprint("c" * 64),
        ModelProviderSnapshot(
            "provider-local",
            ProcessingBoundary.LOCAL_MODEL,
            "model-1",
            "1.0.0",
            SHA_A,
            DecodingParameters(Decimal("0"), Decimal("1"), 256, 41),
        ),
        (
            VersionedComponentRef(ComponentKind.TOOL, "tool-b", "1", SHA_B),
            VersionedComponentRef(ComponentKind.SKILL, "skill-a", "1", SHA_A),
        ),
        SecuritySnapshotRef(
            OperatingProfile.LOCAL_SOVEREIGN,
            ("policy://z", "policy://a"),
            (SHA_B, SHA_A),
            ("approval://b", "approval://a"),
        ),
        ExecutionProtocol(
            DeterminismMode.DETERMINISTIC,
            1,
            1,
            0,
            Decimal("60"),
            Decimal("30"),
            (41,),
            "mean-v1",
        ),
        EnvironmentSnapshot(
            "Windows",
            "x86_64",
            "3.12",
            "synapse-v3",
            (("z-cap", "2"), ("a-cap", "1")),
        ),
        RunProvenance("actor-1", "project-1", "caller-checksum"),
    )
    return spec, catalog


def prepared() -> tuple[EvalRunRuntime, RunStoreFake, EvalRun]:
    spec, catalog = manifest_spec()
    store = RunStoreFake()
    runtime = EvalRunRuntime(store, catalog)
    manifest = EvalRunManifestBuilder().build(spec)
    run = runtime.prepare_run(
        EvalRunId("run-1"),
        manifest,
        created_at=NOW,
        idempotency_key=IdempotencyKey("prepare-run"),
    )
    return runtime, store, run


def ready() -> tuple[EvalRunRuntime, RunStoreFake, EvalRun]:
    runtime, store, run = prepared()
    run = runtime.begin_validation(
        run.run_id,
        timestamp=T1,
        expected_revision=Revision(1),
        idempotency_key=IdempotencyKey("validate-run"),
    )
    run = runtime.mark_ready(
        run.run_id,
        timestamp=T2,
        expected_revision=Revision(2),
        idempotency_key=IdempotencyKey("ready-run"),
    )
    return runtime, store, run


def test_manifest_builder_is_deterministic_canonical_and_semantically_sensitive() -> None:
    spec, _ = manifest_spec()
    builder = EvalRunManifestBuilder()
    first = builder.build(spec)
    reordered = replace(
        spec,
        component_references=tuple(reversed(spec.component_references)),
        security=replace(
            spec.security,
            policy_references=tuple(reversed(spec.security.policy_references)),
            policy_checksums=tuple(reversed(spec.security.policy_checksums)),
            approval_manifest_references=tuple(reversed(spec.security.approval_manifest_references)),
        ),
        environment=replace(spec.environment, capability_versions=tuple(reversed(spec.environment.capability_versions))),
    )
    assert builder.build(reordered) == first
    changed = replace(spec, execution=replace(spec.execution, retry_count=1))
    assert builder.build(changed).protocol_fingerprint != first.protocol_fingerprint
    assert builder.build(changed).run_fingerprint != first.run_fingerprint
    assert first.manifest_id == spec.manifest_id


def test_manifest_rejects_secrets_duplicates_and_inconsistent_fingerprints() -> None:
    spec, _ = manifest_spec()
    builder = EvalRunManifestBuilder()
    unsafe = replace(spec, security=replace(spec.security, policy_references=("policy://token=secret", "policy://a")))
    with pytest.raises(ManifestMismatch):
        builder.build(unsafe)
    with pytest.raises(DuplicateReference):
        builder.build(replace(spec, component_references=(spec.component_references[0],) * 2))
    manifest = builder.build(spec)
    with pytest.raises(ManifestMismatch):
        builder.validate(replace(manifest, checksum=SHA_A))


def test_prepare_is_valid_idempotent_and_rejects_manifest_conflicts() -> None:
    spec, catalog = manifest_spec()
    store = RunStoreFake()
    runtime = EvalRunRuntime(store, catalog)
    manifest = EvalRunManifestBuilder().build(spec)
    created = runtime.prepare_run(EvalRunId("run-1"), manifest, created_at=NOW, idempotency_key=IdempotencyKey("prepare"))
    replay = runtime.prepare_run(EvalRunId("run-1"), manifest, created_at=NOW, idempotency_key=IdempotencyKey("prepare"))
    assert replay == created and created.status is RunStatus.CREATED
    changed = replace(manifest, checksum=SHA_A)
    with pytest.raises(ManifestMismatch):
        runtime.prepare_run(EvalRunId("run-1"), changed, created_at=NOW, idempotency_key=IdempotencyKey("prepare"))
    other = replace(manifest, manifest_id=EvalRunManifestId("manifest-other"))
    with pytest.raises(RunLifecycleIdempotencyConflict):
        runtime.prepare_run(EvalRunId("run-other"), other, created_at=NOW, idempotency_key=IdempotencyKey("prepare"))


def test_prepare_rejects_missing_or_non_frozen_catalog_references() -> None:
    spec, catalog = manifest_spec()
    manifest = EvalRunManifestBuilder().build(spec)
    runtime = EvalRunRuntime(RunStoreFake(), catalog)
    suite = catalog.suites.pop(spec.suite_id)
    with pytest.raises(UnresolvedRunReference):
        runtime.prepare_run(EvalRunId("missing-suite"), manifest, created_at=NOW, idempotency_key=IdempotencyKey("missing-suite"))
    catalog.suites[spec.suite_id] = suite
    version_key = (spec.suite_id, spec.suite_version)
    catalog.suite_versions[version_key] = replace(
        catalog.suite_versions[version_key], status=DefinitionStatus.DRAFT
    )
    with pytest.raises(ManifestMismatch):
        runtime.prepare_run(EvalRunId("draft-version"), manifest, created_at=NOW, idempotency_key=IdempotencyKey("draft-version"))


def test_readiness_revalidates_frozen_catalog_and_uses_cas() -> None:
    runtime, store, run = prepared()
    validating = runtime.begin_validation(run.run_id, timestamp=T1, expected_revision=Revision(1), idempotency_key=IdempotencyKey("validating"))
    assert validating.status is RunStatus.VALIDATING
    with pytest.raises(RunRevisionConflict):
        runtime.mark_ready(run.run_id, timestamp=T2, expected_revision=Revision(1), idempotency_key=IdempotencyKey("stale-ready"))
    ready_run = runtime.mark_ready(run.run_id, timestamp=T2, expected_revision=Revision(2), idempotency_key=IdempotencyKey("ready"))
    assert ready_run.status is RunStatus.READY and store.revisions[run.run_id] == Revision(3)
    assert runtime.mark_ready(run.run_id, timestamp=T2, expected_revision=Revision(2), idempotency_key=IdempotencyKey("ready")) == ready_run


def test_blocked_invalid_and_policy_denied_are_distinct_safe_states() -> None:
    runtime, _, run = prepared()
    validating = runtime.begin_validation(run.run_id, timestamp=T1, expected_revision=Revision(1), idempotency_key=IdempotencyKey("validate"))
    blocked = runtime.block_run(run.run_id, RunLifecycleReason("approval_pending", "condition://approval/1"), timestamp=T2, expected_revision=validating.revision, idempotency_key=IdempotencyKey("block"))
    assert blocked.status is RunStatus.BLOCKED and "approval_pending" in (blocked.finalization_reference or "")
    resumed = runtime.begin_validation(run.run_id, timestamp=T3, expected_revision=blocked.revision, idempotency_key=IdempotencyKey("resume"))
    invalid = runtime.invalidate_run(run.run_id, RunLifecycleReason("checksum_mismatch", "invalid://manifest/checksum"), timestamp=T4, expected_revision=resumed.revision, idempotency_key=IdempotencyKey("invalid"))
    assert invalid.status is RunStatus.INVALID
    with pytest.raises(TerminalRunMutation):
        runtime.begin_validation(run.run_id, timestamp=T4, expected_revision=invalid.revision, idempotency_key=IdempotencyKey("mutate-invalid"))


def test_running_partial_failure_requires_immutable_finalization() -> None:
    runtime, _, ready_run = ready()
    running = runtime.start_run(ready_run.run_id, timestamp=T3, expected_revision=ready_run.revision, idempotency_key=IdempotencyKey("start"))
    assert running.status is RunStatus.RUNNING
    assert runtime.start_run(ready_run.run_id, timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("start")) == running
    with pytest.raises(RunCompletionNotAllowed):
        runtime.mark_partially_failed(running.run_id, RunLifecycleReason("infrastructure_exhausted", "failure://execution/summary-1"), accepted_result_count=1, failed_execution_count=1, timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("partial"))
    with pytest.raises(RunCancellationNotAllowed):
        runtime.cancel_run(running.run_id, REASON, timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("running-cancel"))


def test_cancel_is_idempotent_and_start_requires_ready() -> None:
    runtime, _, ready_run = ready()
    cancelled = runtime.cancel_run(ready_run.run_id, REASON, timestamp=T3, expected_revision=ready_run.revision, idempotency_key=IdempotencyKey("cancel"))
    assert cancelled.status is RunStatus.CANCELLED
    assert runtime.cancel_run(ready_run.run_id, REASON, timestamp=T4, expected_revision=cancelled.revision, idempotency_key=IdempotencyKey("cancel")) == cancelled
    with pytest.raises(TerminalRunMutation):
        runtime.start_run(ready_run.run_id, timestamp=T4, expected_revision=cancelled.revision, idempotency_key=IdempotencyKey("start-late"))
    fresh, _, created = prepared()
    with pytest.raises(RunNotReady):
        fresh.start_run(created.run_id, timestamp=T1, expected_revision=Revision(1), idempotency_key=IdempotencyKey("start-early"))


def test_running_failure_requires_finalization_and_recovery_is_read_only() -> None:
    runtime, _, ready_run = ready()
    running = runtime.start_run(ready_run.run_id, timestamp=T3, expected_revision=ready_run.revision, idempotency_key=IdempotencyKey("start"))
    with pytest.raises(RunCompletionNotAllowed):
        runtime.fail_run(running.run_id, RunLifecycleReason("run_infrastructure_failure", "failure://run/final-1"), failed_execution_count=1, timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("fail"))
    assert runtime.get_run(running.run_id) == running
    with pytest.raises(RunCompletionNotAllowed):
        runtime.complete_run(running.run_id)
    assert runtime.list_runs(RunListFilter(status=RunStatus.FAILED), PageRequest()).items == ()


def test_running_invalid_and_policy_denied_require_finalization() -> None:
    runtime, _, ready_run = ready()
    running = runtime.start_run(ready_run.run_id, timestamp=T3, expected_revision=ready_run.revision, idempotency_key=IdempotencyKey("start-terminal-authority"))
    with pytest.raises(RunCompletionNotAllowed):
        runtime.invalidate_run(running.run_id, RunLifecycleReason("checksum_mismatch", "invalid://result/checksum"), timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("running-invalid"))
    with pytest.raises(RunCompletionNotAllowed):
        runtime.mark_policy_denied(running.run_id, RunLifecycleReason("policy_denied", "denial://policy/decision-2"), timestamp=T4, expected_revision=running.revision, idempotency_key=IdempotencyKey("running-denied"))


def test_policy_denied_is_only_a_caller_supplied_terminal_representation() -> None:
    runtime, _, run = prepared()
    validating = runtime.begin_validation(run.run_id, timestamp=T1, expected_revision=Revision(1), idempotency_key=IdempotencyKey("validate-policy"))
    denied = runtime.mark_policy_denied(validating.run_id, RunLifecycleReason("policy_denied", "denial://policy/decision-1"), timestamp=T2, expected_revision=validating.revision, idempotency_key=IdempotencyKey("deny"))
    assert denied.status is RunStatus.POLICY_DENIED
    with pytest.raises(TerminalRunMutation):
        runtime.start_run(denied.run_id, timestamp=T3, expected_revision=denied.revision, idempotency_key=IdempotencyKey("start-denied"))


def test_reason_and_timestamp_validation_never_echo_sensitive_input() -> None:
    with pytest.raises(InvalidRunTransition) as caught:
        RunLifecycleReason("bad reason", "reason://token=must-not-leak")
    assert "must-not-leak" not in str(caught.value)
    runtime, _, run = prepared()
    with pytest.raises(InvalidRunTransition):
        runtime.begin_validation(run.run_id, timestamp=UtcTimestamp("2026-07-17T17:00:00+00:00"), expected_revision=Revision(1), idempotency_key=IdempotencyKey("past"))
