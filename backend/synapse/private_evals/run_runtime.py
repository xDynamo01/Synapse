from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import NoReturn

from .canonical import canonical_json, content_checksum, fingerprint
from .catalog import DatasetBindingRef, EvalCaseVersionRef, EvaluatorIdentity
from .contracts import EvalCatalogStore, EvalRunStore
from .errors import PrivateEvalDomainError
from .run_errors import (
    EvalRunLifecycleError,
    InvalidRunTransition,
    ManifestAlreadyExists,
    ManifestMismatch,
    ManifestNotFound,
    RunAlreadyExists,
    RunCancellationNotAllowed,
    RunCompletionNotAllowed,
    RunLifecycleIdempotencyConflict,
    RunLifecycleIntegrityConflict,
    RunLifecycleQueryInvalid,
    RunLifecycleUnavailable,
    RunNotFound,
    RunNotReady,
    RunRevisionConflict,
    TerminalRunMutation,
    UnresolvedRunReference,
)
from .runs import (
    EnvironmentSnapshot,
    EvalRun,
    EvalRunManifest,
    ExecutionProtocol,
    ModelProviderSnapshot,
    RunProvenance,
    SecuritySnapshotRef,
    VersionedComponentRef,
)
from .states import DefinitionStatus, RunStatus, SuiteStatus
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
from .store_models import IdempotencyKey, PageRequest, RunListFilter, StorePage
from .values import (
    ContentChecksum,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    Revision,
    UtcTimestamp,
)

_SENSITIVE_VALUE = re.compile(
    r"(?i)\b(?:api[_-]?key|authorization|password|private[_-]?key|secret|token)\s*[:=]"
)
_SAFE_REASON_CODE = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SAFE_REFERENCE = re.compile(r"^[a-z][a-z0-9+.-]*://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$")


@dataclass(frozen=True)
class RunLifecycleReason:
    code: str
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not _SAFE_REASON_CODE.fullmatch(self.code):
            raise InvalidRunTransition()
        if not isinstance(self.reference, str) or not _SAFE_REFERENCE.fullmatch(self.reference):
            raise InvalidRunTransition()
        if _SENSITIVE_VALUE.search(self.reference):
            raise InvalidRunTransition()

    @property
    def record_reference(self) -> str:
        separator = "&" if "?" in self.reference else "?"
        return f"{self.reference}{separator}reason={self.code}"


@dataclass(frozen=True)
class RunManifestSpec:
    manifest_id: EvalRunManifestId
    suite_id: EvalSuiteId
    suite_version: EvalVersion
    suite_checksum: ContentChecksum
    case_references: tuple[EvalCaseVersionRef, ...]
    dataset_binding: DatasetBindingRef
    evaluator: EvaluatorIdentity
    subject_kind: str
    source_fingerprint: Fingerprint
    model_provider: ModelProviderSnapshot | None
    component_references: tuple[VersionedComponentRef, ...]
    security: SecuritySnapshotRef
    execution: ExecutionProtocol
    environment: EnvironmentSnapshot
    provenance: RunProvenance


