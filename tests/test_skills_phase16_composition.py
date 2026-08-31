from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from typing import cast

import pytest

from synapse.skills.application.commands import PublishSkillVersionCommand
from synapse.skills.application.queries import GetPublishedSkillVersionQuery
from synapse.skills.compatibility import SkillLegacyCompatibilityIncomplete
from synapse.skills.composition import (
    SkillsCompatibilityMode,
    SkillsCompositionClosed,
    SkillsCompositionCompatibilityUnavailable,
    SkillsCompositionConstructionFailed,
    SkillsCompositionIntegrityFailed,
    SkillsCompositionInvalidConfiguration,
    SkillsCompositionMigrationRequired,
    SkillsHealthStatus,
    SkillsIntegrityPolicy,
    SkillsMigrationPolicy,
    SkillsMigrationStatus,
    SkillsRuntimeConfiguration,
    SkillsRuntimeState,
    build_skills_runtime,
)
from synapse.skills.persistence import SkillSQLiteConfig
from synapse.skills.phase2_models import PublishedSkillVersionId, SkillSemanticReference
from synapse.skills.phase3_values import SkillStoreQueryLimit
from synapse.skills.phase4_verification import SkillPackageVerifier
from synapse.skills.phase5_models import PublishVerifiedSkillVersionRequest

NOW = datetime(2026, 7, 29, tzinfo=UTC)


def configuration(
    path: Path,
    *,
    migration: SkillsMigrationPolicy = SkillsMigrationPolicy.MIGRATE_IF_NEEDED,
    integrity: SkillsIntegrityPolicy = SkillsIntegrityPolicy.EXPLICIT_ONLY,
    compatibility: SkillsCompatibilityMode = SkillsCompatibilityMode.DISABLED,
) -> SkillsRuntimeConfiguration:
    return SkillsRuntimeConfiguration(
        SkillSQLiteConfig(path),
        migration,
        integrity,
        compatibility,
        SkillStoreQueryLimit(100),
    )


def publication_request(root: Path) -> PublishVerifiedSkillVersionRequest:
    content = b"# Composition"
    digest = hashlib.sha256(content).hexdigest()
    root.mkdir()
    (root / "SKILL.md").write_bytes(content)
    (root / "manifest.yaml").write_text(
        f"""format_version: 1
skill_id: composition-skill
version: 1.0.0
display_name: Composition skill
summary: Composition integration.
description: Verified composition integration fixture.
provenance:
  publisher_ref: publisher:test
scopes:
  - project
content:
  - logical_path: SKILL.md
    fingerprint: {digest}
    kind: instructions
    media_type: text/markdown
    size_bytes: {len(content)}
""",
        encoding="utf-8",
    )
    return PublishVerifiedSkillVersionRequest(
        snapshot=SkillPackageVerifier().verify(root),
        actor_ref=SkillSemanticReference("actor:test"),
        publication_ref=SkillSemanticReference("publication:test"),
        idempotency_ref=SkillSemanticReference("idempotency:test"),
        published_at=NOW,
    )


def test_build_migrates_empty_database_and_exposes_all_handler_groups(
    tmp_path: Path,
) -> None:
    runtime = build_skills_runtime(configuration(tmp_path / "skills.sqlite3"))
    assert runtime.state is SkillsRuntimeState.READY
    assert runtime.health().migration is SkillsMigrationStatus.APPLIED
    gateway = runtime.gateway
    assert callable(gateway.publish)
    assert callable(gateway.apply_lifecycle)
    assert callable(gateway.install)
    assert callable(gateway.bind_governance)
    assert callable(gateway.get)
    assert callable(gateway.lifecycle)
    assert callable(gateway.analyze)
    assert callable(gateway.governance)
    assert callable(gateway.build_handoff)


def test_require_current_rejects_empty_database_without_partial_runtime(
    tmp_path: Path,
) -> None:
    with pytest.raises(SkillsCompositionMigrationRequired):
        build_skills_runtime(
            configuration(
                tmp_path / "empty.sqlite3",
                migration=SkillsMigrationPolicy.REQUIRE_CURRENT,
            )
        )


def test_verify_only_accepts_current_schema(tmp_path: Path) -> None:
    path = tmp_path / "current.sqlite3"
    build_skills_runtime(configuration(path)).close()
    runtime = build_skills_runtime(
        configuration(path, migration=SkillsMigrationPolicy.VERIFY_ONLY)
    )
    assert runtime.health().schema_current
    assert runtime.health().migration is SkillsMigrationStatus.CURRENT_VERIFIED


