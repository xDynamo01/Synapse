from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, TypeVar

from .analysis import EvalBaseline, EvalComparison, RegressionReport, RegressionRule
from .case_evaluation import eval_result_checksum
from .catalog import (
    DatasetBinding,
    EvalCaseVersion,
    EvalCaseVersionRef,
    EvalSuite,
    EvalSuiteVersion,
)
from .contracts import (
    EvalAnalysisStore,
    EvalCatalogStore,
    EvalEvidenceStore,
    EvalMaterializationStore,
    EvalRunStore,
)
from .evaluation import BaselineFactory
from .evaluation_records import (
    EvaluationAttemptRecord,
    evaluation_attempt_checksum,
    evaluation_attempt_fingerprint,
)
from .evidence_submission_models import (
    EvalEvidenceSubmissionRecord,
    EvidenceSubmissionAttemptRecord,
    EvidenceSubmissionReceiptRecord,
    evidence_submission_attempt_checksum,
    evidence_submission_attempt_fingerprint,
    evidence_submission_receipt_checksum,
    evidence_submission_record_checksum,
)
from .result_models import MaterializedOutputRecord
from .run_finalization_models import EvalRunFinalizationRecord, validate_finalization_record
from .run_runtime import EvalRunManifestBuilder
from .run_scoring import RunScoringDecision, run_scoring_decision_checksum
from .runs import EvalResult, EvalRun, EvalRunManifest
from .sqlite_serialization import decode_record, encode_record
from .store_errors import (
    EvalDuplicateRecord,
    EvalIdempotencyConflict,
    EvalIntegrityConflict,
    EvalInvalidCursor,
    EvalPersistenceConfigError,
    EvalRecordNotFound,
    EvalRevisionConflict,
    EvalSchemaVersionMismatch,
    EvalStoreError,
    EvalStoreUnavailable,
)
from .store_models import (
    BaselineListFilter,
    ComparisonListFilter,
    DatasetBindingListFilter,
    IdempotencyKey,
    PageRequest,
    RunListFilter,
    StoreCursor,
    StoreOrder,
    StorePage,
    StoreWriteOutcome,
    SuiteListFilter,
    WriteDisposition,
)
from .values import (
    BaselineId,
    ComparisonId,
    ContentChecksum,
    DatasetBindingId,
    EvalCaseId,
    EvalResultId,
    EvalRunFinalizationId,
    EvalRunId,
    EvalRunManifestId,
    EvalSuiteId,
    EvalVersion,
    Fingerprint,
    MaterializedOutputId,
    RegressionReportId,
    RegressionRuleId,
    Revision,
    ScoringDecisionId,
)

SCHEMA_VERSION = 1
T = TypeVar("T")

_RECORD_TABLES = (
    "eval_suites",
    "eval_suite_versions",
    "eval_case_versions",
    "eval_dataset_bindings",
    "eval_runs",
    "eval_run_manifests",
    "eval_results",
    "eval_evaluation_attempts",
    "eval_run_finalizations",
    "eval_scoring_decisions",
    "eval_baselines",
    "eval_comparisons",
    "eval_regression_rules",
    "eval_regression_reports",
    "eval_materialized_outputs",
    "eval_evidence_attempts",
    "eval_evidence_receipts",
    "eval_evidence_submissions",
)
_SCHEMA_TABLES = frozenset((*_RECORD_TABLES, "private_evals_schema", "private_evals_idempotency"))
_RECORD_COLUMNS = (
    "record_key",
    "revision",
    "parent_a",
    "parent_b",
    "parent_c",
    "status",
    "owner",
    "classification",
    "created_at",
    "payload",
    "payload_checksum",
)
_SEMANTIC_UNIQUES = {
    "eval_evaluation_attempts": "parent_b, parent_c",
    "eval_results": "parent_b",
    "eval_run_finalizations": "parent_a",
    "eval_scoring_decisions": "parent_a",
    "eval_materialized_outputs": "parent_b",
    "eval_evidence_attempts": "parent_c",
    "eval_evidence_receipts": "parent_a, parent_b",
    "eval_evidence_submissions": "parent_a",
}
_FOREIGN_KEYS = {
    "eval_suite_versions": ("parent_a", "eval_suites", "record_key"),
    "eval_case_versions": ("parent_a", "eval_suites", "record_key"),
    "eval_results": ("parent_a", "eval_runs", "record_key"),
    "eval_evaluation_attempts": ("parent_a", "eval_runs", "record_key"),
    "eval_run_finalizations": ("parent_a", "eval_runs", "record_key"),
    "eval_evidence_receipts": ("parent_b", "eval_evidence_attempts", "record_key"),
}


@dataclass(frozen=True)
class PrivateEvalsPersistenceConfig:
    database_path: Path
    timeout_seconds: float = 5.0
    create_if_missing: bool = True
    read_only: bool = False
    expected_schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.database_path, Path) or str(self.database_path) in {"", ":memory:"}:
            raise EvalPersistenceConfigError()
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not 0.05 <= float(self.timeout_seconds) <= 60.0
        ):
            raise EvalPersistenceConfigError()
        if not isinstance(self.create_if_missing, bool) or not isinstance(self.read_only, bool):
            raise EvalPersistenceConfigError()
        if self.expected_schema_version != SCHEMA_VERSION:
            raise EvalSchemaVersionMismatch()
        if self.read_only and self.create_if_missing:
            raise EvalPersistenceConfigError()

    def __repr__(self) -> str:
        return (
            "PrivateEvalsPersistenceConfig("
            f"create_if_missing={self.create_if_missing!r}, "
            f"read_only={self.read_only!r}, "
            f"expected_schema_version={self.expected_schema_version!r}, "
            "database_path=<redacted>, timeout_seconds=<redacted>)"
        )


