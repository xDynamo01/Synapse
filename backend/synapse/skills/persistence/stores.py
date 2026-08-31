from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, TypeVar

from synapse.skills.phase2_models import PublishedSkillVersionId, SkillId, SkillSemanticReference
from synapse.skills.phase3_contracts import (
    SkillAssignmentStore,
    SkillBindingStore,
    SkillCatalogStore,
    SkillInstallationHistory,
    SkillInstallationStore,
    SkillLeaseStore,
    SkillLifecycleHistory,
    SkillLifecycleStore,
    SkillStoreWriteOutcome,
)
from synapse.skills.phase3_errors import (
    SkillStoreDivergentDuplicate,
    SkillStoreInvalidParentReference,
    SkillStoreNotFound,
    SkillStoreUnavailable,
)
from synapse.skills.phase3_records import (
    PublishedSkillVersionRecord,
    SkillActivationRecord,
    SkillAssignmentRecord,
    SkillAssignmentTerminationRecord,
    SkillEvaluationBindingRecord,
    SkillGovernanceBindingRecord,
    SkillInstallationRecord,
    SkillInstallationTerminationRecord,
    SkillLeaseRecord,
    SkillLeaseTerminationRecord,
    SkillLifecycleRecord,
    SkillRevocationRecord,
)
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase8_contracts import (
    SkillDependencyCatalogPage,
    SkillDependencyCatalogProvider,
)
from synapse.skills.phase10_contracts import SkillExternalBindingStore
from synapse.skills.phase10_models import (
    SkillGovernanceBindingHistory,
    SkillIntelligenceBindingHistory,
    SkillIntelligenceBindingRecord,
)
from synapse.skills.phase10_models import (
    SkillGovernanceBindingRecord as ExternalGovernanceBindingRecord,
)
from synapse.skills.phase11_contracts import SkillPrivateEvalBindingStore
from synapse.skills.phase11_models import (
    SkillPrivateEvalBindingHistory,
    SkillPrivateEvalBindingRecord,
)

from .codec import canonical_timestamp, decode_record, encode_record
from .connection import SkillSQLiteConnectionFactory
from .errors import SkillPersistenceError, SkillPersistenceUnavailable
from .migrations import SkillPersistenceSchemaVersion

_RecordT = TypeVar("_RecordT")
_TABLES = frozenset(
    {
        "publications",
        "lifecycle_records",
        "installation_records",
        "installation_terminations",
        "assignments",
        "assignment_terminations",
        "leases",
        "lease_terminations",
        "legacy_governance_bindings",
        "legacy_evaluation_bindings",
        "governance_bindings",
        "intelligence_bindings",
        "private_eval_bindings",
    }
)


