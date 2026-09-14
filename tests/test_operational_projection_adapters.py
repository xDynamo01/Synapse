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


def test_local_chat_projects_factual_request_and_response_direction() -> None:
    payload: dict[str, object] = {"agent_id": "artemis", "provider_id": "synapse_local", "model_name": "deepseek"}
    for event_type, source, target in [
        ("local_chat.thinking", "agent:artemis", "runtime:synapse_local:deepseek"),
        ("local_chat.completed", "runtime:synapse_local:deepseek", "agent:artemis"),
    ]:
        result = adapt_source_record(record(event_type=event_type, payload=payload), 1)
        assert result.fact is not None
        assert result.fact.metadata["transfer_source"] == source
        assert result.fact.metadata["transfer_target"] == target
    failure = adapt_source_record(record(event_type="local_chat.request_failed", payload=payload), 1)
    assert failure.fact is not None
    assert "transfer_source" not in failure.fact.metadata


def test_local_chat_does_not_invent_direction_without_agent_identity() -> None:
    result = adapt_source_record(record(event_type="local_chat.thinking", payload={"provider_id": "synapse_local", "model_name": "deepseek"}), 1)
    assert result.fact is not None
    assert "transfer_source" not in result.fact.metadata


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


def test_local_chat_completed_preserves_safe_model_metrics() -> None:
    result = adapt_source_record(
        record(
            event_type="local_chat.completed",
            project_id="conversation:abc",
            payload={
                "agent_id": "artemis",
                "provider_id": "lmstudio",
                "model_name": "deepseek/deepseek-r1-0528-qwen3-8b",
                "status": "completed",
                "phase": "completed",
                "current_operation": "Response generated",
                "input_count": 353,
                "output_count": 295,
                "total_count": 648,
                "latency_ms": 6457,
                "first_output_ms": 686,
                "output_rate": 48.97,
                "finish_reason": "stop",
                "reasoning_content": "must never cross the adapter",
            },
        ),
        3,
    )

    assert result.disposition is SourceAdaptationDisposition.ADAPTED
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.entity.entity_id == "runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b"
    assert result.fact.entity.status is OperationalStatus.COMPLETED
    assert result.fact.entity.metadata["input_count"] == 353
    assert result.fact.entity.metadata["output_count"] == 295
    assert result.fact.entity.metadata["total_count"] == 648
    assert result.fact.entity.metadata["latency_ms"] == 6457
    assert result.fact.entity.metadata["first_output_ms"] == 686
    assert result.fact.entity.metadata["output_rate"] == 48.97
    assert result.fact.entity.metadata["finish_reason"] == "stop"
    assert result.fact.entity.metadata["phase"] == "completed"
    assert "reasoning_content" not in result.fact.entity.metadata


def test_lmstudio_native_phase_maps_to_model_runtime_activity() -> None:
    result = adapt_source_record(
        record(
            event_type="lmstudio.native.reasoning",
            project_id="conversation:abc",
            payload={
                "agent_id": "artemis",
                "provider_id": "lmstudio",
                "model_name": "deepseek/deepseek-r1-0528-qwen3-8b",
                "status": "processing",
                "phase": "reasoning",
                "current_operation": "Reasoning",
                "current_task": "Model reasoning in progress",
                "reasoning_content": "must never cross the adapter",
            },
        ),
        4,
    )

    assert result.disposition is SourceAdaptationDisposition.ADAPTED
    assert result.fact is not None and result.fact.entity is not None
    assert result.fact.entity.entity_id == "runtime:lmstudio:deepseek/deepseek-r1-0528-qwen3-8b"
    assert result.fact.entity.status is OperationalStatus.PROCESSING
    assert result.fact.entity.metadata["phase"] == "reasoning"
    assert "reasoning_content" not in result.fact.entity.metadata
