from __future__ import annotations

from dataclasses import replace
from typing import NoReturn

from .catalog import DatasetBinding, EvalCaseVersion, EvalSuite, EvalSuiteVersion
from .catalog_errors import (
    CaseVersionAlreadyExists,
    CaseVersionNotFound,
    CaseVersionRevisionConflict,
    CatalogIdempotencyConflict,
    CatalogIntegrityConflict,
    CatalogQueryInvalid,
    CatalogUnavailable,
    DatasetBindingAlreadyExists,
    DatasetBindingNotFound,
    EvalCatalogError,
    IncompatibleCaseReference,
    IncompatibleDatasetBinding,
    InvalidCaseTransition,
    InvalidSuiteTransition,
    SuiteAlreadyExists,
    SuiteNotFound,
    SuiteRevisionConflict,
    SuiteVersionAlreadyExists,
    SuiteVersionNotFound,
    SuiteVersionRevisionConflict,
    UnresolvedCaseReference,
)
from .contracts import EvalCatalogStore
from .states import DatasetCustodyKind, DefinitionStatus, SuiteStatus
from .store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidCursor,
    EvalInvalidStoreQuery,
    EvalRecordNotFound,
    EvalRevisionConflict,
    EvalStoreError,
    EvalStoreUnavailable,
)
from .store_models import (
    DatasetBindingListFilter,
    IdempotencyKey,
    PageRequest,
    StorePage,
    SuiteListFilter,
)
from .values import DatasetBindingId, EvalCaseId, EvalSuiteId, EvalVersion, Revision