class _SQLiteStore:
    def __init__(self, connections: SkillSQLiteConnectionFactory) -> None:
        self._connections = connections

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        try:
            with self._connections.connection() as connection:
                self._assert_schema(connection)
                if write:
                    connection.execute("BEGIN IMMEDIATE")
                try:
                    yield connection
                    if write:
                        connection.commit()
                except Exception:
                    if write:
                        connection.rollback()
                    raise
        except (
            SkillStoreDivergentDuplicate,
            SkillStoreInvalidParentReference,
            SkillStoreNotFound,
            SkillPersistenceError,
        ):
            raise
        except sqlite3.Error as exc:
            raise SkillPersistenceUnavailable() from exc

    @staticmethod
    def _assert_schema(connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT schema_version FROM skill_schema_metadata WHERE singleton = 1"
        ).fetchone()
        if row is None or row[0] != int(SkillPersistenceSchemaVersion.V1):
            raise SkillStoreUnavailable()

    @staticmethod
    def _append(
        connection: sqlite3.Connection,
        *,
        table: str,
        key_column: str,
        key: str,
        columns: tuple[str, ...],
        values: tuple[object, ...],
        payload: str,
        record: object,
        record_type: type[object],
    ) -> SkillStoreWriteOutcome:
        if table not in _TABLES or key_column not in {
            "exact_identity",
            "record_id",
            "occurrence_ref",
        }:
            raise SkillStoreUnavailable()
        existing = connection.execute(
            f"SELECT payload FROM {table} WHERE {key_column} = ?", (key,)
        ).fetchone()
        if existing is not None:
            if decode_record(existing[0], record_type) != record:
                raise SkillStoreDivergentDuplicate()
            return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
        placeholders = ",".join("?" for _ in columns)
        names = ",".join(columns)
        try:
            connection.execute(
                f"INSERT INTO {table} ({names}) VALUES ({placeholders})", values
            )
        except sqlite3.IntegrityError:
            existing = connection.execute(
                f"SELECT payload FROM {table} WHERE {key_column} = ?", (key,)
            ).fetchone()
            if (
                existing is not None
                and decode_record(existing[0], record_type) == record
            ):
                return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
            raise SkillStoreDivergentDuplicate() from None
        return SkillStoreWriteOutcome.CREATED

    @staticmethod
    def _assert_publication(
        connection: sqlite3.Connection, identity: PublishedSkillVersionId
    ) -> None:
        if (
            connection.execute(
                "SELECT 1 FROM publications WHERE exact_identity = ?",
                (identity.to_canonical_text(),),
            ).fetchone()
            is None
        ):
            raise SkillStoreInvalidParentReference()

    @staticmethod
    def _assert_parent_identity(
        connection: sqlite3.Connection,
        table: str,
        key: str,
        identity: PublishedSkillVersionId,
    ) -> None:
        if table not in _TABLES:
            raise SkillStoreUnavailable()
        row = connection.execute(
            f"SELECT exact_identity FROM {table} WHERE record_id = ?", (key,)
        ).fetchone()
        if row is None or row[0] != identity.to_canonical_text():
            raise SkillStoreInvalidParentReference()