def test_full_integrity_and_explicit_integrity_are_distinguishable(
    tmp_path: Path,
) -> None:
    full = build_skills_runtime(
        configuration(
            tmp_path / "full.sqlite3", integrity=SkillsIntegrityPolicy.FULL
        )
    )
    assert full.health().integrity is SkillsHealthStatus.HEALTHY
    explicit = build_skills_runtime(configuration(tmp_path / "explicit.sqlite3"))
    assert explicit.health().integrity is SkillsHealthStatus.NOT_CHECKED
    assert explicit.verify_integrity().integrity is SkillsHealthStatus.HEALTHY
    assert explicit.health().integrity is SkillsHealthStatus.HEALTHY


def test_compatibility_is_not_exposed_when_disabled(tmp_path: Path) -> None:
    runtime = build_skills_runtime(configuration(tmp_path / "disabled.sqlite3"))
    with pytest.raises(SkillsCompositionCompatibilityUnavailable):
        _ = runtime.compatibility
    assert not runtime.health().compatibility_enabled


def test_publish_query_compatibility_restart_and_replay(tmp_path: Path) -> None:
    path = tmp_path / "integration.sqlite3"
    request = publication_request(tmp_path / "package")
    runtime = build_skills_runtime(
        configuration(path, compatibility=SkillsCompatibilityMode.READ_ONLY)
    )
    created = runtime.gateway.publish(PublishSkillVersionCommand(request))
    exact = runtime.gateway.get(GetPublishedSkillVersionQuery(created.identity))
    assert exact.record.identity == created.identity
    assert runtime.compatibility.get_exact(created.identity).identity == created.identity
    with pytest.raises(SkillLegacyCompatibilityIncomplete):
        runtime.compatibility.list("composition-skill")
    runtime.close()

    restarted = build_skills_runtime(
        configuration(
            path,
            migration=SkillsMigrationPolicy.REQUIRE_CURRENT,
            compatibility=SkillsCompatibilityMode.READ_ONLY,
        )
    )
    replayed = restarted.gateway.publish(PublishSkillVersionCommand(request))
    assert replayed.outcome.value == "replayed"
    assert restarted.compatibility.get_exact(created.identity).identity == created.identity


def test_close_is_idempotent_and_all_access_fails_safely(tmp_path: Path) -> None:
    runtime = build_skills_runtime(
        configuration(
            tmp_path / "close.sqlite3",
            compatibility=SkillsCompatibilityMode.READ_ONLY,
        )
    )
    gateway = runtime.gateway
    compatibility = runtime.compatibility
    captured_get = gateway.get
    captured_compatibility_get = compatibility.get_exact
    runtime.close()
    runtime.close()
    assert runtime.state is SkillsRuntimeState.CLOSED
    assert runtime.health().status is SkillsHealthStatus.CLOSED
    with pytest.raises(SkillsCompositionClosed):
        _ = runtime.gateway
    with pytest.raises(SkillsCompositionClosed):
        gateway.get(cast(GetPublishedSkillVersionQuery, object()))
    with pytest.raises(SkillsCompositionClosed):
        compatibility.get_exact(cast(PublishedSkillVersionId, object()))
    with pytest.raises(SkillsCompositionClosed):
        captured_get(cast(GetPublishedSkillVersionQuery, object()))
    with pytest.raises(SkillsCompositionClosed):
        captured_compatibility_get(cast(PublishedSkillVersionId, object()))
    with pytest.raises(SkillsCompositionClosed):
        runtime.verify_integrity()


def test_context_manager_closes_and_independent_builds_are_not_singletons(
    tmp_path: Path,
) -> None:
    first = build_skills_runtime(configuration(tmp_path / "one.sqlite3"))
    second = build_skills_runtime(configuration(tmp_path / "two.sqlite3"))
    assert first is not second
    with first:
        assert first.state is SkillsRuntimeState.READY
    assert first.state is SkillsRuntimeState.CLOSED
    assert second.state is SkillsRuntimeState.READY


def test_configuration_is_frozen_and_rejects_wrong_policy_type(tmp_path: Path) -> None:
    config = configuration(tmp_path / "valid.sqlite3")
    assert str(tmp_path) not in repr(config)
    with pytest.raises((AttributeError, TypeError)):
        config.migration = SkillsMigrationPolicy.VERIFY_ONLY  # type: ignore[misc]
    with pytest.raises(SkillsCompositionInvalidConfiguration):
        SkillsRuntimeConfiguration(
            SkillSQLiteConfig(tmp_path / "invalid.sqlite3"),
            "migrate_if_needed",  # type: ignore[arg-type]
            SkillsIntegrityPolicy.FULL,
            SkillsCompatibilityMode.DISABLED,
            SkillStoreQueryLimit(100),
        )


def test_health_contains_no_path_or_sql(tmp_path: Path) -> None:
    runtime = build_skills_runtime(configuration(tmp_path / "safe.sqlite3"))
    rendered = repr(runtime.health())
    assert str(tmp_path) not in rendered
    assert "SELECT " not in rendered


