from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from synapse.intelligence_boundary.models import DataClassification, InformationOwnership
from synapse.private_evals import (
    CaseVersionRevisionConflict,
    CatalogIdempotencyConflict,
    ContentBinding,
    ContentChecksum,
    DatasetBinding,
    DatasetBindingAlreadyExists,
    DatasetBindingId,
    DatasetBindingListFilter,
    DatasetCustodyKind,
    DefinitionStatus,
    EvalCaseId,
    EvalCaseVersion,
    EvalCatalogRuntime,
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalRecordNotFound,
    EvalRevisionConflict,
    EvalSuite,
    EvalSuiteId,
    EvalSuiteVersion,
    EvaluatorId,
    EvaluatorIdentity,
    EvalVersion,
    Fingerprint,
    IdempotencyKey,
    IncompatibleCaseReference,
    IncompatibleDatasetBinding,
    InputKind,
    InvalidSuiteTransition,
    PageRequest,
    Revision,
    SideEffectPolicy,
    StoreCursor,
    StoreOrder,
    StorePage,
    StoreWriteOutcome,
    SuiteAlreadyExists,
    SuiteListFilter,
    SuiteNotFound,
    SuiteRevisionConflict,
    SuiteStatus,
    SuiteVersionAlreadyExists,
    SuiteVersionRevisionConflict,
    UnresolvedCaseReference,
    UtcTimestamp,
    WriteDisposition,
    content_checksum,
)

SUITE_ID = EvalSuiteId("suite.catalog")
CASE_ID = EvalCaseId("case.catalog")
VERSION = EvalVersion("1.0.0")
NOW = UtcTimestamp("2026-07-17T18:00:00+00:00")
LATER = UtcTimestamp("2026-07-17T19:00:00+00:00")
SHA_A = ContentChecksum("a" * 64)
SHA_B = ContentChecksum("b" * 64)