class EvalCatalogRuntime:
    """Coordinates the versioned definition catalog through its domain-owned port."""

    def __init__(self, store: EvalCatalogStore) -> None:
        self._store = store

    def create_suite(self, suite: EvalSuite, *, idempotency_key: IdempotencyKey) -> EvalSuite:
        if suite.status is not SuiteStatus.ACTIVE or suite.revision != Revision(1):
            raise InvalidSuiteTransition()
        try:
            self._store.create_suite(suite, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=SuiteAlreadyExists)
        return suite

    def update_suite(
        self,
        suite: EvalSuite,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalSuite:
        current = self.resolve_suite(suite.suite_id)
        if suite != current:
            immutable_changed = (
                suite.suite_id != current.suite_id
                or suite.owner != current.owner
                or suite.project_id != current.project_id
                or suite.classification != current.classification
                or suite.created_at != current.created_at
            )
            if immutable_changed or suite.revision.value != current.revision.value + 1:
                raise InvalidSuiteTransition()
            allowed = {
                SuiteStatus.ACTIVE: {SuiteStatus.ACTIVE, SuiteStatus.DEPRECATED},
                SuiteStatus.DEPRECATED: {SuiteStatus.DEPRECATED, SuiteStatus.ARCHIVED},
                SuiteStatus.ARCHIVED: {SuiteStatus.ARCHIVED},
            }
            if suite.status not in allowed[current.status]:
                raise InvalidSuiteTransition()
        try:
            self._store.update_suite(
                suite,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=SuiteRevisionConflict)
        return suite

    def create_suite_version(
        self, version: EvalSuiteVersion, *, idempotency_key: IdempotencyKey
    ) -> EvalSuiteVersion:
        suite = self.resolve_suite(version.suite_id)
        if suite.status is not SuiteStatus.ACTIVE or version.status is not DefinitionStatus.DRAFT:
            raise InvalidSuiteTransition()
        self._validate_suite_snapshots(suite, version)
        self._validate_references(version, require_frozen=False)
        try:
            self._store.save_suite_version(version, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=SuiteVersionAlreadyExists)
        return version

    def freeze_suite_version(
        self,
        suite_id: EvalSuiteId,
        version: EvalVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalSuiteVersion:
        current = self.resolve_suite_version(suite_id, version)
        if current.status is DefinitionStatus.FROZEN:
            return current
        if current.status is not DefinitionStatus.DRAFT:
            raise InvalidSuiteTransition()
        suite = self.resolve_suite(suite_id)
        if suite.status is not SuiteStatus.ACTIVE:
            raise InvalidSuiteTransition()
        self._validate_suite_snapshots(suite, current)
        self._validate_references(current, require_frozen=True)
        frozen = replace(current, status=DefinitionStatus.FROZEN)
        try:
            self._store.update_suite_version_status(
                frozen,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=SuiteVersionRevisionConflict)
        return frozen

    def deprecate_suite_version(
        self,
        suite_id: EvalSuiteId,
        version: EvalVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalSuiteVersion:
        current = self.resolve_suite_version(suite_id, version)
        if current.status is DefinitionStatus.DEPRECATED:
            return current
        if current.status is not DefinitionStatus.FROZEN:
            raise InvalidSuiteTransition()
        deprecated = replace(current, status=DefinitionStatus.DEPRECATED)
        try:
            self._store.update_suite_version_status(
                deprecated,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=SuiteVersionRevisionConflict)
        return deprecated

    def register_case_version(
        self, case: EvalCaseVersion, *, idempotency_key: IdempotencyKey
    ) -> EvalCaseVersion:
        suite = self.resolve_suite(case.suite_id)
        if (
            suite.status is not SuiteStatus.ACTIVE
            or case.status is not DefinitionStatus.DRAFT
            or case.owner != suite.owner
            or case.classification != suite.classification
        ):
            raise IncompatibleCaseReference()
        try:
            self._store.save_case_version(case, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=CaseVersionAlreadyExists)
        return case

    def freeze_case_version(
        self,
        suite_id: EvalSuiteId,
        case_id: EvalCaseId,
        version: EvalVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalCaseVersion:
        current = self.resolve_case_version(suite_id, case_id, version)
        if current.status is DefinitionStatus.FROZEN:
            return current
        if current.status is not DefinitionStatus.DRAFT:
            raise InvalidCaseTransition()
        suite = self.resolve_suite(suite_id)
        if (
            suite.status is not SuiteStatus.ACTIVE
            or current.owner != suite.owner
            or current.classification != suite.classification
        ):
            raise InvalidCaseTransition()
        frozen = replace(current, status=DefinitionStatus.FROZEN)
        try:
            self._store.update_case_version_status(
                frozen,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=CaseVersionRevisionConflict)
        return frozen

    def deprecate_case_version(
        self,
        suite_id: EvalSuiteId,
        case_id: EvalCaseId,
        version: EvalVersion,
        *,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalCaseVersion:
        current = self.resolve_case_version(suite_id, case_id, version)
        if current.status is DefinitionStatus.DEPRECATED:
            return current
        if current.status is not DefinitionStatus.FROZEN:
            raise InvalidCaseTransition()
        deprecated = replace(current, status=DefinitionStatus.DEPRECATED)
        try:
            self._store.update_case_version_status(
                deprecated,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=CaseVersionRevisionConflict)
        return deprecated

    def register_dataset_binding(
        self, binding: DatasetBinding, *, idempotency_key: IdempotencyKey
    ) -> DatasetBinding:
        reference_scheme = binding.content_reference.split(":", 1)[0].casefold()
        if (
            binding.custody_kind is not DatasetCustodyKind.GOVERNED_LOCAL
            or reference_scheme.startswith("desktop")
        ):
            raise IncompatibleDatasetBinding()
        try:
            self._store.save_dataset_binding(binding, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=DatasetBindingAlreadyExists)
        return binding

    def resolve_suite(self, suite_id: EvalSuiteId) -> EvalSuite:
        try:
            return self._store.get_suite(suite_id)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=SuiteNotFound)

    def resolve_suite_version(
        self, suite_id: EvalSuiteId, version: EvalVersion
    ) -> EvalSuiteVersion:
        try:
            return self._store.get_suite_version(suite_id, version)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=SuiteVersionNotFound)

    def resolve_case_version(
        self, suite_id: EvalSuiteId, case_id: EvalCaseId, version: EvalVersion
    ) -> EvalCaseVersion:
        try:
            return self._store.get_case_version(suite_id, case_id, version)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=CaseVersionNotFound)

    def resolve_dataset_binding(
        self, binding_id: DatasetBindingId, revision: Revision
    ) -> DatasetBinding:
        try:
            return self._store.get_dataset_binding(binding_id, revision)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=DatasetBindingNotFound)

    def list_suites(
        self, filters: SuiteListFilter, page: PageRequest
    ) -> StorePage[EvalSuite]:
        try:
            return self._store.list_suites(filters, page)
        except EvalStoreError as error:
            self._raise_store_error(error)

    def list_suite_versions(
        self, suite_id: EvalSuiteId, page: PageRequest
    ) -> StorePage[EvalSuiteVersion]:
        try:
            return self._store.list_suite_versions(suite_id, page)
        except EvalStoreError as error:
            self._raise_store_error(error)

    def list_case_versions(
        self, suite_id: EvalSuiteId, suite_version: EvalVersion, page: PageRequest
    ) -> StorePage[EvalCaseVersion]:
        try:
            return self._store.list_case_versions(suite_id, suite_version, page)
        except EvalStoreError as error:
            self._raise_store_error(error)

    def list_dataset_bindings(
        self, filters: DatasetBindingListFilter, page: PageRequest
    ) -> StorePage[DatasetBinding]:
        try:
            return self._store.list_dataset_bindings(filters, page)
        except EvalStoreError as error:
            self._raise_store_error(error)

    def _validate_suite_snapshots(
        self, suite: EvalSuite, version: EvalSuiteVersion
    ) -> None:
        if version.owner != suite.owner or version.classification != suite.classification:
            raise IncompatibleCaseReference()

    def _validate_references(
        self, version: EvalSuiteVersion, *, require_frozen: bool
    ) -> None:
        for case_reference in version.case_references:
            try:
                case = self.resolve_case_version(
                    case_reference.suite_id,
                    case_reference.case_id,
                    case_reference.version,
                )
            except CaseVersionNotFound as error:
                raise UnresolvedCaseReference() from error
            if (
                case.suite_id != version.suite_id
                or case.checksum != case_reference.checksum
                or case.owner != version.owner
                or case.classification != version.classification
                or case.status is DefinitionStatus.DEPRECATED
                or (require_frozen and case.status is not DefinitionStatus.FROZEN)
            ):
                raise IncompatibleCaseReference()
        for dataset_reference in version.dataset_references:
            try:
                binding = self.resolve_dataset_binding(
                    dataset_reference.binding_id, dataset_reference.revision
                )
            except DatasetBindingNotFound as error:
                raise IncompatibleDatasetBinding() from error
            if (
                binding.checksum != dataset_reference.checksum
                or binding.owner != version.owner
                or binding.classification != version.classification
            ):
                raise IncompatibleDatasetBinding()

    @staticmethod
    def _raise_store_error(
        error: EvalStoreError,
        *,
        not_found: type[EvalCatalogError] | None = None,
        duplicate: type[EvalCatalogError] | None = None,
        revision: type[EvalCatalogError] | None = None,
    ) -> NoReturn:
        if isinstance(error, EvalRecordNotFound) and not_found is not None:
            raise not_found() from error
        if isinstance(error, EvalDuplicateRecord) and duplicate is not None:
            raise duplicate() from error
        if isinstance(error, EvalRevisionConflict) and revision is not None:
            raise revision() from error
        if isinstance(error, EvalIdempotencyConflict):
            raise CatalogIdempotencyConflict() from error
        if isinstance(error, EvalIntegrityConflict):
            raise CatalogIntegrityConflict() from error
        if isinstance(error, (EvalInvalidCursor, EvalInvalidStoreQuery)):
            raise CatalogQueryInvalid() from error
        if isinstance(error, EvalStoreUnavailable):
            raise CatalogUnavailable() from error
        raise CatalogIntegrityConflict() from error