class SQLiteSkillCatalogStore(
    _SQLiteStore, SkillCatalogStore, SkillDependencyCatalogProvider
):
    def save_version(
        self, record: PublishedSkillVersionRecord
    ) -> SkillStoreWriteOutcome:
        identity = record.identity
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            structural = connection.execute(
                "SELECT exact_identity, payload FROM publications "
                "WHERE skill_id = ? AND version = ?",
                (identity.skill_id.value, str(identity.version)),
            ).fetchone()
            if structural is not None:
                if (
                    structural[0] != identity.to_canonical_text()
                    or decode_record(structural[1], PublishedSkillVersionRecord)
                    != record
                ):
                    raise SkillStoreDivergentDuplicate()
                return SkillStoreWriteOutcome.IDEMPOTENT_REPLAY
            return self._append(
                connection,
                table="publications",
                key_column="exact_identity",
                key=identity.to_canonical_text(),
                columns=(
                    "exact_identity",
                    "skill_id",
                    "version",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    identity.to_canonical_text(),
                    identity.skill_id.value,
                    str(identity.version),
                    canonical_timestamp(record.recorded_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=PublishedSkillVersionRecord,
            )

    def get_version(
        self, identity: PublishedSkillVersionId
    ) -> PublishedSkillVersionRecord:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload FROM publications WHERE exact_identity = ?",
                (identity.to_canonical_text(),),
            ).fetchone()
        if row is None:
            raise SkillStoreNotFound()
        return decode_record(row[0], PublishedSkillVersionRecord)

    def list_versions(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        return self._ordered_versions(skill_id)[: limit.limit]

    def list_dependency_candidates(
        self, skill_id: SkillId, limit: SkillStoreQueryLimit
    ) -> SkillDependencyCatalogPage:
        records = self._ordered_versions(skill_id)
        return SkillDependencyCatalogPage(
            records[: limit.limit], len(records) <= limit.limit
        )

    def _ordered_versions(
        self, skill_id: SkillId
    ) -> tuple[PublishedSkillVersionRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM publications WHERE skill_id = ?", (skill_id.value,)
            ).fetchall()
        records = tuple(
            decode_record(row[0], PublishedSkillVersionRecord) for row in rows
        )
        return tuple(
            sorted(
                records,
                key=lambda record: (
                    record.identity.version.precedence_key(),
                    str(record.identity.version),
                    record.identity.to_canonical_text(),
                ),
            )
        )


class SQLiteSkillLifecycleStore(_SQLiteStore, SkillLifecycleStore):
    def append_lifecycle(
        self, record: SkillLifecycleRecord
    ) -> SkillStoreWriteOutcome:
        return self._save(record, "lifecycle", record.occurred_at, None)

    def append_activation(
        self, record: SkillActivationRecord
    ) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            self._assert_parent_identity(
                connection,
                "installation_records",
                record.installation_id.value,
                record.identity,
            )
            return self._save_in_connection(
                connection, record, "activation", record.activated_at, record.installation_id.value
            )

    def append_revocation(
        self, record: SkillRevocationRecord
    ) -> SkillStoreWriteOutcome:
        return self._save(record, "revocation", record.revoked_at, None)

    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillLifecycleHistory:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT record_kind, payload FROM lifecycle_records "
                "WHERE exact_identity = ? ORDER BY occurred_at, record_id LIMIT ?",
                (identity.to_canonical_text(), limit.limit + 1),
            ).fetchall()
        records = tuple(_decode_lifecycle(row[0], row[1]) for row in rows[: limit.limit])
        return SkillLifecycleHistory(records, len(rows) <= limit.limit)

    def _save(
        self,
        record: SkillLifecycleRecord | SkillRevocationRecord,
        kind: str,
        occurred_at: datetime,
        parent: str | None,
    ) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            return self._save_in_connection(connection, record, kind, occurred_at, parent)

    def _save_in_connection(
        self,
        connection: sqlite3.Connection,
        record: SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord,
        kind: str,
        occurred_at: datetime,
        parent: str | None,
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        self._assert_publication(connection, record.identity)
        return self._append(
            connection,
            table="lifecycle_records",
            key_column="record_id",
            key=record.record_id.value,
            columns=(
                "record_id",
                "exact_identity",
                "record_kind",
                "occurred_at",
                "parent_installation_id",
                "payload",
            ),
            values=(
                record.record_id.value,
                record.identity.to_canonical_text(),
                kind,
                canonical_timestamp(occurred_at),
                parent,
                payload,
            ),
            payload=payload,
            record=record,
            record_type=type(record),
        )


class SQLiteSkillInstallationStore(_SQLiteStore, SkillInstallationStore):
    def append_installation(
        self, record: SkillInstallationRecord
    ) -> SkillStoreWriteOutcome:
        return self._save(
            "installation_records",
            record.record_id.value,
            record.identity,
            record.installed_at,
            record,
        )

    def append_termination(
        self, record: SkillInstallationTerminationRecord
    ) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            self._assert_parent_identity(
                connection,
                "installation_records",
                record.installation_id.value,
                record.identity,
            )
            payload = encode_record(record)
            return self._append(
                connection,
                table="installation_terminations",
                key_column="record_id",
                key=record.record_id.value,
                columns=(
                    "record_id",
                    "installation_id",
                    "exact_identity",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.record_id.value,
                    record.installation_id.value,
                    record.identity.to_canonical_text(),
                    canonical_timestamp(record.terminated_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillInstallationTerminationRecord,
            )

    def history(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillInstallationHistory:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT kind, payload FROM ("
                "SELECT 'installation' kind, occurred_at, record_id, payload "
                "FROM installation_records WHERE exact_identity = ? UNION ALL "
                "SELECT 'termination', occurred_at, record_id, payload "
                "FROM installation_terminations WHERE exact_identity = ?) "
                "ORDER BY occurred_at, record_id LIMIT ?",
                (identity.to_canonical_text(), identity.to_canonical_text(), limit.limit + 1),
            ).fetchall()
        records = tuple(
            _decode_installation(row[0], row[1]) for row in rows[: limit.limit]
        )
        return SkillInstallationHistory(records, len(rows) <= limit.limit)

    def _save(
        self,
        table: str,
        key: str,
        identity: PublishedSkillVersionId,
        occurred_at: datetime,
        record: object,
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            self._assert_publication(connection, identity)
            return self._append(
                connection,
                table=table,
                key_column="record_id",
                key=key,
                columns=("record_id", "exact_identity", "occurred_at", "payload"),
                values=(
                    key,
                    identity.to_canonical_text(),
                    canonical_timestamp(occurred_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=type(record),
            )


class SQLiteSkillAssignmentStore(_SQLiteStore, SkillAssignmentStore):
    def append_assignment(
        self, record: SkillAssignmentRecord
    ) -> SkillStoreWriteOutcome:
        return self._save_assignment(record)

    def append_termination(
        self, record: SkillAssignmentTerminationRecord
    ) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            parent = connection.execute(
                "SELECT subject_ref, exact_identity FROM assignments WHERE record_id = ?",
                (record.assignment_id.value,),
            ).fetchone()
            if (
                parent is None
                or parent[1] != record.identity.to_canonical_text()
            ):
                raise SkillStoreInvalidParentReference()
            payload = encode_record(record)
            return self._append(
                connection,
                table="assignment_terminations",
                key_column="record_id",
                key=record.record_id.value,
                columns=(
                    "record_id",
                    "assignment_id",
                    "exact_identity",
                    "subject_ref",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.record_id.value,
                    record.assignment_id.value,
                    record.identity.to_canonical_text(),
                    parent[0],
                    canonical_timestamp(record.terminated_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillAssignmentTerminationRecord,
            )

    def history_for_subject(
        self, subject_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillAssignmentRecord | SkillAssignmentTerminationRecord, ...]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT kind, payload FROM ("
                "SELECT 'assignment' kind, occurred_at, record_id, payload FROM assignments "
                "WHERE subject_ref = ? UNION ALL "
                "SELECT 'termination', occurred_at, record_id, payload "
                "FROM assignment_terminations WHERE subject_ref = ?) "
                "ORDER BY occurred_at, record_id LIMIT ?",
                (subject_ref.value, subject_ref.value, limit.limit),
            ).fetchall()
        return tuple(_decode_assignment(row[0], row[1]) for row in rows)

    def _save_assignment(
        self, record: SkillAssignmentRecord
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            self._assert_publication(connection, record.identity)
            return self._append(
                connection,
                table="assignments",
                key_column="record_id",
                key=record.record_id.value,
                columns=(
                    "record_id",
                    "exact_identity",
                    "subject_ref",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.record_id.value,
                    record.identity.to_canonical_text(),
                    record.subject_ref.value,
                    canonical_timestamp(record.assigned_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillAssignmentRecord,
            )


class SQLiteSkillLeaseStore(_SQLiteStore, SkillLeaseStore):
    def append_lease(self, record: SkillLeaseRecord) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            self._assert_parent_identity(
                connection,
                "assignments",
                record.assignment_id.value,
                record.identity,
            )
            payload = encode_record(record)
            return self._append(
                connection,
                table="leases",
                key_column="record_id",
                key=record.record_id.value,
                columns=(
                    "record_id",
                    "assignment_id",
                    "exact_identity",
                    "agent_ref",
                    "task_ref",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.record_id.value,
                    record.assignment_id.value,
                    record.identity.to_canonical_text(),
                    record.agent_ref.value,
                    record.task_ref.value,
                    canonical_timestamp(record.granted_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillLeaseRecord,
            )

    def append_termination(
        self, record: SkillLeaseTerminationRecord
    ) -> SkillStoreWriteOutcome:
        with self._connection(write=True) as connection:
            parent = connection.execute(
                "SELECT agent_ref, task_ref, exact_identity FROM leases WHERE record_id = ?",
                (record.lease_id.value,),
            ).fetchone()
            if (
                parent is None
                or parent[2] != record.identity.to_canonical_text()
            ):
                raise SkillStoreInvalidParentReference()
            payload = encode_record(record)
            return self._append(
                connection,
                table="lease_terminations",
                key_column="record_id",
                key=record.record_id.value,
                columns=(
                    "record_id",
                    "lease_id",
                    "exact_identity",
                    "agent_ref",
                    "task_ref",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.record_id.value,
                    record.lease_id.value,
                    record.identity.to_canonical_text(),
                    parent[0],
                    parent[1],
                    canonical_timestamp(record.terminated_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillLeaseTerminationRecord,
            )

    def history_for_agent(
        self, agent_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        return self._history("agent_ref", agent_ref.value, limit)

    def history_for_task(
        self, task_ref: SkillSemanticReference, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        return self._history("task_ref", task_ref.value, limit)

    def history_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        return self._history("exact_identity", identity.to_canonical_text(), limit)

    def _history(
        self, column: str, value: str, limit: SkillStoreQueryLimit
    ) -> tuple[SkillLeaseRecord | SkillLeaseTerminationRecord, ...]:
        if column not in {"agent_ref", "task_ref", "exact_identity"}:
            raise SkillStoreUnavailable()
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT kind, payload FROM ("
                f"SELECT 'lease' kind, occurred_at, record_id, payload FROM leases "
                f"WHERE {column} = ? UNION ALL "
                f"SELECT 'termination', occurred_at, record_id, payload "
                f"FROM lease_terminations WHERE {column} = ?) "
                "ORDER BY occurred_at, record_id LIMIT ?",
                (value, value, limit.limit),
            ).fetchall()
        return tuple(_decode_lease(row[0], row[1]) for row in rows)


class SQLiteSkillBindingStore(_SQLiteStore, SkillBindingStore):
    def append_governance(
        self, record: SkillGovernanceBindingRecord
    ) -> SkillStoreWriteOutcome:
        return self._save_legacy(
            "legacy_governance_bindings", record, record.bound_at
        )

    def append_evaluation(
        self, record: SkillEvaluationBindingRecord
    ) -> SkillStoreWriteOutcome:
        return self._save_legacy(
            "legacy_evaluation_bindings", record, record.bound_at
        )

    def list_governance_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillGovernanceBindingRecord, ...]:
        return self._list_legacy(
            "legacy_governance_bindings",
            identity,
            limit,
            SkillGovernanceBindingRecord,
        )

    def list_evaluations_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> tuple[SkillEvaluationBindingRecord, ...]:
        return self._list_legacy(
            "legacy_evaluation_bindings",
            identity,
            limit,
            SkillEvaluationBindingRecord,
        )

    def _save_legacy(
        self,
        table: str,
        record: SkillGovernanceBindingRecord | SkillEvaluationBindingRecord,
        occurred_at: datetime,
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            self._assert_publication(connection, record.identity)
            return self._append(
                connection,
                table=table,
                key_column="record_id",
                key=record.record_id.value,
                columns=("record_id", "exact_identity", "occurred_at", "payload"),
                values=(
                    record.record_id.value,
                    record.identity.to_canonical_text(),
                    canonical_timestamp(occurred_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=type(record),
            )

    def _list_legacy(
        self,
        table: str,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
        record_type: type[_RecordT],
    ) -> tuple[_RecordT, ...]:
        if table not in {
            "legacy_governance_bindings",
            "legacy_evaluation_bindings",
        }:
            raise SkillStoreUnavailable()
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table} WHERE exact_identity = ? "
                "ORDER BY occurred_at, record_id LIMIT ?",
                (identity.to_canonical_text(), limit.limit),
            ).fetchall()
        return tuple(decode_record(row[0], record_type) for row in rows)


class SQLiteSkillExternalBindingStore(_SQLiteStore, SkillExternalBindingStore):
    def append_governance(
        self, record: ExternalGovernanceBindingRecord
    ) -> SkillStoreWriteOutcome:
        return self._save_external(
            "governance_bindings",
            record.occurrence_ref.value,
            record.binding_ref.value,
            record.identity,
            record.bound_at,
            record,
        )

    def append_intelligence(
        self, record: SkillIntelligenceBindingRecord
    ) -> SkillStoreWriteOutcome:
        return self._save_external(
            "intelligence_bindings",
            record.occurrence_ref.value,
            record.binding_ref.value,
            record.identity,
            record.bound_at,
            record,
        )

    def list_governance_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillGovernanceBindingHistory:
        rows, complete = self._list_external(
            "governance_bindings", identity, limit, ExternalGovernanceBindingRecord
        )
        return SkillGovernanceBindingHistory(rows, complete)

    def list_intelligence_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillIntelligenceBindingHistory:
        rows, complete = self._list_external(
            "intelligence_bindings", identity, limit, SkillIntelligenceBindingRecord
        )
        return SkillIntelligenceBindingHistory(rows, complete)

    def _save_external(
        self,
        table: str,
        occurrence_ref: str,
        binding_ref: str,
        identity: PublishedSkillVersionId,
        occurred_at: datetime,
        record: object,
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            self._assert_publication(connection, identity)
            return self._append(
                connection,
                table=table,
                key_column="occurrence_ref",
                key=occurrence_ref,
                columns=(
                    "occurrence_ref",
                    "binding_ref",
                    "exact_identity",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    occurrence_ref,
                    binding_ref,
                    identity.to_canonical_text(),
                    canonical_timestamp(occurred_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=type(record),
            )

    def _list_external(
        self,
        table: str,
        identity: PublishedSkillVersionId,
        limit: SkillStoreQueryLimit,
        record_type: type[_RecordT],
    ) -> tuple[tuple[_RecordT, ...], bool]:
        if table not in {"governance_bindings", "intelligence_bindings"}:
            raise SkillStoreUnavailable()
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table} WHERE exact_identity = ? "
                "ORDER BY occurred_at, occurrence_ref LIMIT ?",
                (identity.to_canonical_text(), limit.limit + 1),
            ).fetchall()
        return (
            tuple(decode_record(row[0], record_type) for row in rows[: limit.limit]),
            len(rows) <= limit.limit,
        )


class SQLiteSkillPrivateEvalBindingStore(
    _SQLiteStore, SkillPrivateEvalBindingStore
):
    def append_private_eval(
        self, record: SkillPrivateEvalBindingRecord
    ) -> SkillStoreWriteOutcome:
        payload = encode_record(record)
        with self._connection(write=True) as connection:
            self._assert_publication(connection, record.identity)
            return self._append(
                connection,
                table="private_eval_bindings",
                key_column="occurrence_ref",
                key=record.occurrence_ref.value,
                columns=(
                    "occurrence_ref",
                    "binding_ref",
                    "exact_identity",
                    "occurred_at",
                    "payload",
                ),
                values=(
                    record.occurrence_ref.value,
                    record.binding_ref.value,
                    record.identity.to_canonical_text(),
                    canonical_timestamp(record.bound_at),
                    payload,
                ),
                payload=payload,
                record=record,
                record_type=SkillPrivateEvalBindingRecord,
            )

    def list_private_evals_for_version(
        self, identity: PublishedSkillVersionId, limit: SkillStoreQueryLimit
    ) -> SkillPrivateEvalBindingHistory:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM private_eval_bindings WHERE exact_identity = ? "
                "ORDER BY occurred_at, occurrence_ref LIMIT ?",
                (identity.to_canonical_text(), limit.limit + 1),
            ).fetchall()
        return SkillPrivateEvalBindingHistory(
            tuple(
                decode_record(row[0], SkillPrivateEvalBindingRecord)
                for row in rows[: limit.limit]
            ),
            len(rows) <= limit.limit,
        )


def _decode_lifecycle(
    kind: str, payload: str
) -> SkillLifecycleRecord | SkillActivationRecord | SkillRevocationRecord:
    record_types = {
        "lifecycle": SkillLifecycleRecord,
        "activation": SkillActivationRecord,
        "revocation": SkillRevocationRecord,
    }
    record_type = record_types.get(kind)
    if record_type is None:
        raise SkillStoreUnavailable()
    return decode_record(payload, record_type)


def _decode_installation(
    kind: str, payload: str
) -> SkillInstallationRecord | SkillInstallationTerminationRecord:
    if kind == "installation":
        return decode_record(payload, SkillInstallationRecord)
    if kind == "termination":
        return decode_record(payload, SkillInstallationTerminationRecord)
    raise SkillStoreUnavailable()


def _decode_assignment(
    kind: str, payload: str
) -> SkillAssignmentRecord | SkillAssignmentTerminationRecord:
    if kind == "assignment":
        return decode_record(payload, SkillAssignmentRecord)
    if kind == "termination":
        return decode_record(payload, SkillAssignmentTerminationRecord)
    raise SkillStoreUnavailable()


def _decode_lease(
    kind: str, payload: str
) -> SkillLeaseRecord | SkillLeaseTerminationRecord:
    if kind == "lease":
        return decode_record(payload, SkillLeaseRecord)
    if kind == "termination":
        return decode_record(payload, SkillLeaseTerminationRecord)
    raise SkillStoreUnavailable()