class EvalRunManifestBuilder:
    """Builds canonical, secret-free reproducibility identities without external I/O."""

    def build(self, spec: RunManifestSpec) -> EvalRunManifest:
        normalized = self._normalize(spec)
        protocol_payload = {
            "suite_id": normalized.suite_id,
            "suite_version": normalized.suite_version,
            "suite_checksum": normalized.suite_checksum,
            "case_references": normalized.case_references,
            "dataset_binding": normalized.dataset_binding,
            "evaluator": normalized.evaluator,
            "security": normalized.security,
            "execution": normalized.execution,
        }
        subject_payload = {
            "subject_kind": normalized.subject_kind.casefold(),
            "source_fingerprint": normalized.source_fingerprint,
            "model_provider": normalized.model_provider,
            "component_references": normalized.component_references,
        }
        environment_payload = {"environment": normalized.environment}
        provenance_payload = {"provenance": normalized.provenance}
        self._reject_sensitive(
            (protocol_payload, subject_payload, environment_payload, provenance_payload)
        )
        protocol_fingerprint = fingerprint(protocol_payload)
        subject_fingerprint = fingerprint(subject_payload)
        environment_fingerprint = fingerprint(environment_payload)
        run_fingerprint = fingerprint(
            {
                "protocol_fingerprint": protocol_fingerprint,
                "subject_fingerprint": subject_fingerprint,
            }
        )
        checksum = content_checksum(
            {
                "protocol": protocol_payload,
                "subject": subject_payload,
                "environment": environment_payload,
                "provenance": provenance_payload,
                "run_fingerprint": run_fingerprint,
            }
        )
        return EvalRunManifest(
            manifest_id=normalized.manifest_id,
            suite_id=normalized.suite_id,
            suite_version=normalized.suite_version,
            suite_checksum=normalized.suite_checksum,
            case_references=normalized.case_references,
            dataset_binding=normalized.dataset_binding,
            evaluator=normalized.evaluator,
            subject_kind=normalized.subject_kind.casefold(),
            source_fingerprint=normalized.source_fingerprint,
            model_provider=normalized.model_provider,
            component_references=normalized.component_references,
            security=normalized.security,
            execution=normalized.execution,
            environment=normalized.environment,
            provenance=normalized.provenance,
            protocol_fingerprint=protocol_fingerprint,
            subject_fingerprint=subject_fingerprint,
            run_fingerprint=run_fingerprint,
            environment_fingerprint=environment_fingerprint,
            checksum=checksum,
        )

    def validate(self, manifest: EvalRunManifest) -> None:
        rebuilt = self.build(
            RunManifestSpec(
                manifest.manifest_id,
                manifest.suite_id,
                manifest.suite_version,
                manifest.suite_checksum,
                manifest.case_references,
                manifest.dataset_binding,
                manifest.evaluator,
                manifest.subject_kind,
                manifest.source_fingerprint,
                manifest.model_provider,
                manifest.component_references,
                manifest.security,
                manifest.execution,
                manifest.environment,
                manifest.provenance,
            )
        )
        if rebuilt != manifest:
            raise ManifestMismatch()

    @staticmethod
    def _normalize(spec: RunManifestSpec) -> RunManifestSpec:
        components = tuple(
            sorted(
                spec.component_references,
                key=lambda item: (
                    item.kind.value,
                    item.component_id,
                    item.version,
                    item.checksum.value,
                ),
            )
        )
        policy_pairs = sorted(
            zip(spec.security.policy_references, spec.security.policy_checksums, strict=True),
            key=lambda item: item[0],
        )
        security = replace(
            spec.security,
            policy_references=tuple(item[0] for item in policy_pairs),
            policy_checksums=tuple(item[1] for item in policy_pairs),
            approval_manifest_references=tuple(
                sorted(spec.security.approval_manifest_references)
            ),
        )
        environment = replace(
            spec.environment,
            capability_versions=tuple(sorted(spec.environment.capability_versions)),
        )
        provenance = replace(
            spec.provenance,
            prior_manifest_references=tuple(
                sorted(
                    spec.provenance.prior_manifest_references,
                    key=lambda item: item.value,
                )
            ),
        )
        return replace(
            spec,
            component_references=components,
            security=security,
            environment=environment,
            provenance=provenance,
        )

    @staticmethod
    def _reject_sensitive(payloads: tuple[object, ...]) -> None:
        if _SENSITIVE_VALUE.search(canonical_json(payloads)):
            raise ManifestMismatch()