def _payload_checksum(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _value(item: Any) -> Any:
    return getattr(item, "value", item)


def _record_reference(table: str, key: str, record: Any) -> str:
    reference = getattr(record, "record_reference", None)
    return reference if isinstance(reference, str) and reference else f"{table}:{key}"


def _record_key(table: str, record: Any) -> str:
    """Derive the persisted key from the approved record identity."""

    if table == "eval_suites":
        return record.suite_id.value
    if table == "eval_suite_versions":
        return f"{record.suite_id.value}:{record.version.value}"
    if table == "eval_case_versions":
        return f"{record.suite_id.value}:{record.case_id.value}:{record.version.value}"
    if table == "eval_dataset_bindings":
        return f"{record.binding_id.value}:{record.dataset_revision.value}"
    if table == "eval_runs":
        return record.run_id.value
    if table == "eval_run_manifests":
        return record.manifest_id.value
    if table == "eval_results":
        return record.result_id.value
    if table == "eval_evaluation_attempts":
        return record.fingerprint.value
    if table == "eval_run_finalizations":
        return record.finalization_id.value
    if table == "eval_scoring_decisions":
        return record.decision_id.value
    if table == "eval_baselines":
        return record.baseline_id.value
    if table == "eval_comparisons":
        return record.comparison_id.value
    if table == "eval_regression_rules":
        return f"{record.rule_id.value}:{record.version.value}"
    if table == "eval_regression_reports":
        return record.report_id.value
    if table == "eval_materialized_outputs":
        return record.output_id.value
    if table == "eval_evidence_attempts":
        return record.fingerprint.value
    if table == "eval_evidence_receipts":
        return (
            f"{record.logical_submission_fingerprint.value}:"
            f"{record.attempt_fingerprint.value}"
        )
    if table == "eval_evidence_submissions":
        return record.submission_id
    raise EvalIntegrityConflict()


def _record_columns(table: str, record: Any) -> dict[str, str | None]:
    values: dict[str, str | None] = {
        "parent_a": None,
        "parent_b": None,
        "parent_c": None,
        "status": None,
        "owner": None,
        "classification": None,
        "created_at": None,
    }
    if table == "eval_suites":
        values.update(
            status=record.status.value,
            owner=record.owner.value,
            classification=record.classification.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_suite_versions":
        values.update(
            parent_a=record.suite_id.value,
            status=record.status.value,
            owner=record.owner.value,
            classification=record.classification.value,
        )
    elif table == "eval_case_versions":
        values.update(
            parent_a=record.suite_id.value,
            parent_b=record.case_id.value,
            parent_c=record.version.value,
            status=record.status.value,
            owner=record.owner.value,
            classification=record.classification.value,
        )
    elif table == "eval_dataset_bindings":
        values.update(
            parent_a=record.asset_id,
            owner=record.owner.value,
            classification=record.classification.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_runs":
        values.update(
            parent_a=record.suite_id.value,
            parent_b=record.suite_version.value,
            status=record.status.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_run_manifests":
        values.update(parent_a=record.suite_id.value, parent_b=record.suite_version.value)
    elif table == "eval_results":
        logical = (
            f"{record.run_id.value}:{record.case_reference.case_id.value}:"
            f"{record.case_reference.version.value}:{record.repetition}"
        )
        values.update(
            parent_a=record.run_id.value,
            parent_b=logical,
            status=record.status.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_evaluation_attempts":
        identity = record.event_identity
        values.update(
            parent_a=identity.run_id.value,
            parent_b=identity.fingerprint.value if identity.fingerprint is not None else None,
            parent_c=str(record.attempt),
            status=record.status.value,
            created_at=record.started_at.value,
        )
    elif table == "eval_run_finalizations":
        values.update(
            parent_a=record.run_id.value,
            status=record.lifecycle_status.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_scoring_decisions":
        values.update(
            parent_a=record.run_id.value,
            parent_b=record.suite_id.value,
            parent_c=record.suite_version.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_baselines":
        values.update(
            parent_a=record.scope.suite_id.value,
            parent_b=record.scope.suite_version.value,
            parent_c=record.source_run_id.value,
            status=record.status.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_comparisons":
        values.update(
            parent_a=record.scope.suite_id.value,
            parent_b=record.scope.suite_version.value,
            parent_c=f"{record.current_run_id.value}:{record.baseline_id.value}",
            status=record.result.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_regression_rules":
        values.update(
            parent_a=record.rule_id.value,
            parent_b=record.version.value,
            status=record.status.value,
        )
    elif table == "eval_regression_reports":
        values.update(
            parent_a=record.comparison_id.value,
            parent_b=record.rule_id.value,
            parent_c=record.rule_version.value,
            status=record.result.value,
            created_at=record.created_at.value,
        )
    elif table == "eval_materialized_outputs":
        logical = (
            f"{record.run_id.value}:{record.case_reference.case_id.value}:"
            f"{record.case_reference.version.value}:{record.repetition}"
        )
        values.update(
            parent_a=record.run_id.value,
            parent_b=logical,
            created_at=record.created_at.value,
        )
    elif table == "eval_evidence_attempts":
        logical = (
            f"{record.logical_submission_fingerprint.value}:{record.attempt_number}:"
            f"{record.projection_fingerprint.value}"
        )
        values.update(
            parent_a=record.logical_submission_fingerprint.value,
            parent_b=record.projection_fingerprint.value,
            parent_c=logical,
            status=record.status.value,
            created_at=record.started_at.value,
        )
    elif table == "eval_evidence_receipts":
        values.update(
            parent_a=record.logical_submission_fingerprint.value,
            parent_b=record.attempt_fingerprint.value,
            parent_c=record.projection_fingerprint.value,
            created_at=record.received_at.value,
        )
    elif table == "eval_evidence_submissions":
        values.update(
            parent_a=record.run_id.value,
            parent_b=record.finalization_fingerprint.value,
            created_at=record.submitted_at.value,
        )
    else:
        raise EvalIntegrityConflict()
    return values


def _validate_semantic_integrity(record: Any) -> None:
    try:
        if isinstance(record, EvalRunManifest):
            EvalRunManifestBuilder().validate(record)
        elif isinstance(record, EvalResult):
            if record.checksum != eval_result_checksum(record):
                raise EvalIntegrityConflict()
        elif isinstance(record, EvaluationAttemptRecord):
            if (
                record.fingerprint is None
                or record.checksum is None
                or record.fingerprint != evaluation_attempt_fingerprint(record)
                or record.checksum != evaluation_attempt_checksum(record)
            ):
                raise EvalIntegrityConflict()
        elif isinstance(record, EvalRunFinalizationRecord):
            validate_finalization_record(record)
        elif isinstance(record, RunScoringDecision):
            if record.checksum != run_scoring_decision_checksum(record):
                raise EvalIntegrityConflict()
        elif isinstance(record, EvalBaseline):
            BaselineFactory().validate(record)
        elif isinstance(record, EvidenceSubmissionAttemptRecord):
            if (
                record.fingerprint is None
                or record.checksum is None
                or record.fingerprint != evidence_submission_attempt_fingerprint(record)
                or record.checksum != evidence_submission_attempt_checksum(record)
            ):
                raise EvalIntegrityConflict()
        elif isinstance(record, EvidenceSubmissionReceiptRecord):
            if record.checksum != evidence_submission_receipt_checksum(record):
                raise EvalIntegrityConflict()
        elif isinstance(record, EvalEvidenceSubmissionRecord):
            if record.checksum != evidence_submission_record_checksum(record):
                raise EvalIntegrityConflict()
    except EvalIntegrityConflict:
        raise
    except Exception as error:
        raise EvalIntegrityConflict() from error


def _cursor_offset(page: PageRequest) -> int:
    if page.cursor is None:
        return 0
    if not page.cursor.value.startswith("offset:"):
        raise EvalInvalidCursor()
    try:
        offset = int(page.cursor.value.removeprefix("offset:"))
    except ValueError as error:
        raise EvalInvalidCursor() from error
    if offset < 0:
        raise EvalInvalidCursor()
    return offset


class _SQLiteStoreBase:
    def __init__(self, config: PrivateEvalsPersistenceConfig) -> None:
        if not isinstance(config, PrivateEvalsPersistenceConfig):
            raise EvalPersistenceConfigError()
        self.config = config
        self._closed = False
        self._initialize()

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> _SQLiteStoreBase:
        self._ensure_open()
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _ensure_open(self) -> None:
        if self._closed:
            raise EvalStoreUnavailable()

    def _raw_connection(self) -> sqlite3.Connection:
        self._ensure_open()
        path = self.config.database_path
        if self.config.read_only:
            target = f"file:{path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(
                target,
                timeout=self.config.timeout_seconds,
                isolation_level=None,
                uri=True,
            )
        else:
            connection = sqlite3.connect(
                path,
                timeout=self.config.timeout_seconds,
                isolation_level=None,
            )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.config.timeout_seconds * 1000)}")
        if not self.config.read_only:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
        return connection

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        if write and self.config.read_only:
            raise EvalStoreUnavailable()
        try:
            connection = self._raw_connection()
        except sqlite3.Error as error:
            raise EvalStoreUnavailable() from error
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            if write:
                connection.commit()
        except EvalStoreError:
            if write:
                connection.rollback()
            raise
        except sqlite3.Error as error:
            if write:
                connection.rollback()
            raise EvalStoreUnavailable() from error
        finally:
            connection.close()

    def _initialize(self) -> None:
        path = self.config.database_path
        path_exists = path.exists()
        if not path_exists:
            if not self.config.create_if_missing or self.config.read_only:
                raise EvalStoreUnavailable()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as error:
                raise EvalStoreUnavailable() from error
        with self._connection(write=not self.config.read_only) as connection:
            tables = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
            }
            if not tables:
                if self.config.read_only or not self.config.create_if_missing:
                    raise EvalSchemaVersionMismatch()
                self._create_schema(connection)
            self._validate_schema(connection)

    @staticmethod
    def _create_schema(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS private_evals_schema (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                schema_version INTEGER NOT NULL,
                format_version INTEGER NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO private_evals_schema(singleton, schema_version, format_version) "
            "VALUES(1, ?, 1)",
            (SCHEMA_VERSION,),
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS private_evals_idempotency (
                operation TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                record_key TEXT NOT NULL,
                payload_checksum TEXT NOT NULL,
                record_reference TEXT NOT NULL,
                previous_revision INTEGER,
                stored_revision INTEGER NOT NULL,
                PRIMARY KEY(operation, idempotency_key)
            )
            """
        )
        for table in _RECORD_TABLES:
            foreign_key = _FOREIGN_KEYS.get(table)
            foreign_key_sql = ""
            if foreign_key is not None:
                source, parent_table, target = foreign_key
                foreign_key_sql = (
                    f", FOREIGN KEY({source}) REFERENCES {parent_table}({target}) "
                    "ON UPDATE RESTRICT ON DELETE RESTRICT"
                )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {table} (
                    record_key TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    parent_a TEXT,
                    parent_b TEXT,
                    parent_c TEXT,
                    status TEXT,
                    owner TEXT,
                    classification TEXT,
                    created_at TEXT,
                    payload TEXT NOT NULL,
                    payload_checksum TEXT NOT NULL
                    {foreign_key_sql}
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {table}_parent_a_idx ON {table}(parent_a)"
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS {table}_created_idx ON {table}(created_at, record_key)"
            )
        for table, columns in _SEMANTIC_UNIQUES.items():
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_semantic_identity_uq "
                f"ON {table}({columns})"
            )

    def _validate_schema(self, connection: sqlite3.Connection) -> None:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if tables != _SCHEMA_TABLES:
            raise EvalSchemaVersionMismatch()
        metadata = connection.execute(
            "SELECT singleton, schema_version, format_version FROM private_evals_schema"
        ).fetchall()
        if (
            len(metadata) != 1
            or metadata[0]["singleton"] != 1
            or metadata[0]["schema_version"] != self.config.expected_schema_version
            or metadata[0]["format_version"] != 1
        ):
            raise EvalSchemaVersionMismatch()
        expected_idempotency_columns = {
            "operation",
            "idempotency_key",
            "record_key",
            "payload_checksum",
            "record_reference",
            "previous_revision",
            "stored_revision",
        }
        actual_idempotency_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(private_evals_idempotency)"
            ).fetchall()
        }
        if actual_idempotency_columns != expected_idempotency_columns:
            raise EvalSchemaVersionMismatch()
        for table in _RECORD_TABLES:
            columns = tuple(
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            if columns != _RECORD_COLUMNS:
                raise EvalSchemaVersionMismatch()
            indexes = {
                row["name"]
                for row in connection.execute(f"PRAGMA index_list({table})").fetchall()
            }
            required_indexes = {f"{table}_parent_a_idx", f"{table}_created_idx"}
            if table in _SEMANTIC_UNIQUES:
                required_indexes.add(f"{table}_semantic_identity_uq")
            if not required_indexes <= indexes:
                raise EvalSchemaVersionMismatch()
            foreign_keys = connection.execute(f"PRAGMA foreign_key_list({table})").fetchall()
            expected_foreign_key = _FOREIGN_KEYS.get(table)
            if expected_foreign_key is None:
                if foreign_keys:
                    raise EvalSchemaVersionMismatch()
                continue
            if len(foreign_keys) != 1:
                raise EvalSchemaVersionMismatch()
            source, parent_table, target = expected_foreign_key
            foreign_key = foreign_keys[0]
            if (
                foreign_key["from"] != source
                or foreign_key["table"] != parent_table
                or foreign_key["to"] != target
                or foreign_key["on_update"] != "RESTRICT"
                or foreign_key["on_delete"] != "RESTRICT"
            ):
                raise EvalSchemaVersionMismatch()

    @staticmethod
    def _replay(
        connection: sqlite3.Connection,
        operation: str,
        key: IdempotencyKey,
        record_key: str,
        checksum: str,
        outcome_checksum: ContentChecksum,
    ) -> StoreWriteOutcome | None:
        row = connection.execute(
            """SELECT record_key, payload_checksum, record_reference,
                      previous_revision, stored_revision
               FROM private_evals_idempotency
               WHERE operation = ? AND idempotency_key = ?""",
            (operation, key.value),
        ).fetchone()
        if row is None:
            return None
        if row["record_key"] != record_key or row["payload_checksum"] != checksum:
            raise EvalIdempotencyConflict()
        previous = (
            Revision(row["previous_revision"]) if row["previous_revision"] is not None else None
        )
        return StoreWriteOutcome(
            row["record_reference"],
            previous,
            Revision(row["stored_revision"]),
            WriteDisposition.IDEMPOTENT_REPLAY,
            outcome_checksum,
        )

    @staticmethod
    def _outcome_checksum(record: object, payload_checksum: str) -> ContentChecksum:
        semantic_checksum = getattr(record, "checksum", None)
        return (
            semantic_checksum
            if isinstance(semantic_checksum, ContentChecksum)
            else ContentChecksum(payload_checksum)
        )

    @staticmethod
    def _remember(
        connection: sqlite3.Connection,
        operation: str,
        key: IdempotencyKey,
        record_key: str,
        checksum: str,
        reference: str,
        previous: int | None,
        stored: int,
    ) -> None:
        try:
            connection.execute(
                """INSERT INTO private_evals_idempotency(
                       operation, idempotency_key, record_key, payload_checksum,
                       record_reference, previous_revision, stored_revision
                   ) VALUES(?, ?, ?, ?, ?, ?, ?)""",
                (operation, key.value, record_key, checksum, reference, previous, stored),
            )
        except sqlite3.IntegrityError as error:
            raise EvalIdempotencyConflict() from error

    @staticmethod
    def _validate_row(
        table: str,
        row: sqlite3.Row,
        expected: type[T],
        record_key: str,
    ) -> T:
        payload = row["payload"]
        if _payload_checksum(payload) != row["payload_checksum"]:
            raise EvalIntegrityConflict()
        try:
            record = decode_record(payload, expected)
        except EvalStoreError:
            raise
        except Exception as error:
            raise EvalIntegrityConflict() from error
        if not isinstance(record, expected) or _record_key(table, record) != record_key:
            raise EvalIntegrityConflict()
        _validate_semantic_integrity(record)
        record_revision = getattr(record, "revision", None)
        if table in {"eval_suite_versions", "eval_case_versions"}:
            status_value = getattr(getattr(record, "status", None), "value", None)
            if not isinstance(status_value, str):
                raise EvalIntegrityConflict()
            try:
                expected_revision = {
                    "draft": 1,
                    "frozen": 2,
                    "deprecated": 3,
                }[status_value]
            except KeyError as error:
                raise EvalIntegrityConflict() from error
        else:
            expected_revision = 1 if record_revision is None else record_revision.value
        if expected_revision != row["revision"]:
            raise EvalIntegrityConflict()
        expected_columns = _record_columns(table, record)
        if any(row[column] != value for column, value in expected_columns.items()):
            raise EvalIntegrityConflict()
        return record

    @staticmethod
    def _assert_foreign_key_integrity(
        connection: sqlite3.Connection, table: str
    ) -> None:
        if table in _FOREIGN_KEYS and connection.execute(
            f"PRAGMA foreign_key_check({table})"
        ).fetchone() is not None:
            raise EvalIntegrityConflict()

    def _create(
        self,
        table: str,
        record_key: str,
        record: Any,
        idempotency_key: IdempotencyKey,
        *,
        parent_a: str | None = None,
        parent_b: str | None = None,
        parent_c: str | None = None,
        status: str | None = None,
        owner: str | None = None,
        classification: str | None = None,
        created_at: str | None = None,
        append_sequence: tuple[str, int] | None = None,
        active_connection: sqlite3.Connection | None = None,
    ) -> StoreWriteOutcome:
        if _record_key(table, record) != record_key:
            raise EvalIntegrityConflict()
        _validate_semantic_integrity(record)
        record_revision = getattr(record, "revision", None)
        if record_revision is not None and record_revision != Revision(1):
            raise EvalRevisionConflict()
        payload = encode_record(record)
        checksum = _payload_checksum(payload)
        outcome_checksum = self._outcome_checksum(record, checksum)
        operation = f"{table}:create"
        reference = _record_reference(table, record_key, record)
        connection_context = (
            self._connection(write=True)
            if active_connection is None
            else nullcontext(active_connection)
        )
        with connection_context as connection:
            self._assert_foreign_key_integrity(connection, table)
            existing = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM {table} WHERE record_key = ?",
                (record_key,),
            ).fetchone()
            if existing is not None:
                self._validate_row(table, existing, type(record), record_key)
            replay = self._replay(
                connection,
                operation,
                idempotency_key,
                record_key,
                checksum,
                outcome_checksum,
            )
            if replay is not None:
                if existing is None:
                    raise EvalIntegrityConflict()
                return replay
            if existing is not None:
                if existing["payload_checksum"] != checksum:
                    raise EvalDuplicateRecord()
                self._remember(
                    connection, operation, idempotency_key, record_key, checksum, reference, 1, 1
                )
                return StoreWriteOutcome(
                    reference,
                    Revision(1),
                    Revision(1),
                    WriteDisposition.IDEMPOTENT_REPLAY,
                    outcome_checksum,
                )
            if append_sequence is not None:
                sequence_parent, sequence_number = append_sequence
                rows = connection.execute(
                    f"SELECT parent_c FROM {table} WHERE parent_b = ? ORDER BY parent_c",
                    (sequence_parent,),
                ).fetchall()
                try:
                    numbers = tuple(int(row["parent_c"]) for row in rows)
                except (TypeError, ValueError) as error:
                    raise EvalIntegrityConflict() from error
                expected_sequence = tuple(range(1, len(numbers) + 1))
                if numbers != expected_sequence or sequence_number != len(numbers) + 1:
                    raise EvalIntegrityConflict()
            try:
                connection.execute(
                    f"""INSERT INTO {table}(
                           record_key, revision, parent_a, parent_b, parent_c, status,
                           owner, classification, created_at, payload, payload_checksum
                       ) VALUES(?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        record_key,
                        parent_a,
                        parent_b,
                        parent_c,
                        status,
                        owner,
                        classification,
                        created_at,
                        payload,
                        checksum,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise EvalDuplicateRecord() from error
            self._remember(
                connection, operation, idempotency_key, record_key, checksum, reference, None, 1
            )
        return StoreWriteOutcome(
            reference,
            None,
            Revision(1),
            WriteDisposition.CREATED,
            outcome_checksum,
        )

    def _update(
        self,
        table: str,
        record_key: str,
        record: Any,
        expected_revision: Revision,
        idempotency_key: IdempotencyKey,
        *,
        status: str | None = None,
        owner: str | None = None,
        classification: str | None = None,
        created_at: str | None = None,
    ) -> StoreWriteOutcome:
        if _record_key(table, record) != record_key:
            raise EvalIntegrityConflict()
        _validate_semantic_integrity(record)
        payload = encode_record(record)
        checksum = _payload_checksum(payload)
        outcome_checksum = self._outcome_checksum(record, checksum)
        operation = f"{table}:update"
        reference = _record_reference(table, record_key, record)
        stored_revision = Revision(expected_revision.value + 1)
        record_revision = getattr(record, "revision", None)
        if record_revision is not None and record_revision != stored_revision:
            raise EvalRevisionConflict()
        with self._connection(write=True) as connection:
            self._assert_foreign_key_integrity(connection, table)
            row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM {table} WHERE record_key = ?",
                (record_key,),
            ).fetchone()
            if row is not None:
                self._validate_row(table, row, type(record), record_key)
            replay = self._replay(
                connection,
                operation,
                idempotency_key,
                record_key,
                checksum,
                outcome_checksum,
            )
            if replay is not None:
                if row is None:
                    raise EvalIntegrityConflict()
                return replay
            if row is None:
                raise EvalRecordNotFound()
            if row["revision"] != expected_revision.value:
                raise EvalRevisionConflict()
            changed = connection.execute(
                f"""UPDATE {table}
                    SET revision = ?, status = COALESCE(?, status),
                        owner = COALESCE(?, owner),
                        classification = COALESCE(?, classification),
                        created_at = COALESCE(?, created_at),
                        payload = ?, payload_checksum = ?
                    WHERE record_key = ? AND revision = ?""",
                (
                    stored_revision.value,
                    status,
                    owner,
                    classification,
                    created_at,
                    payload,
                    checksum,
                    record_key,
                    expected_revision.value,
                ),
            ).rowcount
            if changed != 1:
                raise EvalRevisionConflict()
            self._remember(
                connection,
                operation,
                idempotency_key,
                record_key,
                checksum,
                reference,
                expected_revision.value,
                stored_revision.value,
            )
        return StoreWriteOutcome(
            reference,
            expected_revision,
            stored_revision,
            WriteDisposition.UPDATED,
            outcome_checksum,
        )

    def _get(self, table: str, record_key: str, expected: type[T]) -> T:
        with self._connection() as connection:
            self._assert_foreign_key_integrity(connection, table)
            row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM {table} WHERE record_key = ?",
                (record_key,),
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self._validate_row(table, row, expected, record_key)

    def _exists(
        self, table: str, expected: type[Any], where: str, values: tuple[Any, ...]
    ) -> bool:
        with self._connection() as connection:
            self._assert_foreign_key_integrity(connection, table)
            row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM {table} "
                f"WHERE {where} LIMIT 1",
                values,
            ).fetchone()
        if row is None:
            return False
        self._validate_row(table, row, expected, row["record_key"])
        return True

    def _page(
        self,
        table: str,
        expected: type[T],
        where: str,
        values: tuple[Any, ...],
        page: PageRequest,
    ) -> StorePage[T]:
        start = _cursor_offset(page)
        order_column = "created_at" if page.order in {
            StoreOrder.CREATED_AT_ASC,
            StoreOrder.CREATED_AT_DESC,
        } else "record_key"
        direction = "DESC" if page.order in {
            StoreOrder.ID_DESC,
            StoreOrder.CREATED_AT_DESC,
        } else "ASC"
        condition = f" WHERE {where}" if where else ""
        with self._connection() as connection:
            self._assert_foreign_key_integrity(connection, table)
            total = connection.execute(
                f"SELECT COUNT(*) AS count FROM {table}{condition}", values
            ).fetchone()["count"]
            rows = connection.execute(
                f"""SELECT {', '.join(_RECORD_COLUMNS)} FROM {table}{condition}
                    ORDER BY {order_column} {direction}, record_key {direction}
                    LIMIT ? OFFSET ?""",
                (*values, page.limit, start),
            ).fetchall()
        items: list[T] = []
        for row in rows:
            items.append(self._validate_row(table, row, expected, row["record_key"]))
        next_offset = start + len(items)
        cursor = StoreCursor(f"offset:{next_offset}") if next_offset < total else None
        return StorePage(tuple(items), cursor, total)


class SQLiteEvalCatalogStore(_SQLiteStoreBase, EvalCatalogStore):
    def create_suite(self, suite: EvalSuite, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_suites",
            suite.suite_id.value,
            suite,
            idempotency_key,
            status=suite.status.value,
            owner=suite.owner.value,
            classification=suite.classification.value,
            created_at=suite.created_at.value,
        )

    def get_suite(self, suite_id: EvalSuiteId) -> EvalSuite:
        return self._get("eval_suites", suite_id.value, EvalSuite)

    def update_suite(self, suite: EvalSuite, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update(
            "eval_suites",
            suite.suite_id.value,
            suite,
            expected_revision,
            idempotency_key,
            status=suite.status.value,
            owner=suite.owner.value,
            classification=suite.classification.value,
            created_at=suite.created_at.value,
        )

    def list_suites(self, filters: SuiteListFilter, page: PageRequest) -> StorePage[EvalSuite]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, item in (
            ("status", filters.status),
            ("owner", filters.owner),
            ("classification", filters.classification),
        ):
            if item is not None:
                clauses.append(f"{column} = ?")
                values.append(item.value)
        return self._page("eval_suites", EvalSuite, " AND ".join(clauses), tuple(values), page)

    def save_suite_version(self, version: EvalSuiteVersion, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.get_suite(version.suite_id)
        return self._create(
            "eval_suite_versions",
            f"{version.suite_id.value}:{version.version.value}",
            version,
            idempotency_key,
            parent_a=version.suite_id.value,
            status=version.status.value,
            owner=version.owner.value,
            classification=version.classification.value,
        )

    def get_suite_version(self, suite_id: EvalSuiteId, version: EvalVersion) -> EvalSuiteVersion:
        return self._get("eval_suite_versions", f"{suite_id.value}:{version.value}", EvalSuiteVersion)

    def update_suite_version_status(self, version: EvalSuiteVersion, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update(
            "eval_suite_versions",
            f"{version.suite_id.value}:{version.version.value}",
            version,
            expected_revision,
            idempotency_key,
            status=version.status.value,
            owner=version.owner.value,
            classification=version.classification.value,
        )

    def list_suite_versions(self, suite_id: EvalSuiteId, page: PageRequest) -> StorePage[EvalSuiteVersion]:
        return self._page("eval_suite_versions", EvalSuiteVersion, "parent_a = ?", (suite_id.value,), page)

    def save_case_version(self, case: EvalCaseVersion, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.get_suite(case.suite_id)
        return self._create(
            "eval_case_versions",
            f"{case.suite_id.value}:{case.case_id.value}:{case.version.value}",
            case,
            idempotency_key,
            parent_a=case.suite_id.value,
            parent_b=case.case_id.value,
            parent_c=case.version.value,
            status=case.status.value,
            owner=case.owner.value,
            classification=case.classification.value,
        )

    def get_case_version(self, suite_id: EvalSuiteId, case_id: EvalCaseId, version: EvalVersion) -> EvalCaseVersion:
        return self._get(
            "eval_case_versions", f"{suite_id.value}:{case_id.value}:{version.value}", EvalCaseVersion
        )

    def update_case_version_status(self, case: EvalCaseVersion, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update(
            "eval_case_versions",
            f"{case.suite_id.value}:{case.case_id.value}:{case.version.value}",
            case,
            expected_revision,
            idempotency_key,
            status=case.status.value,
            owner=case.owner.value,
            classification=case.classification.value,
        )

    def list_case_versions(self, suite_id: EvalSuiteId, suite_version: EvalVersion, page: PageRequest) -> StorePage[EvalCaseVersion]:
        version = self.get_suite_version(suite_id, suite_version)
        references = {(item.case_id.value, item.version.value) for item in version.case_references}
        complete = self._page(
            "eval_case_versions",
            EvalCaseVersion,
            "parent_a = ?",
            (suite_id.value,),
            PageRequest(limit=500, order=page.order),
        )
        selected = tuple(
            item for item in complete.items if (item.case_id.value, item.version.value) in references
        )
        start = _cursor_offset(page)
        items = selected[start : start + page.limit]
        next_offset = start + len(items)
        cursor = StoreCursor(f"offset:{next_offset}") if next_offset < len(selected) else None
        return StorePage(items, cursor, len(selected))

    def save_dataset_binding(self, binding: DatasetBinding, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_dataset_bindings",
            f"{binding.binding_id.value}:{binding.dataset_revision.value}",
            binding,
            idempotency_key,
            parent_a=binding.asset_id,
            owner=binding.owner.value,
            classification=binding.classification.value,
            created_at=binding.created_at.value,
        )

    def get_dataset_binding(self, binding_id: DatasetBindingId, revision: Revision) -> DatasetBinding:
        return self._get(
            "eval_dataset_bindings", f"{binding_id.value}:{revision.value}", DatasetBinding
        )

    def list_dataset_bindings(self, filters: DatasetBindingListFilter, page: PageRequest) -> StorePage[DatasetBinding]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, item in (
            ("parent_a", filters.asset_id),
            ("owner", filters.owner),
            ("classification", filters.classification),
        ):
            if item is not None:
                clauses.append(f"{column} = ?")
                values.append(_value(item))
        return self._page(
            "eval_dataset_bindings", DatasetBinding, " AND ".join(clauses), tuple(values), page
        )


class SQLiteEvalRunStore(_SQLiteStoreBase, EvalRunStore):
    def create_run(self, run: EvalRun, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_runs",
            run.run_id.value,
            run,
            idempotency_key,
            parent_a=run.suite_id.value,
            parent_b=run.suite_version.value,
            status=run.status.value,
            created_at=run.created_at.value,
        )

    def get_run(self, run_id: EvalRunId) -> EvalRun:
        return self._get("eval_runs", run_id.value, EvalRun)

    def update_run(self, run: EvalRun, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update(
            "eval_runs",
            run.run_id.value,
            run,
            expected_revision,
            idempotency_key,
            status=run.status.value,
            created_at=run.created_at.value,
        )

    def list_runs(self, filters: RunListFilter, page: PageRequest) -> StorePage[EvalRun]:
        clauses: list[str] = []
        values: list[Any] = []
        if filters.suite_id is not None:
            clauses.append("parent_a = ?")
            values.append(filters.suite_id.value)
        if filters.status is not None:
            clauses.append("status = ?")
            values.append(filters.status.value)
        if filters.creation is not None:
            if filters.creation.created_from is not None:
                clauses.append("created_at >= ?")
                values.append(filters.creation.created_from.value)
            if filters.creation.created_until is not None:
                clauses.append("created_at <= ?")
                values.append(filters.creation.created_until.value)
        return self._page("eval_runs", EvalRun, " AND ".join(clauses), tuple(values), page)

    def save_manifest(self, manifest: EvalRunManifest, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_run_manifests",
            manifest.manifest_id.value,
            manifest,
            idempotency_key,
            parent_a=manifest.suite_id.value,
            parent_b=manifest.suite_version.value,
        )

    def get_manifest(self, manifest_id: EvalRunManifestId) -> EvalRunManifest:
        return self._get("eval_run_manifests", manifest_id.value, EvalRunManifest)

    def save_result(self, result: EvalResult, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.get_run(result.run_id)
        logical = f"{result.run_id.value}:{result.case_reference.case_id.value}:{result.case_reference.version.value}:{result.repetition}"
        if self._exists(
            "eval_results",
            EvalResult,
            "parent_a = ? AND parent_b = ?",
            (result.run_id.value, logical),
        ):
            existing = self.get_result_for_execution(
                result.run_id, result.case_reference, result.repetition
            )
            if encode_record(existing) != encode_record(result):
                raise EvalDuplicateRecord()
        return self._create(
            "eval_results",
            result.result_id.value,
            result,
            idempotency_key,
            parent_a=result.run_id.value,
            parent_b=logical,
            status=result.status.value,
            created_at=result.created_at.value,
        )

    def get_result(self, result_id: EvalResultId) -> EvalResult:
        return self._get("eval_results", result_id.value, EvalResult)

    def get_result_for_execution(self, run_id: EvalRunId, case_reference: EvalCaseVersionRef, repetition: int) -> EvalResult:
        logical = f"{run_id.value}:{case_reference.case_id.value}:{case_reference.version.value}:{repetition}"
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_key FROM eval_results WHERE parent_a = ? AND parent_b = ?",
                (run_id.value, logical),
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self.get_result(EvalResultId(row["record_key"]))

    def result_exists(self, run_id: EvalRunId, case_reference: EvalCaseVersionRef, repetition: int) -> bool:
        logical = f"{run_id.value}:{case_reference.case_id.value}:{case_reference.version.value}:{repetition}"
        return self._exists(
            "eval_results",
            EvalResult,
            "parent_a = ? AND parent_b = ?",
            (run_id.value, logical),
        )

    def list_results(self, run_id: EvalRunId, page: PageRequest) -> StorePage[EvalResult]:
        return self._page("eval_results", EvalResult, "parent_a = ?", (run_id.value,), page)

    def save_evaluation_attempt(self, record: EvaluationAttemptRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        if record.fingerprint is None:
            raise EvalIntegrityConflict()
        identity = record.event_identity
        if identity.fingerprint is None:
            raise EvalIntegrityConflict()
        self.get_run(identity.run_id)
        return self._create(
            "eval_evaluation_attempts",
            record.fingerprint.value,
            record,
            idempotency_key,
            parent_a=identity.run_id.value,
            parent_b=identity.fingerprint.value,
            parent_c=str(record.attempt),
            status=record.status.value,
            created_at=record.started_at.value,
            append_sequence=(identity.fingerprint.value, record.attempt),
        )

    def get_evaluation_attempt(self, attempt_fingerprint: Fingerprint) -> EvaluationAttemptRecord:
        return self._get("eval_evaluation_attempts", attempt_fingerprint.value, EvaluationAttemptRecord)

    def save_finalization(self, record: EvalRunFinalizationRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        self.get_run(record.run_id)
        if self.finalization_exists(record.run_id):
            existing = self.get_finalization_for_run(record.run_id)
            if encode_record(existing) != encode_record(record):
                raise EvalDuplicateRecord()
        return self._create(
            "eval_run_finalizations",
            record.finalization_id.value,
            record,
            idempotency_key,
            parent_a=record.run_id.value,
            status=record.lifecycle_status.value,
            created_at=record.created_at.value,
        )

    def get_finalization(self, finalization_id: EvalRunFinalizationId) -> EvalRunFinalizationRecord:
        return self._get("eval_run_finalizations", finalization_id.value, EvalRunFinalizationRecord)

    def get_finalization_for_run(self, run_id: EvalRunId) -> EvalRunFinalizationRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_key FROM eval_run_finalizations WHERE parent_a = ?", (run_id.value,)
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self.get_finalization(EvalRunFinalizationId(row["record_key"]))

    def finalization_exists(self, run_id: EvalRunId) -> bool:
        return self._exists(
            "eval_run_finalizations", EvalRunFinalizationRecord, "parent_a = ?", (run_id.value,)
        )


class SQLiteEvalAnalysisStore(_SQLiteStoreBase, EvalAnalysisStore):
    def save_scoring_decision(self, decision: RunScoringDecision, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        if self.scoring_decision_exists(decision.run_id):
            existing = self.get_scoring_decision_for_run(decision.run_id)
            if encode_record(existing) != encode_record(decision):
                raise EvalDuplicateRecord()
        return self._create(
            "eval_scoring_decisions",
            decision.decision_id.value,
            decision,
            idempotency_key,
            parent_a=decision.run_id.value,
            parent_b=decision.suite_id.value,
            parent_c=decision.suite_version.value,
            created_at=decision.created_at.value,
        )

    def get_scoring_decision(self, decision_id: ScoringDecisionId) -> RunScoringDecision:
        return self._get("eval_scoring_decisions", decision_id.value, RunScoringDecision)

    def get_scoring_decision_for_run(self, run_id: EvalRunId) -> RunScoringDecision:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_key FROM eval_scoring_decisions WHERE parent_a = ?", (run_id.value,)
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self.get_scoring_decision(ScoringDecisionId(row["record_key"]))

    def scoring_decision_exists(self, run_id: EvalRunId) -> bool:
        return self._exists(
            "eval_scoring_decisions", RunScoringDecision, "parent_a = ?", (run_id.value,)
        )

    def create_baseline(self, baseline: EvalBaseline, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_baselines",
            baseline.baseline_id.value,
            baseline,
            idempotency_key,
            parent_a=baseline.scope.suite_id.value,
            parent_b=baseline.scope.suite_version.value,
            parent_c=baseline.source_run_id.value,
            status=baseline.status.value,
            created_at=baseline.created_at.value,
        )

    def get_baseline(self, baseline_id: BaselineId) -> EvalBaseline:
        return self._get("eval_baselines", baseline_id.value, EvalBaseline)

    def update_baseline_status(self, baseline: EvalBaseline, *, expected_revision: Revision, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._update(
            "eval_baselines",
            baseline.baseline_id.value,
            baseline,
            expected_revision,
            idempotency_key,
            status=baseline.status.value,
            created_at=baseline.created_at.value,
        )

    def list_baselines(self, filters: BaselineListFilter, page: PageRequest) -> StorePage[EvalBaseline]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, item in (
            ("parent_a", filters.suite_id),
            ("parent_b", filters.suite_version),
            ("status", filters.status),
        ):
            if item is not None:
                clauses.append(f"{column} = ?")
                values.append(item.value)
        return self._page("eval_baselines", EvalBaseline, " AND ".join(clauses), tuple(values), page)

    def save_comparison(self, comparison: EvalComparison, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_comparisons",
            comparison.comparison_id.value,
            comparison,
            idempotency_key,
            parent_a=comparison.scope.suite_id.value,
            parent_b=comparison.scope.suite_version.value,
            parent_c=f"{comparison.current_run_id.value}:{comparison.baseline_id.value}",
            status=comparison.result.value,
            created_at=comparison.created_at.value,
        )

    def get_comparison(self, comparison_id: ComparisonId) -> EvalComparison:
        return self._get("eval_comparisons", comparison_id.value, EvalComparison)

    def list_comparisons(self, filters: ComparisonListFilter, page: PageRequest) -> StorePage[EvalComparison]:
        clauses: list[str] = []
        values: list[Any] = []
        for column, item in (
            ("parent_a", filters.suite_id),
            ("parent_b", filters.suite_version),
        ):
            if item is not None:
                clauses.append(f"{column} = ?")
                values.append(item.value)
        if filters.current_run_id is not None:
            clauses.append("substr(parent_c, 1, instr(parent_c, ':') - 1) = ?")
            values.append(filters.current_run_id.value)
        if filters.baseline_id is not None:
            clauses.append("substr(parent_c, instr(parent_c, ':') + 1) = ?")
            values.append(filters.baseline_id.value)
        return self._page(
            "eval_comparisons",
            EvalComparison,
            " AND ".join(clauses),
            tuple(values),
            page,
        )

    def save_regression_rule(self, rule: RegressionRule, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_regression_rules",
            f"{rule.rule_id.value}:{rule.version.value}",
            rule,
            idempotency_key,
            parent_a=rule.rule_id.value,
            parent_b=rule.version.value,
            status=rule.status.value,
        )

    def get_regression_rule(self, rule_id: RegressionRuleId, version: EvalVersion) -> RegressionRule:
        return self._get("eval_regression_rules", f"{rule_id.value}:{version.value}", RegressionRule)

    def save_regression_report(self, report: RegressionReport, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        return self._create(
            "eval_regression_reports",
            report.report_id.value,
            report,
            idempotency_key,
            parent_a=report.comparison_id.value,
            parent_b=report.rule_id.value,
            parent_c=report.rule_version.value,
            status=report.result.value,
            created_at=report.created_at.value,
        )

    def get_regression_report(self, report_id: RegressionReportId) -> RegressionReport:
        return self._get("eval_regression_reports", report_id.value, RegressionReport)


class SQLiteEvalMaterializationStore(_SQLiteStoreBase, EvalMaterializationStore):
    @staticmethod
    def _logical(run_id: EvalRunId, case: EvalCaseVersionRef, repetition: int) -> str:
        return f"{run_id.value}:{case.case_id.value}:{case.version.value}:{repetition}"

    def save_materialized_output(self, record: MaterializedOutputRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        logical = self._logical(record.run_id, record.case_reference, record.repetition)
        if self._exists(
            "eval_materialized_outputs", MaterializedOutputRecord, "parent_b = ?", (logical,)
        ):
            existing = self.get_materialized_output_for_execution(
                record.run_id, record.case_reference, record.repetition
            )
            if encode_record(existing) != encode_record(record):
                raise EvalDuplicateRecord()
        return self._create(
            "eval_materialized_outputs",
            record.output_id.value,
            record,
            idempotency_key,
            parent_a=record.run_id.value,
            parent_b=logical,
            created_at=record.created_at.value,
        )

    def get_materialized_output(self, output_id: MaterializedOutputId) -> MaterializedOutputRecord:
        return self._get("eval_materialized_outputs", output_id.value, MaterializedOutputRecord)

    def get_materialized_output_for_execution(self, run_id: EvalRunId, case_reference: EvalCaseVersionRef, repetition: int) -> MaterializedOutputRecord:
        logical = self._logical(run_id, case_reference, repetition)
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_key FROM eval_materialized_outputs WHERE parent_b = ?", (logical,)
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self.get_materialized_output(MaterializedOutputId(row["record_key"]))

    def materialized_output_exists(self, run_id: EvalRunId, case_reference: EvalCaseVersionRef, repetition: int) -> bool:
        return self._exists(
            "eval_materialized_outputs",
            MaterializedOutputRecord,
            "parent_b = ?",
            (self._logical(run_id, case_reference, repetition),),
        )


class SQLiteEvalEvidenceStore(_SQLiteStoreBase, EvalEvidenceStore):
    def _assert_evidence_chain_open(
        self, connection: sqlite3.Connection, logical_fingerprint: Fingerprint
    ) -> None:
        rows = connection.execute(
            f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_submissions"
        ).fetchall()
        for row in rows:
            submission = self._validate_row(
                "eval_evidence_submissions",
                row,
                EvalEvidenceSubmissionRecord,
                row["record_key"],
            )
            if submission.semantic_fingerprint == logical_fingerprint:
                raise EvalIntegrityConflict()

    def save_evidence_submission(self, record: EvalEvidenceSubmissionRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        with self._connection(write=True) as connection:
            finalization_row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} "
                "FROM eval_run_finalizations WHERE parent_a = ?",
                (record.run_id.value,),
            ).fetchone()
            if finalization_row is None:
                raise EvalIntegrityConflict()
            finalization = self._validate_row(
                "eval_run_finalizations",
                finalization_row,
                EvalRunFinalizationRecord,
                finalization_row["record_key"],
            )
            if (
                finalization.fingerprint != record.finalization_fingerprint
                or record.finalization_reference
                not in {
                    finalization.finalization_id.value,
                    f"private-evals-finalization:{finalization.finalization_id.value}",
                    finalization.record_reference,
                }
            ):
                raise EvalIntegrityConflict()
            attempt_rows = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_attempts "
                "WHERE parent_a = ?",
                (record.semantic_fingerprint.value,),
            ).fetchall()
            receipt_rows = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_receipts "
                "WHERE parent_a = ?",
                (record.semantic_fingerprint.value,),
            ).fetchall()
            attempts = tuple(
                self._validate_row(
                    "eval_evidence_attempts",
                    row,
                    EvidenceSubmissionAttemptRecord,
                    row["record_key"],
                )
                for row in attempt_rows
            )
            receipts = tuple(
                self._validate_row(
                    "eval_evidence_receipts",
                    row,
                    EvidenceSubmissionReceiptRecord,
                    row["record_key"],
                )
                for row in receipt_rows
            )
            attempt_by_fingerprint = {
                item.fingerprint: item for item in attempts if item.fingerprint is not None
            }
            receipt_by_projection = {item.projection_fingerprint: item for item in receipts}
            if (
                len(attempt_by_fingerprint) != len(attempts)
                or len(receipt_by_projection) != len(receipts)
                or set(receipt_by_projection) != set(record.projection_fingerprints)
                or len(attempts) != len(record.projection_fingerprints)
            ):
                raise EvalIntegrityConflict()
            for projection, governance_receipt in zip(
                record.projection_fingerprints, record.governance_receipts
            ):
                receipt = receipt_by_projection[projection]
                attempt = attempt_by_fingerprint.get(receipt.attempt_fingerprint)
                if (
                    attempt is None
                    or attempt.logical_submission_fingerprint
                    != record.semantic_fingerprint
                    or attempt.projection_fingerprint != projection
                    or receipt.governance_receipt != governance_receipt
                ):
                    raise EvalIntegrityConflict()
            return self._create(
                "eval_evidence_submissions",
                record.submission_id,
                record,
                idempotency_key,
                parent_a=record.run_id.value,
                parent_b=record.finalization_fingerprint.value,
                created_at=record.submitted_at.value,
                active_connection=connection,
            )

    def get_evidence_submission(self, submission_id: str) -> EvalEvidenceSubmissionRecord:
        return self._get("eval_evidence_submissions", submission_id, EvalEvidenceSubmissionRecord)

    def get_evidence_submission_for_run(self, run_id: EvalRunId) -> EvalEvidenceSubmissionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT record_key FROM eval_evidence_submissions WHERE parent_a = ?", (run_id.value,)
            ).fetchone()
        if row is None:
            raise EvalRecordNotFound()
        return self.get_evidence_submission(row["record_key"])

    def evidence_submission_exists(self, run_id: EvalRunId) -> bool:
        return self._exists(
            "eval_evidence_submissions",
            EvalEvidenceSubmissionRecord,
            "parent_a = ?",
            (run_id.value,),
        )

    def save_evidence_submission_attempt(self, record: EvidenceSubmissionAttemptRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        if record.fingerprint is None:
            raise EvalIntegrityConflict()
        logical_attempt = f"{record.logical_submission_fingerprint.value}:{record.attempt_number}:{record.projection_fingerprint.value}"
        with self._connection(write=True) as connection:
            existing_row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_attempts "
                "WHERE parent_c = ?",
                (logical_attempt,),
            ).fetchone()
            if existing_row is not None:
                existing = self._validate_row(
                    "eval_evidence_attempts",
                    existing_row,
                    EvidenceSubmissionAttemptRecord,
                    existing_row["record_key"],
                )
                if encode_record(existing) != encode_record(record):
                    raise EvalDuplicateRecord()
            else:
                self._assert_evidence_chain_open(
                    connection, record.logical_submission_fingerprint
                )
            return self._create(
                "eval_evidence_attempts",
                record.fingerprint.value,
                record,
                idempotency_key,
                parent_a=record.logical_submission_fingerprint.value,
                parent_b=record.projection_fingerprint.value,
                parent_c=logical_attempt,
                status=record.status.value,
                created_at=record.started_at.value,
                active_connection=connection,
            )

    def list_evidence_submission_attempts(self, logical_submission_fingerprint: Fingerprint) -> tuple[EvidenceSubmissionAttemptRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_attempts "
                "WHERE parent_a = ? ORDER BY created_at ASC, record_key ASC",
                (logical_submission_fingerprint.value,),
            ).fetchall()
        records = tuple(
            self._validate_row(
                "eval_evidence_attempts",
                row,
                EvidenceSubmissionAttemptRecord,
                row["record_key"],
            )
            for row in rows
        )
        return tuple(sorted(records, key=lambda item: item.attempt_number))

    def save_evidence_submission_receipt(self, record: EvidenceSubmissionReceiptRecord, *, idempotency_key: IdempotencyKey) -> StoreWriteOutcome:
        with self._connection(write=True) as connection:
            key = (
                f"{record.logical_submission_fingerprint.value}:"
                f"{record.attempt_fingerprint.value}"
            )
            existing_row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_receipts "
                "WHERE record_key = ?",
                (key,),
            ).fetchone()
            if existing_row is not None:
                return self._create(
                    "eval_evidence_receipts",
                    key,
                    record,
                    idempotency_key,
                    parent_a=record.logical_submission_fingerprint.value,
                    parent_b=record.attempt_fingerprint.value,
                    parent_c=record.projection_fingerprint.value,
                    created_at=record.received_at.value,
                    active_connection=connection,
                )
            self._assert_evidence_chain_open(
                connection, record.logical_submission_fingerprint
            )
            attempt_row = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_attempts "
                "WHERE record_key = ?",
                (record.attempt_fingerprint.value,),
            ).fetchone()
            if attempt_row is None:
                raise EvalIntegrityConflict()
            attempt = self._validate_row(
                "eval_evidence_attempts",
                attempt_row,
                EvidenceSubmissionAttemptRecord,
                attempt_row["record_key"],
            )
            if (
                attempt.logical_submission_fingerprint
                != record.logical_submission_fingerprint
                or attempt.attempt_number != record.attempt_number
                or attempt.projection_fingerprint != record.projection_fingerprint
                or attempt.projection_kind is not record.projection_kind
            ):
                raise EvalIntegrityConflict()
            return self._create(
                "eval_evidence_receipts",
                key,
                record,
                idempotency_key,
                parent_a=record.logical_submission_fingerprint.value,
                parent_b=record.attempt_fingerprint.value,
                parent_c=record.projection_fingerprint.value,
                created_at=record.received_at.value,
                active_connection=connection,
            )

    def list_evidence_submission_receipts(self, logical_submission_fingerprint: Fingerprint) -> tuple[EvidenceSubmissionReceiptRecord, ...]:
        with self._connection() as connection:
            self._assert_foreign_key_integrity(connection, "eval_evidence_receipts")
            rows = connection.execute(
                f"SELECT {', '.join(_RECORD_COLUMNS)} FROM eval_evidence_receipts "
                "WHERE parent_a = ? ORDER BY created_at ASC, record_key ASC",
                (logical_submission_fingerprint.value,),
            ).fetchall()
        records = tuple(
            self._validate_row(
                "eval_evidence_receipts",
                row,
                EvidenceSubmissionReceiptRecord,
                row["record_key"],
            )
            for row in rows
        )
        return tuple(sorted(records, key=lambda item: item.attempt_number))