def test_integrity_failure_returns_no_partial_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.composition.runtime as runtime_module

    def fail(_self: object) -> None:
        raise RuntimeError("unsafe detail")

    monkeypatch.setattr(runtime_module.SkillPersistenceIntegrityChecker, "check", fail)
    with pytest.raises(SkillsCompositionIntegrityFailed) as raised:
        build_skills_runtime(
            configuration(
                tmp_path / "integrity.sqlite3",
                integrity=SkillsIntegrityPolicy.FULL,
            )
        )
    assert "unsafe detail" not in str(raised.value)


def test_store_construction_failure_returns_no_partial_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.composition.runtime as runtime_module

    def fail(_connections: object) -> None:
        raise RuntimeError("unsafe detail")

    monkeypatch.setattr(runtime_module, "SQLiteSkillCatalogStore", fail)
    with pytest.raises(SkillsCompositionConstructionFailed) as raised:
        build_skills_runtime(configuration(tmp_path / "store.sqlite3"))
    assert "unsafe detail" not in str(raised.value)


def test_compatibility_construction_failure_returns_no_partial_composition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.composition.runtime as runtime_module

    def fail(_queries: object) -> None:
        raise RuntimeError("unsafe detail")

    monkeypatch.setattr(runtime_module, "LegacyCatalogAdapter", fail)
    with pytest.raises(SkillsCompositionConstructionFailed) as raised:
        build_skills_runtime(
            configuration(
                tmp_path / "compatibility.sqlite3",
                compatibility=SkillsCompatibilityMode.READ_ONLY,
            )
        )
    assert "unsafe detail" not in str(raised.value)


def test_failure_after_committed_migration_allows_clean_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.composition.runtime as runtime_module

    path = tmp_path / "retry.sqlite3"
    original = runtime_module.SQLiteSkillCatalogStore

    def fail(_connections: object) -> None:
        raise RuntimeError("after migration")

    monkeypatch.setattr(runtime_module, "SQLiteSkillCatalogStore", fail)
    with pytest.raises(SkillsCompositionConstructionFailed):
        build_skills_runtime(configuration(path))
    monkeypatch.setattr(runtime_module, "SQLiteSkillCatalogStore", original)
    retried = build_skills_runtime(configuration(path))
    assert retried.health().migration is SkillsMigrationStatus.CURRENT_VERIFIED


def test_disabled_mode_does_not_construct_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import synapse.skills.composition.runtime as runtime_module

    def fail(_queries: object) -> None:
        raise AssertionError("compatibility must not be built")

    monkeypatch.setattr(runtime_module, "LegacyCatalogAdapter", fail)
    runtime = build_skills_runtime(configuration(tmp_path / "disabled-spy.sqlite3"))
    assert not runtime.health().compatibility_enabled


def test_two_compositions_same_database_have_independent_close_state(
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared.sqlite3"
    first = build_skills_runtime(configuration(path))
    second = build_skills_runtime(configuration(path))
    first.close()
    assert second.state is SkillsRuntimeState.READY
    assert second.verify_integrity().status is SkillsHealthStatus.HEALTHY


def test_explicit_integrity_detects_corruption_after_startup(tmp_path: Path) -> None:
    path = tmp_path / "later-corrupt.sqlite3"
    runtime = build_skills_runtime(configuration(path))
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TRIGGER publications_no_update")
    with pytest.raises(SkillsCompositionIntegrityFailed):
        runtime.verify_integrity()


def test_operation_started_before_close_may_finish_but_new_operation_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_skills_runtime(configuration(tmp_path / "concurrent.sqlite3"))
    gateway = runtime.gateway
    entered = Event()
    release = Event()

    def blocked(_query: object) -> object:
        entered.set()
        assert release.wait(2)
        raise RuntimeError("operation reached handler")

    monkeypatch.setattr(gateway._catalog, "get", blocked)
    errors: list[Exception] = []

    def call() -> None:
        try:
            gateway.get(cast(GetPublishedSkillVersionQuery, object()))
        except Exception as exc:
            errors.append(exc)

    worker = Thread(target=call)
    worker.start()
    assert entered.wait(2)
    runtime.close()
    with pytest.raises(SkillsCompositionClosed):
        gateway.get(cast(GetPublishedSkillVersionQuery, object()))
    release.set()
    worker.join(2)
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_health_reports_unavailable_from_a_real_failed_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = build_skills_runtime(configuration(tmp_path / "health.sqlite3"))

    def fail() -> object:
        raise RuntimeError("unsafe path")

    monkeypatch.setattr(runtime._connections, "connection", fail)
    health = runtime.health()
    assert health.status is SkillsHealthStatus.UNAVAILABLE
    assert not health.database_reachable
    assert "unsafe path" not in repr(health)