class EvalRunRuntime:
    """Coordinates preparation and local lifecycle; it never executes eval cases."""

    _TERMINAL = {
        RunStatus.PARTIALLY_FAILED,
        RunStatus.COMPLETED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.INVALID,
        RunStatus.POLICY_DENIED,
    }
    _ALLOWED = {
        RunStatus.CREATED: {RunStatus.VALIDATING},
        RunStatus.VALIDATING: {
            RunStatus.READY,
            RunStatus.BLOCKED,
            RunStatus.INVALID,
            RunStatus.POLICY_DENIED,
        },
        RunStatus.BLOCKED: {RunStatus.VALIDATING, RunStatus.CANCELLED},
        RunStatus.READY: {RunStatus.RUNNING, RunStatus.CANCELLED},
        RunStatus.RUNNING: {
            RunStatus.PARTIALLY_FAILED,
            RunStatus.COMPLETED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
            RunStatus.INVALID,
            RunStatus.POLICY_DENIED,
        },
    }

    def __init__(
        self,
        run_store: EvalRunStore,
        catalog_store: EvalCatalogStore,
        manifest_builder: EvalRunManifestBuilder | None = None,
    ) -> None:
        self._runs = run_store
        self._catalog = catalog_store
        self._builder = manifest_builder or EvalRunManifestBuilder()

    def prepare_run(
        self,
        run_id: EvalRunId,
        manifest: EvalRunManifest,
        *,
        created_at: UtcTimestamp,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        self._builder.validate(manifest)
        self._validate_catalog(manifest)
        run = EvalRun(
            run_id,
            manifest.suite_id,
            manifest.suite_version,
            RunStatus.CREATED,
            Revision(1),
            created_at,
            created_at,
            manifest.manifest_id,
        )
        try:
            self._runs.save_manifest(manifest, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=ManifestAlreadyExists)
        try:
            self._runs.create_run(run, idempotency_key=idempotency_key)
        except EvalStoreError as error:
            self._raise_store_error(error, duplicate=RunAlreadyExists)
        return run

    def begin_validation(
        self,
        run_id: EvalRunId,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        return self._transition(
            run_id,
            RunStatus.VALIDATING,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def mark_ready(
        self,
        run_id: EvalRunId,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        current = self.get_run(run_id)
        if current.status is RunStatus.READY:
            return current
        if current.status is not RunStatus.VALIDATING:
            raise RunNotReady()
        manifest = self.get_manifest(current.manifest_id)
        self._builder.validate(manifest)
        self._validate_catalog(manifest)
        return self._transition_loaded(
            current,
            RunStatus.READY,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def block_run(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        return self._transition(
            run_id,
            RunStatus.BLOCKED,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=reason.record_reference,
        )

    def invalidate_run(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        current = self.get_run(run_id)
        if current.status is RunStatus.RUNNING:
            raise RunCompletionNotAllowed()
        return self._transition_loaded(
            current,
            RunStatus.INVALID,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=reason.record_reference,
        )

    def start_run(
        self,
        run_id: EvalRunId,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        current = self.get_run(run_id)
        if current.status is RunStatus.RUNNING:
            return current
        if current.status is not RunStatus.READY:
            if current.status in self._TERMINAL:
                raise TerminalRunMutation()
            raise RunNotReady()
        return self._transition_loaded(
            current,
            RunStatus.RUNNING,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
        )

    def cancel_run(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        current = self.get_run(run_id)
        if current.status is RunStatus.CANCELLED:
            return current
        if current.status is RunStatus.RUNNING:
            raise RunCancellationNotAllowed()
        if current.status not in {RunStatus.BLOCKED, RunStatus.READY}:
            if current.status in self._TERMINAL:
                raise TerminalRunMutation()
            raise RunCancellationNotAllowed()
        return self._transition_loaded(
            current,
            RunStatus.CANCELLED,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=reason.record_reference,
        )

    def mark_partially_failed(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        accepted_result_count: int,
        failed_execution_count: int,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        """Post-execution terminal transitions require immutable finalization."""
        self.get_run(run_id)
        raise RunCompletionNotAllowed()

    def fail_run(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        failed_execution_count: int,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        """Post-execution terminal transitions require immutable finalization."""
        self.get_run(run_id)
        raise RunCompletionNotAllowed()

    def mark_policy_denied(
        self,
        run_id: EvalRunId,
        reason: RunLifecycleReason,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        current = self.get_run(run_id)
        if current.status is RunStatus.RUNNING:
            raise RunCompletionNotAllowed()
        return self._transition_loaded(
            current,
            RunStatus.POLICY_DENIED,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=reason.record_reference,
        )

    def complete_run(self, run_id: EvalRunId) -> NoReturn:
        """Completion is reserved until immutable execution evidence exists."""
        self.get_run(run_id)
        raise RunCompletionNotAllowed()

    def apply_finalization(
        self,
        run_id: EvalRunId,
        target: RunStatus,
        finalization_reference: str,
        finalization_fingerprint: Fingerprint,
        *,
        accepted_result_count: int,
        failed_execution_count: int,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
    ) -> EvalRun:
        """Apply a previously persisted immutable finalization using run CAS."""
        reference_match = (
            re.fullmatch(
                r"private-evals-finalization:([^?]+)\?id=([^&]+)&fingerprint=([0-9a-f]{64})",
                finalization_reference,
            )
            if isinstance(finalization_reference, str)
            else None
        )
        try:
            reference_id = (
                EvalRunFinalizationId(reference_match.group(2))
                if reference_match is not None
                else None
            )
        except PrivateEvalDomainError:
            reference_id = None
        if (
            target not in self._TERMINAL
            or target is RunStatus.BLOCKED
            or not isinstance(finalization_fingerprint, Fingerprint)
            or reference_id is None
            or reference_match is None
            or reference_match.group(1) != run_id.value
            or reference_match.group(3) != finalization_fingerprint.value
            or isinstance(accepted_result_count, bool)
            or not isinstance(accepted_result_count, int)
            or accepted_result_count < 0
            or isinstance(failed_execution_count, bool)
            or not isinstance(failed_execution_count, int)
            or failed_execution_count < 0
        ):
            raise InvalidRunTransition()
        current = self.get_run(run_id)
        if current.status is target and current.finalization_reference == finalization_reference:
            return current
        if current.status in self._TERMINAL:
            raise TerminalRunMutation()
        return self._transition_loaded(
            current,
            target,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=finalization_reference,
            accepted_result_count=accepted_result_count,
            failed_execution_count=failed_execution_count,
        )

    def get_run(self, run_id: EvalRunId) -> EvalRun:
        try:
            return self._runs.get_run(run_id)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=RunNotFound)

    def get_manifest(self, manifest_id: EvalRunManifestId | None) -> EvalRunManifest:
        if manifest_id is None:
            raise ManifestNotFound()
        try:
            return self._runs.get_manifest(manifest_id)
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=ManifestNotFound)

    def list_runs(
        self, filters: RunListFilter, page: PageRequest
    ) -> StorePage[EvalRun]:
        try:
            return self._runs.list_runs(filters, page)
        except EvalStoreError as error:
            self._raise_store_error(error)

    def _validate_catalog(self, manifest: EvalRunManifest) -> None:
        try:
            suite = self._catalog.get_suite(manifest.suite_id)
            version = self._catalog.get_suite_version(
                manifest.suite_id, manifest.suite_version
            )
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=UnresolvedRunReference)
        if (
            suite.status is not SuiteStatus.ACTIVE
            or version.status is not DefinitionStatus.FROZEN
            or version.checksum != manifest.suite_checksum
            or version.case_references != manifest.case_references
            or manifest.dataset_binding not in version.dataset_references
        ):
            raise ManifestMismatch()
        for reference in manifest.case_references:
            try:
                case = self._catalog.get_case_version(
                    reference.suite_id, reference.case_id, reference.version
                )
            except EvalStoreError as error:
                self._raise_store_error(error, not_found=UnresolvedRunReference)
            if (
                case.status is not DefinitionStatus.FROZEN
                or case.checksum != reference.checksum
                or case.evaluator != manifest.evaluator
                or case.owner != version.owner
                or case.classification != version.classification
            ):
                raise ManifestMismatch()
        try:
            binding = self._catalog.get_dataset_binding(
                manifest.dataset_binding.binding_id,
                manifest.dataset_binding.revision,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, not_found=UnresolvedRunReference)
        if (
            binding.checksum != manifest.dataset_binding.checksum
            or binding.owner != version.owner
            or binding.classification != version.classification
        ):
            raise ManifestMismatch()

    def _transition(
        self,
        run_id: EvalRunId,
        target: RunStatus,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
        reference: str | None = None,
        accepted_result_count: int | None = None,
        failed_execution_count: int | None = None,
    ) -> EvalRun:
        return self._transition_loaded(
            self.get_run(run_id),
            target,
            timestamp=timestamp,
            expected_revision=expected_revision,
            idempotency_key=idempotency_key,
            reference=reference,
            accepted_result_count=accepted_result_count,
            failed_execution_count=failed_execution_count,
        )

    def _transition_loaded(
        self,
        current: EvalRun,
        target: RunStatus,
        *,
        timestamp: UtcTimestamp,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
        reference: str | None = None,
        accepted_result_count: int | None = None,
        failed_execution_count: int | None = None,
    ) -> EvalRun:
        if current.status is target:
            return current
        if current.status in self._TERMINAL:
            raise TerminalRunMutation()
        if target not in self._ALLOWED.get(current.status, set()):
            raise InvalidRunTransition()
        if timestamp.instant < current.updated_at.instant:
            raise InvalidRunTransition()
        lifecycle_reference = (
            reference
            if target in self._TERMINAL or target is RunStatus.BLOCKED
            else None
        )
        updated = replace(
            current,
            status=target,
            revision=Revision(current.revision.value + 1),
            updated_at=timestamp,
            accepted_result_count=(
                current.accepted_result_count
                if accepted_result_count is None
                else accepted_result_count
            ),
            failed_execution_count=(
                current.failed_execution_count
                if failed_execution_count is None
                else failed_execution_count
            ),
            finalization_reference=lifecycle_reference,
        )
        try:
            self._runs.update_run(
                updated,
                expected_revision=expected_revision,
                idempotency_key=idempotency_key,
            )
        except EvalStoreError as error:
            self._raise_store_error(error, revision=RunRevisionConflict)
        return updated

    @staticmethod
    def _raise_store_error(
        error: EvalStoreError,
        *,
        not_found: type[EvalRunLifecycleError] | None = None,
        duplicate: type[EvalRunLifecycleError] | None = None,
        revision: type[EvalRunLifecycleError] | None = None,
    ) -> NoReturn:
        if isinstance(error, EvalRecordNotFound) and not_found is not None:
            raise not_found() from error
        if isinstance(error, EvalDuplicateRecord) and duplicate is not None:
            raise duplicate() from error
        if isinstance(error, EvalRevisionConflict) and revision is not None:
            raise revision() from error
        if isinstance(error, EvalIdempotencyConflict):
            raise RunLifecycleIdempotencyConflict() from error
        if isinstance(error, EvalIntegrityConflict):
            raise RunLifecycleIntegrityConflict() from error
        if isinstance(error, (EvalInvalidCursor, EvalInvalidStoreQuery)):
            raise RunLifecycleQueryInvalid() from error
        if isinstance(error, EvalStoreUnavailable):
            raise RunLifecycleUnavailable() from error
        raise RunLifecycleIntegrityConflict() from error
