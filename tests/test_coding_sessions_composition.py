import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from tests.test_coding_sessions_sqlite import _append_request, _record, _session

from synapse.coding_sessions import (
    CodingSessionExactRecordReadRequest,
    CodingSessionPersistenceStream,
    CodingSessionRecordAppendStatus,
)
from synapse.coding_sessions_composition import (
    CodingSessionsCapability,
    CodingSessionsCapabilityState,
    CodingSessionsRuntimeBuilder,
    CodingSessionsRuntimeBuildError,
    CodingSessionsRuntimeClosedError,
    CodingSessionsRuntimeConfig,
)


def _config(tmp_path: Path, **changes) -> CodingSessionsRuntimeConfig:
    base = CodingSessionsRuntimeConfig(
        persistence_path=(tmp_path / "coding-sessions.db").resolve(),
        persistence_reference="coding-sessions:test",
        migration_applied_at="2026-08-10T12:00:00Z",
    )
    return replace(base, **changes)


def _states(runtime) -> dict[CodingSessionsCapability, CodingSessionsCapabilityState]:
    return {item.capability: item.state for item in runtime.health().integrations}


def test_minimal_configuration_builds_without_emitting_domain_operations(tmp_path: Path) -> None:
    runtime = CodingSessionsRuntimeBuilder().build(_config(tmp_path))

    health = runtime.health()
    assert health.open and health.persistence_available and health.schema_valid
    assert runtime.domain.contracts is not None
    assert runtime.integrations.repository is None
    states = _states(runtime)
    assert states[CodingSessionsCapability.PERSISTENCE] is CodingSessionsCapabilityState.SUPPORTED
    assert states[CodingSessionsCapability.REPOSITORY_RUNTIME] is CodingSessionsCapabilityState.UNAVAILABLE


def test_full_reference_integrations_are_explicit_and_factual(tmp_path: Path) -> None:
    enabled = frozenset(
        {
            CodingSessionsCapability.REPOSITORY_RUNTIME,
            CodingSessionsCapability.GOVERNANCE_APPROVALS,
            CodingSessionsCapability.WORKERS_MISSIONS,
            CodingSessionsCapability.SANDBOX_REFERENCES,
            CodingSessionsCapability.PRIVATE_EVALS,
            CodingSessionsCapability.DEPLOYMENT_REFERENCES,
        }
    )
    runtime = CodingSessionsRuntimeBuilder().build(
        _config(tmp_path, enabled_integrations=enabled)
    )
    states = _states(runtime)

    assert runtime.integrations.repository is not None
    assert runtime.integrations.governance is not None
    assert runtime.integrations.workers_missions is not None
    assert runtime.integrations.sandbox is not None
    assert runtime.integrations.private_evals is not None
    assert runtime.integrations.deployment is not None
    assert states[CodingSessionsCapability.DEPLOYMENT_REFERENCES] is CodingSessionsCapabilityState.DEGRADED
    assert states[CodingSessionsCapability.DEPLOYMENT_RUNTIME] is CodingSessionsCapabilityState.UNAVAILABLE
    assert states[CodingSessionsCapability.SANDBOX_CONCRETE_EXECUTION] is CodingSessionsCapabilityState.UNAVAILABLE


def test_invalid_configuration_and_forbidden_concrete_capabilities_fail_closed(
    tmp_path: Path,
) -> None:
    builder = CodingSessionsRuntimeBuilder()
    with pytest.raises(CodingSessionsRuntimeBuildError):
        builder.build(_config(tmp_path, migration_checksum="sha256:invalid"))
    with pytest.raises(CodingSessionsRuntimeBuildError):
        builder.build(_config(tmp_path, sandbox_driver_available=True))
    with pytest.raises(CodingSessionsRuntimeBuildError):
        builder.build(_config(tmp_path, deployment_runtime_available=True))


def test_migration_mismatch_fails_before_runtime_is_exposed(tmp_path: Path) -> None:
    config = _config(tmp_path)
    with sqlite3.connect(config.persistence_path) as connection:
        connection.execute("PRAGMA user_version=1")
    with pytest.raises(CodingSessionsRuntimeBuildError):
        CodingSessionsRuntimeBuilder().build(config)


class _Resource:
    def __init__(self, *, close_fails: bool = False) -> None:
        self.opened = False
        self.closed = False
        self.close_fails = close_fails

    def open(self) -> None:
        self.opened = True

    def close(self) -> None:
        self.closed = True
        if self.close_fails:
            raise RuntimeError("close failed")

    def healthy(self) -> bool:
        return self.opened and not self.closed


def test_partial_build_failure_closes_already_open_resources(tmp_path: Path) -> None:
    resource = _Resource()

    def unavailable_database(_config):
        raise RuntimeError("database unavailable")

    with pytest.raises(CodingSessionsRuntimeBuildError):
        CodingSessionsRuntimeBuilder(database_factory=unavailable_database).build(
            _config(tmp_path, managed_resources=(resource,))
        )
    assert resource.opened and resource.closed


def test_restart_preserves_intermediate_lifecycle_record_exactly(tmp_path: Path) -> None:
    config = _config(tmp_path)
    first = CodingSessionsRuntimeBuilder().build(config)
    record = _record(
        1,
        stream=CodingSessionPersistenceStream.LIFECYCLE_COORDINATION,
        category="lifecycle-suspended",
    )
    assessment = first.persistence.lifecycle.append_lifecycle_record(
        _append_request(record)
    )
    assert assessment.status is CodingSessionRecordAppendStatus.APPENDED
    first.close()

    restarted = CodingSessionsRuntimeBuilder().build(config)
    result = restarted.persistence.lifecycle.read_exact(
        CodingSessionExactRecordReadRequest(
            _session(), record.stream, record.record_identity, record.record_fingerprint
        )
    )
    assert result.record == record


def test_close_is_idempotent_and_use_after_close_is_rejected(tmp_path: Path) -> None:
    resource = _Resource()
    runtime = CodingSessionsRuntimeBuilder().build(
        _config(tmp_path, managed_resources=(resource,))
    )
    runtime.close()
    runtime.close()

    assert resource.closed
    assert not runtime.health().open
    with pytest.raises(CodingSessionsRuntimeClosedError):
        _ = runtime.persistence
    with pytest.raises(CodingSessionsRuntimeClosedError):
        _ = runtime.integrations


def test_runtime_has_no_generic_execute_or_implicit_authority_selection(tmp_path: Path) -> None:
    runtime = CodingSessionsRuntimeBuilder().build(_config(tmp_path))
    assert not hasattr(runtime, "execute")
    assert not hasattr(runtime, "current_repository")
    assert not hasattr(runtime, "selected_worker")
    assert not hasattr(runtime, "authorize")
    assert not hasattr(runtime, "complete_session")