class CatalogStoreFake:
    def __init__(self) -> None:
        self.suites: dict[EvalSuiteId, EvalSuite] = {}
        self.suite_versions: dict[tuple[EvalSuiteId, EvalVersion], EvalSuiteVersion] = {}
        self.cases: dict[tuple[EvalSuiteId, EvalCaseId, EvalVersion], EvalCaseVersion] = {}
        self.bindings: dict[tuple[DatasetBindingId, Revision], DatasetBinding] = {}
        self.revisions: dict[object, Revision] = {}
        self.replays: dict[tuple[str, IdempotencyKey], object] = {}

    def _create(
        self,
        operation: str,
        key: object,
        value: object,
        idempotency_key: IdempotencyKey,
        records: dict[object, object],
        checksum: ContentChecksum,
    ) -> StoreWriteOutcome:
        replay_key = (operation, idempotency_key)
        if replay_key in self.replays:
            if self.replays[replay_key] != value:
                raise EvalIdempotencyConflict()
            return StoreWriteOutcome(operation, None, Revision(1), WriteDisposition.IDEMPOTENT_REPLAY, checksum)
        if key in records:
            raise EvalDuplicateRecord()
        records[key] = value
        self.revisions[key] = Revision(1)
        self.replays[replay_key] = value
        return StoreWriteOutcome(operation, None, Revision(1), WriteDisposition.CREATED, checksum)

    def _update(
        self,
        operation: str,
        key: object,
        value: object,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
        records: dict[object, object],
        checksum: ContentChecksum,
    ) -> StoreWriteOutcome:
        replay_key = (operation, idempotency_key)
        if replay_key in self.replays:
            if self.replays[replay_key] != value:
                raise EvalIdempotencyConflict()
            stored = self.revisions[key]
            return StoreWriteOutcome(operation, expected_revision, stored, WriteDisposition.IDEMPOTENT_REPLAY, checksum)
        actual = self.revisions[key]
        if actual != expected_revision:
            raise EvalRevisionConflict()
        stored = Revision(actual.value + 1)
        records[key] = value
        self.revisions[key] = stored
        self.replays[replay_key] = value
        return StoreWriteOutcome(operation, actual, stored, WriteDisposition.UPDATED, checksum)

    def create_suite(self, suite: EvalSuite, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create("suite", suite.suite_id, suite, idempotency_key, self.suites, content_checksum(suite))

    def get_suite(self, suite_id: EvalSuiteId) -> EvalSuite:
        try:
            return self.suites[suite_id]
        except KeyError as error:
            raise EvalRecordNotFound() from error

    def update_suite(self, suite: EvalSuite, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update("suite-update", suite.suite_id, suite, expected_revision, idempotency_key, self.suites, content_checksum(suite))

    def list_suites(self, filters: SuiteListFilter, page: PageRequest) -> StorePage[EvalSuite]:
        values = [value for value in self.suites.values() if filters.status is None or value.status is filters.status]
        return self._page(values, page, lambda item: item.suite_id.value)

    def save_suite_version(self, version: EvalSuiteVersion, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        key = (version.suite_id, version.version)
        return self._create("suite-version", key, version, idempotency_key, self.suite_versions, version.checksum)

    def get_suite_version(self, suite_id: EvalSuiteId, version: EvalVersion) -> EvalSuiteVersion:
        try:
            return self.suite_versions[(suite_id, version)]
        except KeyError as error:
            raise EvalRecordNotFound() from error

    def update_suite_version_status(self, version: EvalSuiteVersion, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        key = (version.suite_id, version.version)
        return self._update("suite-version-status", key, version, expected_revision, idempotency_key, self.suite_versions, version.checksum)

    def list_suite_versions(self, suite_id: EvalSuiteId, page: PageRequest) -> StorePage[EvalSuiteVersion]:
        values = [value for value in self.suite_versions.values() if value.suite_id == suite_id]
        return self._page(values, page, lambda item: item.version.value)

    def save_case_version(self, case: EvalCaseVersion, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        key = (case.suite_id, case.case_id, case.version)
        return self._create("case", key, case, idempotency_key, self.cases, case.checksum)

    def get_case_version(self, suite_id: EvalSuiteId, case_id: EvalCaseId, version: EvalVersion) -> EvalCaseVersion:
        try:
            return self.cases[(suite_id, case_id, version)]
        except KeyError as error:
            raise EvalRecordNotFound() from error

    def update_case_version_status(self, case: EvalCaseVersion, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        key = (case.suite_id, case.case_id, case.version)
        return self._update("case-status", key, case, expected_revision, idempotency_key, self.cases, case.checksum)

    def list_case_versions(self, suite_id: EvalSuiteId, suite_version: EvalVersion, page: PageRequest) -> StorePage[EvalCaseVersion]:
        referenced = {ref.case_id for ref in self.get_suite_version(suite_id, suite_version).case_references}
        values = [value for value in self.cases.values() if value.suite_id == suite_id and value.case_id in referenced]
        return self._page(values, page, lambda item: f"{item.case_id.value}:{item.version.value}")

    def save_dataset_binding(self, binding: DatasetBinding, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        key = (binding.binding_id, binding.dataset_revision)
        return self._create("binding", key, binding, idempotency_key, self.bindings, binding.checksum)

    def get_dataset_binding(self, binding_id: DatasetBindingId, revision: Revision) -> DatasetBinding:
        try:
            return self.bindings[(binding_id, revision)]
        except KeyError as error:
            raise EvalRecordNotFound() from error

    def list_dataset_bindings(self, filters: DatasetBindingListFilter, page: PageRequest) -> StorePage[DatasetBinding]:
        values = [value for value in self.bindings.values() if filters.asset_id is None or value.asset_id == filters.asset_id]
        return self._page(values, page, lambda item: f"{item.binding_id.value}:{item.dataset_revision.value}")

    @staticmethod
    def _page(values: list[object], page: PageRequest, key: object) -> StorePage:  # type: ignore[type-arg]
        ordered = sorted(values, key=key, reverse=page.order is StoreOrder.ID_DESC)  # type: ignore[arg-type]
        start = int(page.cursor.value) if page.cursor is not None else 0
        items = tuple(ordered[start : start + page.limit])
        next_offset = start + len(items)
        cursor = StoreCursor(str(next_offset)) if next_offset < len(ordered) else None
        return StorePage(items, cursor, len(ordered))


def suite(**changes: object) -> EvalSuite:
    model = EvalSuite(SUITE_ID, "Catalog", "Private eval catalog", InformationOwnership.PROJECT, "project-1", DataClassification.PUBLIC, SuiteStatus.ACTIVE, Revision(1), NOW, NOW)
    return replace(model, **changes)


def case(**changes: object) -> EvalCaseVersion:
    content = ContentBinding(InputKind.INLINE, DataClassification.PUBLIC, inline_value="public fixture")
    model = EvalCaseVersion(SUITE_ID, CASE_ID, VERSION, content, content, EvaluatorIdentity(EvaluatorId("evaluator-1"), VERSION, SHA_A, "exact", SHA_B), Decimal("1"), ("core",), InformationOwnership.PROJECT, DataClassification.PUBLIC, Decimal("10"), SideEffectPolicy.NONE, True, True, DefinitionStatus.DRAFT, SHA_A)
    return replace(model, **changes)


def binding(**changes: object) -> DatasetBinding:
    model = DatasetBinding(DatasetBindingId("binding-1"), "asset-1", "asset://private-evals/dataset-1", Revision(1), SHA_A, SHA_B, 1, DataClassification.PUBLIC, InformationOwnership.PROJECT, "classification:v1", "ownership:v1", "retention:v1", Fingerprint("c" * 64), DatasetCustodyKind.GOVERNED_LOCAL, NOW, SHA_A)
    return replace(model, **changes)


def suite_version(case_model: EvalCaseVersion, binding_model: DatasetBinding, **changes: object) -> EvalSuiteVersion:
    model = EvalSuiteVersion(SUITE_ID, VERSION, (case_model.reference,), (binding_model.reference,), VERSION, 1, 1, Decimal("30"), 0, (), (CASE_ID,), DataClassification.PUBLIC, InformationOwnership.PROJECT, DefinitionStatus.DRAFT, SHA_B)
    return replace(model, **changes)


def configured() -> tuple[EvalCatalogRuntime, CatalogStoreFake, EvalCaseVersion, DatasetBinding, EvalSuiteVersion]:
    store = CatalogStoreFake()
    runtime = EvalCatalogRuntime(store)
    runtime.create_suite(suite(), idempotency_key=IdempotencyKey("suite-create"))
    case_model = runtime.register_case_version(case(), idempotency_key=IdempotencyKey("case-create"))
    binding_model = runtime.register_dataset_binding(binding(), idempotency_key=IdempotencyKey("binding-create"))
    version = runtime.create_suite_version(suite_version(case_model, binding_model), idempotency_key=IdempotencyKey("version-create"))
    return runtime, store, case_model, binding_model, version


def test_suite_create_replay_conflict_update_and_concurrency() -> None:
    store = CatalogStoreFake()
    runtime = EvalCatalogRuntime(store)
    original = suite()
    assert runtime.create_suite(original, idempotency_key=IdempotencyKey("create-1")) == original
    assert runtime.create_suite(original, idempotency_key=IdempotencyKey("create-1")) == original
    with pytest.raises(CatalogIdempotencyConflict):
        runtime.create_suite(replace(original, name="Different"), idempotency_key=IdempotencyKey("create-1"))
    with pytest.raises(SuiteAlreadyExists):
        runtime.create_suite(original, idempotency_key=IdempotencyKey("create-2"))
    updated = replace(original, name="Renamed", revision=Revision(2), updated_at=LATER)
    assert runtime.update_suite(updated, expected_revision=Revision(1), idempotency_key=IdempotencyKey("update-1")) == updated
    stale = replace(updated, description="stale", revision=Revision(3))
    with pytest.raises(SuiteRevisionConflict):
        runtime.update_suite(stale, expected_revision=Revision(1), idempotency_key=IdempotencyKey("update-2"))


def test_suite_rejects_initial_and_metadata_transitions_outside_policy() -> None:
    store = CatalogStoreFake()
    runtime = EvalCatalogRuntime(store)
    with pytest.raises(InvalidSuiteTransition):
        runtime.create_suite(suite(status=SuiteStatus.DEPRECATED), idempotency_key=IdempotencyKey("bad-create"))
    runtime.create_suite(suite(), idempotency_key=IdempotencyKey("create"))
    with pytest.raises(InvalidSuiteTransition):
        runtime.update_suite(suite(owner=InformationOwnership.USER, revision=Revision(2)), expected_revision=Revision(1), idempotency_key=IdempotencyKey("bad-owner"))
    deprecated = suite(status=SuiteStatus.DEPRECATED, revision=Revision(2), updated_at=LATER)
    runtime.update_suite(deprecated, expected_revision=Revision(1), idempotency_key=IdempotencyKey("deprecate"))
    with pytest.raises(InvalidSuiteTransition):
        runtime.update_suite(replace(deprecated, status=SuiteStatus.ACTIVE, revision=Revision(3)), expected_revision=Revision(2), idempotency_key=IdempotencyKey("reactivate"))


def test_case_lifecycle_is_cas_controlled_and_deprecated_case_is_unavailable() -> None:
    runtime, store, case_model, binding_model, version = configured()
    frozen = runtime.freeze_case_version(SUITE_ID, CASE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("case-freeze"))
    assert frozen.status is DefinitionStatus.FROZEN
    assert runtime.freeze_case_version(SUITE_ID, CASE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("case-freeze")) == frozen
    with pytest.raises(CaseVersionRevisionConflict):
        runtime.deprecate_case_version(SUITE_ID, CASE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("case-deprecate-stale"))
    deprecated = runtime.deprecate_case_version(SUITE_ID, CASE_ID, VERSION, expected_revision=Revision(2), idempotency_key=IdempotencyKey("case-deprecate"))
    assert deprecated.status is DefinitionStatus.DEPRECATED
    with pytest.raises(IncompatibleCaseReference):
        runtime.freeze_suite_version(SUITE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("suite-freeze"))
    assert store.suite_versions[(SUITE_ID, VERSION)] == version


def test_suite_version_freeze_deprecate_and_concurrent_cas() -> None:
    runtime, store, case_model, binding_model, _ = configured()
    runtime.freeze_case_version(SUITE_ID, CASE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("case-freeze"))
    frozen = runtime.freeze_suite_version(SUITE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("suite-freeze"))
    assert frozen.status is DefinitionStatus.FROZEN and store.revisions[(SUITE_ID, VERSION)] == Revision(2)
    with pytest.raises(SuiteVersionAlreadyExists):
        runtime.create_suite_version(
            replace(
                suite_version(case_model, binding_model),
                default_retry_count=1,
                checksum=ContentChecksum("d" * 64),
            ),
            idempotency_key=IdempotencyKey("mutate-frozen"),
        )
    assert runtime.freeze_suite_version(SUITE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("suite-freeze")) == frozen
    with pytest.raises(SuiteVersionRevisionConflict):
        runtime.deprecate_suite_version(SUITE_ID, VERSION, expected_revision=Revision(1), idempotency_key=IdempotencyKey("stale-deprecate"))
    deprecated = runtime.deprecate_suite_version(SUITE_ID, VERSION, expected_revision=Revision(2), idempotency_key=IdempotencyKey("deprecate"))
    assert deprecated.status is DefinitionStatus.DEPRECATED
    with pytest.raises(InvalidSuiteTransition):
        runtime.freeze_suite_version(SUITE_ID, VERSION, expected_revision=Revision(3), idempotency_key=IdempotencyKey("refreeze"))


def test_suite_version_requires_exact_resolved_references() -> None:
    runtime, _, case_model, binding_model, _ = configured()
    with pytest.raises(UnresolvedCaseReference):
        runtime.create_suite_version(suite_version(replace(case_model, version=EvalVersion("2.0.0")), binding_model, version=EvalVersion("2.0.0")), idempotency_key=IdempotencyKey("missing-case"))
    bad_binding = replace(binding_model.reference, checksum=SHA_B)
    with pytest.raises(IncompatibleDatasetBinding):
        runtime.create_suite_version(replace(suite_version(case_model, binding_model), version=EvalVersion("2.0.0"), dataset_references=(bad_binding,)), idempotency_key=IdempotencyKey("bad-binding"))


def test_dataset_binding_replay_conflict_resolution_and_no_latest() -> None:
    store = CatalogStoreFake()
    runtime = EvalCatalogRuntime(store)
    model = binding()
    assert runtime.register_dataset_binding(model, idempotency_key=IdempotencyKey("binding")) == model
    assert runtime.register_dataset_binding(model, idempotency_key=IdempotencyKey("binding")) == model
    with pytest.raises(CatalogIdempotencyConflict):
        runtime.register_dataset_binding(replace(model, checksum=SHA_B), idempotency_key=IdempotencyKey("binding"))
    with pytest.raises(DatasetBindingAlreadyExists):
        runtime.register_dataset_binding(model, idempotency_key=IdempotencyKey("binding-other"))
    with pytest.raises(IncompatibleDatasetBinding):
        runtime.register_dataset_binding(
            replace(model, binding_id=DatasetBindingId("desktop-binding"), content_reference="desktop://upload/private"),
            idempotency_key=IdempotencyKey("desktop-binding"),
        )
    assert runtime.resolve_dataset_binding(model.binding_id, Revision(1)) == model
    with pytest.raises(TypeError):
        runtime.resolve_dataset_binding(model.binding_id)  # type: ignore[call-arg]


def test_resolution_listing_filters_pagination_order_and_safe_errors() -> None:
    runtime, _, _, _, version = configured()
    second = suite(suite_id=EvalSuiteId("suite.catalog-2"))
    runtime.create_suite(second, idempotency_key=IdempotencyKey("suite-2"))
    first_page = runtime.list_suites(SuiteListFilter(status=SuiteStatus.ACTIVE), PageRequest(limit=1))
    assert len(first_page.items) == 1 and first_page.next_cursor is not None and first_page.total == 2
    second_page = runtime.list_suites(SuiteListFilter(), PageRequest(first_page.next_cursor, 1, StoreOrder.ID_ASC))
    assert second_page.items[0].suite_id != first_page.items[0].suite_id
    assert runtime.list_suite_versions(SUITE_ID, PageRequest()).items == (version,)
    assert runtime.list_case_versions(SUITE_ID, VERSION, PageRequest()).items[0].case_id == CASE_ID
    assert runtime.list_dataset_bindings(DatasetBindingListFilter(asset_id="asset-1"), PageRequest()).total == 1
    with pytest.raises(SuiteNotFound) as caught:
        runtime.resolve_suite(EvalSuiteId("missing"))
    assert "missing" not in str(caught.value) and "asset://" not in repr(caught.value)
