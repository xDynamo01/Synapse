"""Append-only durable host facts and pure restart reconciliation for the Windows driver."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import cast

from synapse.sandbox import OpaqueReference, SandboxWorkspaceId

SCHEMA_VERSION = 1
SCHEMA_ID = "windows-sandbox-driver-state-v1"


class WindowsDriverEventType(StrEnum):
    ATTEMPT_CREATED = "attempt_created"
    JOB_CREATED = "job_created"
    JOB_CONFIGURED = "job_configured"
    PROCESS_CREATED = "process_created"
    CONTAINMENT_VERIFIED = "containment_verified"
    PROCESS_RESUMED = "process_resumed"
    OUTPUT_CAPTURE_OBSERVED = "output_capture_observed"
    RESOURCE_POLICY_OBSERVED = "resource_policy_observed"
    NETWORK_POLICY_OBSERVED = "network_policy_observed"
    SECRET_STATE_OBSERVED = "secret_state_observed"
    PUBLICATION_STATE_OBSERVED = "publication_state_observed"
    CLEANUP_STATE_OBSERVED = "cleanup_state_observed"
    TERMINATION_PROVEN = "termination_proven"
    ATTEMPT_COMPLETED = "attempt_completed"


class WindowsRestartClassification(StrEnum):
    NEVER_STARTED = "never_started"
    COMPLETED_BEFORE_RESTART = "completed_before_restart"
    TERMINATED_AND_PROVEN = "terminated_and_proven"
    STARTED_BUT_HANDLES_LOST = "started_but_handles_lost"
    PUBLICATION_INCOMPLETE = "publication_incomplete"
    CLEANUP_INCOMPLETE = "cleanup_incomplete"
    SECRET_REVOCATION_UNPROVEN = "secret_revocation_unproven"
    OUTPUT_CAPTURE_INCOMPLETE = "output_capture_incomplete"
    RECONCILIATION_REQUIRED = "reconciliation_required"
    ORPHANED = "orphaned"


class WindowsReconciliationAction(StrEnum):
    MANUAL_PROCESS_RECONCILIATION = "manual_process_reconciliation"
    VERIFY_PUBLICATION_METADATA = "verify_publication_metadata"
    INSPECT_CONTROLLED_TEMP_RESIDUALS = "inspect_controlled_temp_residuals"
    OBTAIN_CURRENT_CLEANUP_AUTHORITY = "obtain_current_cleanup_authority"
    VERIFY_SECRET_REVOCATION_EXTERNALLY = "verify_secret_revocation_externally"
    ACCEPT_OUTPUT_CAPTURE_LOSS = "accept_output_capture_loss"


@dataclass(frozen=True, slots=True)
class WindowsDriverDurableEventV1:
    event_reference: OpaqueReference
    driver_attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    sequence: int
    event_type: WindowsDriverEventType
    occurred_at: datetime
    process_created: bool = False
    job_created: bool = False
    job_configured: bool = False
    containment_verified: bool = False
    process_resumed: bool = False
    historical_root_pid: int | None = None
    output_capture_state: str | None = None
    resource_policy_state: str | None = None
    network_policy_state: str | None = None
    secret_state: str | None = None
    publication_state: str | None = None
    cleanup_state: str | None = None
    termination_proof_reference: OpaqueReference | None = None
    safe_references: tuple[OpaqueReference, ...] = ()

    def __post_init__(self) -> None:
        if self.sequence < 1 or self.occurred_at.tzinfo is None:
            raise ValueError("driver_event_invalid")
        if self.historical_root_pid is not None and self.historical_root_pid <= 0:
            raise ValueError("historical_pid_invalid")

    def content(self) -> dict[str, object]:
        return {
            "event_reference": self.event_reference.value,
            "driver_attempt_reference": self.driver_attempt_reference.value,
            "workspace_id": self.workspace_id.value,
            "sequence": self.sequence,
            "event_type": self.event_type.value,
            "occurred_at": self.occurred_at.isoformat(),
            "process_created": self.process_created,
            "job_created": self.job_created,
            "job_configured": self.job_configured,
            "containment_verified": self.containment_verified,
            "process_resumed": self.process_resumed,
            "historical_root_pid": self.historical_root_pid,
            "output_capture_state": self.output_capture_state,
            "resource_policy_state": self.resource_policy_state,
            "network_policy_state": self.network_policy_state,
            "secret_state": self.secret_state,
            "publication_state": self.publication_state,
            "cleanup_state": self.cleanup_state,
            "termination_proof_reference": self.termination_proof_reference.value
            if self.termination_proof_reference
            else None,
            "safe_references": [item.value for item in self.safe_references],
        }


@dataclass(frozen=True, slots=True)
class WindowsDriverStoreHealth:
    store_available: bool
    schema_compatible: bool
    replay_available: bool
    integrity_valid: bool
    restart_projection_available: bool
    live_handle_recovery_available: bool
    orphan_detection_available: bool
    reconciliation_planning_available: bool
    automatic_destructive_reconciliation_enabled: bool
    diagnostic_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsRestartProjectionV1:
    driver_attempt_reference: OpaqueReference
    workspace_id: SandboxWorkspaceId
    classifications: tuple[WindowsRestartClassification, ...]
    historical_root_pid: int | None
    termination_proof_reference: OpaqueReference | None
    output_capture_state: str | None
    resource_policy_state: str | None
    network_policy_state: str | None
    secret_state: str | None
    publication_state: str | None
    cleanup_state: str | None
    historical_event_count: int
    handles_recoverable: bool = False
    reconciliation_required: bool = False


@dataclass(frozen=True, slots=True)
class WindowsReconciliationPlanV1:
    projection: WindowsRestartProjectionV1
    required_actions: tuple[WindowsReconciliationAction, ...]
    automatic_actions: tuple[WindowsReconciliationAction, ...] = ()


class WindowsDriverStateIntegrityError(RuntimeError):
    pass


class WindowsSandboxDriverStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._initialized = False

    def initialize(self) -> WindowsDriverStoreHealth:
        self._initialize()
        self._initialized = True
        health = self.health()
        if not health.schema_compatible or not health.integrity_valid:
            raise WindowsDriverStateIntegrityError(
                health.diagnostic_codes[0] if health.diagnostic_codes else "driver_store_invalid"
            )
        return health

    def append(self, event: WindowsDriverDurableEventV1) -> bool:
        self._require_initialized()
        payload = self._encode(event)
        checksum = self._checksum(payload)
        with self._connect() as connection:
            self._require_compatible(connection)
            existing = connection.execute(
                "SELECT payload, checksum FROM driver_events WHERE event_reference = ?",
                (event.event_reference.value,),
            ).fetchone()
            if existing is not None:
                if existing == (payload, checksum):
                    return False
                raise WindowsDriverStateIntegrityError("driver_event_contradiction")
            latest = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) FROM driver_events WHERE attempt_reference = ?",
                (event.driver_attempt_reference.value,),
            ).fetchone()[0]
            if event.sequence != latest + 1:
                raise WindowsDriverStateIntegrityError("driver_event_sequence_invalid")
            connection.execute(
                "INSERT INTO driver_events(event_reference, attempt_reference, workspace_id, sequence, event_type, occurred_at, payload, checksum) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_reference.value,
                    event.driver_attempt_reference.value,
                    event.workspace_id.value,
                    event.sequence,
                    event.event_type.value,
                    event.occurred_at.isoformat(),
                    payload,
                    checksum,
                ),
            )
        return True

    def replay(self) -> tuple[WindowsDriverDurableEventV1, ...]:
        self._require_initialized()
        try:
            with self._connect() as connection:
                self._require_compatible(connection)
                rows = connection.execute(
                    "SELECT payload, checksum FROM driver_events ORDER BY attempt_reference COLLATE BINARY, sequence"
                ).fetchall()
        except sqlite3.DatabaseError as error:
            raise WindowsDriverStateIntegrityError("driver_store_corrupt") from error
        events: list[WindowsDriverDurableEventV1] = []
        sequences: dict[OpaqueReference, int] = {}
        for payload, checksum in rows:
            if self._checksum(payload) != checksum:
                raise WindowsDriverStateIntegrityError("driver_event_checksum_invalid")
            try:
                event = self._decode(payload)
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
                raise WindowsDriverStateIntegrityError("driver_event_payload_invalid") from error
            expected = sequences.get(event.driver_attempt_reference, 0) + 1
            if event.sequence != expected:
                raise WindowsDriverStateIntegrityError("driver_event_sequence_invalid")
            sequences[event.driver_attempt_reference] = event.sequence
            events.append(event)
        return tuple(events)

    def health(self) -> WindowsDriverStoreHealth:
        if not self._initialized or not self._path.exists():
            return WindowsDriverStoreHealth(
                False, False, False, False, False, False, False, False, False,
                ("driver_store_not_initialized",),
            )
        diagnostics: tuple[str, ...] = ()
        compatible = integrity = True
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT schema_version, schema_id FROM driver_schema"
                ).fetchone()
            compatible = row == (SCHEMA_VERSION, SCHEMA_ID)
            if not compatible:
                diagnostics = ("driver_schema_incompatible",)
            else:
                self.replay()
        except (sqlite3.DatabaseError, WindowsDriverStateIntegrityError):
            integrity = False
            diagnostics = ("driver_store_integrity_invalid",)
        return WindowsDriverStoreHealth(
            True,
            compatible,
            compatible and integrity,
            integrity,
            compatible and integrity,
            False,
            compatible and integrity,
            compatible and integrity,
            False,
            diagnostics,
        )

    def _initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS driver_schema(
                    schema_version INTEGER NOT NULL,
                    schema_id TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS driver_events(
                    event_reference TEXT PRIMARY KEY,
                    attempt_reference TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    checksum TEXT NOT NULL,
                    UNIQUE(attempt_reference, sequence)
                );
                CREATE TRIGGER IF NOT EXISTS driver_events_no_update
                BEFORE UPDATE ON driver_events BEGIN SELECT RAISE(ABORT, 'append_only'); END;
                CREATE TRIGGER IF NOT EXISTS driver_events_no_delete
                BEFORE DELETE ON driver_events BEGIN SELECT RAISE(ABORT, 'append_only'); END;
                """
            )
            row = connection.execute("SELECT COUNT(*) FROM driver_schema").fetchone()[0]
            if row == 0:
                connection.execute(
                    "INSERT INTO driver_schema(schema_version, schema_id) VALUES (?, ?)",
                    (SCHEMA_VERSION, SCHEMA_ID),
                )
            elif row != 1:
                raise WindowsDriverStateIntegrityError("driver_schema_invalid")

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise WindowsDriverStateIntegrityError("driver_store_not_initialized")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _require_compatible(connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT schema_version, schema_id FROM driver_schema").fetchone()
        if row != (SCHEMA_VERSION, SCHEMA_ID):
            raise WindowsDriverStateIntegrityError("driver_schema_incompatible")

    @staticmethod
    def _encode(event: WindowsDriverDurableEventV1) -> str:
        return json.dumps(event.content(), sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _checksum(payload: str) -> str:
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _decode(payload: str) -> WindowsDriverDurableEventV1:
        item = json.loads(payload)
        return WindowsDriverDurableEventV1(
            OpaqueReference(item["event_reference"]),
            OpaqueReference(item["driver_attempt_reference"]),
            SandboxWorkspaceId(item["workspace_id"]),
            item["sequence"],
            WindowsDriverEventType(item["event_type"]),
            datetime.fromisoformat(item["occurred_at"]),
            item["process_created"],
            item["job_created"],
            item["job_configured"],
            item["containment_verified"],
            item["process_resumed"],
            item["historical_root_pid"],
            item["output_capture_state"],
            item["resource_policy_state"],
            item["network_policy_state"],
            item["secret_state"],
            item["publication_state"],
            item["cleanup_state"],
            OpaqueReference(item["termination_proof_reference"])
            if item["termination_proof_reference"]
            else None,
            tuple(OpaqueReference(value) for value in item["safe_references"]),
        )


class WindowsSandboxReconciliationPlanner:
    def project(
        self, events: tuple[WindowsDriverDurableEventV1, ...]
    ) -> tuple[WindowsRestartProjectionV1, ...]:
        grouped: dict[OpaqueReference, list[WindowsDriverDurableEventV1]] = {}
        for event in events:
            grouped.setdefault(event.driver_attempt_reference, []).append(event)
        return tuple(
            self._projection(tuple(grouped[attempt]))
            for attempt in sorted(grouped, key=lambda item: item.value)
        )

    def plan(self, projection: WindowsRestartProjectionV1) -> WindowsReconciliationPlanV1:
        states = set(projection.classifications)
        actions: set[WindowsReconciliationAction] = set()
        if WindowsRestartClassification.ORPHANED in states:
            actions.add(WindowsReconciliationAction.MANUAL_PROCESS_RECONCILIATION)
        if WindowsRestartClassification.PUBLICATION_INCOMPLETE in states:
            actions.add(WindowsReconciliationAction.VERIFY_PUBLICATION_METADATA)
            actions.add(WindowsReconciliationAction.INSPECT_CONTROLLED_TEMP_RESIDUALS)
        if WindowsRestartClassification.CLEANUP_INCOMPLETE in states:
            actions.add(WindowsReconciliationAction.OBTAIN_CURRENT_CLEANUP_AUTHORITY)
            actions.add(WindowsReconciliationAction.INSPECT_CONTROLLED_TEMP_RESIDUALS)
        if WindowsRestartClassification.SECRET_REVOCATION_UNPROVEN in states:
            actions.add(WindowsReconciliationAction.VERIFY_SECRET_REVOCATION_EXTERNALLY)
        if WindowsRestartClassification.OUTPUT_CAPTURE_INCOMPLETE in states:
            actions.add(WindowsReconciliationAction.ACCEPT_OUTPUT_CAPTURE_LOSS)
        return WindowsReconciliationPlanV1(
            projection, tuple(sorted(actions, key=lambda item: item.value)), ()
        )

    @staticmethod
    def _projection(events: tuple[WindowsDriverDurableEventV1, ...]) -> WindowsRestartProjectionV1:
        first = events[0]
        latest: dict[str, object] = {}
        kinds = {event.event_type for event in events}
        for event in events:
            for name in (
                "historical_root_pid",
                "output_capture_state",
                "resource_policy_state",
                "network_policy_state",
                "secret_state",
                "publication_state",
                "cleanup_state",
                "termination_proof_reference",
            ):
                value = getattr(event, name)
                if value is not None:
                    latest[name] = value
        states: set[WindowsRestartClassification] = set()
        resumed = WindowsDriverEventType.PROCESS_RESUMED in kinds
        proof = latest.get("termination_proof_reference")
        if not resumed:
            states.add(WindowsRestartClassification.NEVER_STARTED)
        elif proof is not None:
            states.add(WindowsRestartClassification.TERMINATED_AND_PROVEN)
            if WindowsDriverEventType.ATTEMPT_COMPLETED in kinds:
                states.add(WindowsRestartClassification.COMPLETED_BEFORE_RESTART)
        else:
            states.update(
                {
                    WindowsRestartClassification.STARTED_BUT_HANDLES_LOST,
                    WindowsRestartClassification.ORPHANED,
                    WindowsRestartClassification.RECONCILIATION_REQUIRED,
                }
            )
        publication = latest.get("publication_state")
        if publication in {
            "candidate",
            "custody_accepted",
            "publication_requested",
            "publication_unverified",
            "publication_failed",
        }:
            states.add(WindowsRestartClassification.PUBLICATION_INCOMPLETE)
        cleanup = latest.get("cleanup_state")
        if cleanup in {"requested", "in_progress", "partial", "failed", "unverified"}:
            states.add(WindowsRestartClassification.CLEANUP_INCOMPLETE)
        if latest.get("secret_state") in {"revocation_requested", "revocation_unproven"}:
            states.add(WindowsRestartClassification.SECRET_REVOCATION_UNPROVEN)
        if latest.get("output_capture_state") in {"capturing", "finalization_incomplete"}:
            states.add(WindowsRestartClassification.OUTPUT_CAPTURE_INCOMPLETE)
        if states & {
            WindowsRestartClassification.PUBLICATION_INCOMPLETE,
            WindowsRestartClassification.CLEANUP_INCOMPLETE,
            WindowsRestartClassification.SECRET_REVOCATION_UNPROVEN,
            WindowsRestartClassification.OUTPUT_CAPTURE_INCOMPLETE,
        }:
            states.add(WindowsRestartClassification.RECONCILIATION_REQUIRED)
        return WindowsRestartProjectionV1(
            first.driver_attempt_reference,
            first.workspace_id,
            tuple(sorted(states, key=lambda item: item.value)),
            cast(int | None, latest.get("historical_root_pid")),
            cast(OpaqueReference | None, proof),
            cast(str | None, latest.get("output_capture_state")),
            cast(str | None, latest.get("resource_policy_state")),
            cast(str | None, latest.get("network_policy_state")),
            cast(str | None, latest.get("secret_state")),
            cast(str | None, publication),
            cast(str | None, cleanup),
            len(events),
            False,
            WindowsRestartClassification.RECONCILIATION_REQUIRED in states,
        )
