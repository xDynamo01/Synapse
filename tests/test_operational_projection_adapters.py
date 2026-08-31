from synapse.operational_projection import (
    OperationalSourceRecord,
    OperationalStatus,
    SourceAdaptationDisposition,
    adapt_source_record,
)

NOW = "2026-08-20T12:00:00+00:00"


def record(
    *,
    event_type: str = "agent.started",
    project_id: str | None = "synapse",
    payload: dict[str, object] | None = None,
) -> OperationalSourceRecord:
    return OperationalSourceRecord(
        event_id="event:agent-started",
        event_type=event_type,
        actor_id="backend",
        occurred_at=NOW,
        project_id=project_id,
        payload=payload
        or {
            "agent_id": "backend",
            "role": "coding",
            "status": "running",
            "current_task": "Refactor service",
            "file_count": 12,
            "prompt": "must never cross the adapter",
        },
        source_reference="event-log:event:agent-started",
    )


def test_adapter_requires_explicit_project_scope() -> None:
    result = adapt_source_record(record(project_id=None), 1)
    assert result.disposition is SourceAdaptationDisposition.PROJECT_SCOPE_UNKNOWN
    assert result.fact is None


def test_adapter_minimizes_payload_and_preserves_source_reference() -> None:
    result = adapt_source_record(record(), 1)
    assert result.disposition is SourceAdaptationDisposition.ADAPTED
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.source_reference == "event-log:event:agent-started"
    assert result.fact.entity.status is OperationalStatus.RUNNING
    assert result.fact.entity.resources.files == 12
    assert "prompt" not in result.fact.metadata
    assert "prompt" not in result.fact.entity.metadata


def test_unknown_status_stays_unknown_instead_of_being_invented() -> None:
    result = adapt_source_record(record(payload={"agent_id": "backend", "status": "busy"}), 1)
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.entity.status is OperationalStatus.UNKNOWN


def test_unmapped_event_is_unsupported() -> None:
    result = adapt_source_record(record(event_type="unmapped.happened"), 1)
    assert result.disposition is SourceAdaptationDisposition.UNSUPPORTED


def test_presence_update_maps_to_primary_agent_activity() -> None:
    result = adapt_source_record(
        record(
            event_type="presence.updated",
            project_id="conversation:abc",
            payload={
                "agent_id": "artemis",
                "state": "thinking",
                "activity": "Generating agent response",
                "current_session_id": "abc",
            },
        ),
        1,
    )

    assert result.disposition is SourceAdaptationDisposition.ADAPTED
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.entity.entity_id == "agent:artemis"
    assert result.fact.entity.status is OperationalStatus.PROCESSING
    assert result.fact.entity.current_operation == "Generating agent response"


def test_chat_response_generated_maps_to_model_runtime_activity() -> None:
    result = adapt_source_record(
        record(
            event_type="chat.response_generated",
            project_id="conversation:abc",
            payload={
                "agent_id": "artemis",
                "model": {"provider": "lmstudio", "model": "deepseek/deepseek-r1-0528-qwen3-8b"},
                "session_id": "abc",
            },
        ),
        2,
    )

    assert result.disposition is SourceAdaptationDisposition.ADAPTED
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.entity.entity_id == "runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b"
    assert result.fact.entity.parent_entity_id == "agent:artemis"
    assert result.fact.entity.status is OperationalStatus.COMPLETED
