from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

import pytest

from synapse.context_fusion.contracts import (
    ContextFusionSettings,
    ConversationContextRead,
    MemoryContextRead,
    MissionRead,
    MissionSummaryRead,
    PerceptionObservationRead,
    PerceptionSignalRead,
)
from synapse.context_fusion.errors import ContextSourceUnavailable
from synapse.context_fusion.runtime import ContextFusionRuntime
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext
from synapse.observability.correlation import (
    correlation_scope,
    current_correlation,
    new_correlation,
)


class Events:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict]] = []

    def emit(self, event_type: str, _actor: str, payload: dict):
        self.items.append((event_type, payload))


class Conversations:
    def __init__(self, *, delay: float = 0, failure: Exception | None = None) -> None:
        self.delay = delay
        self.failure = failure
        self.correlation_id: str | None = None

    def participants(self, conversation_id: str) -> list[str]:
        time.sleep(self.delay)
        self.correlation_id = (
            current_correlation().correlation_id if current_correlation() else None
        )
        if self.failure:
            raise self.failure
        if conversation_id == "missing":
            raise NotFound("Conversation not found: missing")
        return ["agent-a"]

    def read(self, conversation_id: str) -> ConversationContextRead:
        self.participants(conversation_id)
        return ConversationContextRead(
            participants=["agent-a"],
            summary={"conversation_id": conversation_id, "summary": "summary text"},
            messages=[{"message_id": "m1", "role": "user", "payload": {"body": "hello"}}],
        )


class Missions:
    def get_mission(self, mission_id: str) -> MissionRead:
        if mission_id == "missing":
            raise NotFound("Mission not found: missing")
        return MissionRead(None, "owner", {"mission_id": mission_id})

    def list_task_ids(self, _mission_id: str) -> list[str]:
        return []

    def get_task(self, _task_id: str):
        raise NotFound("Task not found")

    def summarize(self, mission_id: str) -> MissionSummaryRead:
        return MissionSummaryRead({"mission_id": mission_id}, {"health": "healthy"})


class Perception:
    def __init__(self, available: bool = False) -> None:
        self.available = available

    def list_signals(self) -> list[PerceptionSignalRead]:
        if not self.available:
            return []
        return [
            PerceptionSignalRead(
                type="speech",
                modality="audio",
                source="mock",
                values={"speech_features": {"duration_ms": 100}},
                id="sig-1",
                timestamp="2026-01-01T00:00:00+00:00",
                conversation_id="c1",
                confidence=0.8,
                provenance=[{"provider": "mock"}],
                sensitivity="sensitive",
                correlation_id="corr-1",
            )
        ]

    def list_observations(self, **_kwargs) -> list[PerceptionObservationRead]:
        if not self.available:
            return []
        return [
            PerceptionObservationRead(
                id="obs-1",
                content="observed",
                type="speech",
                confidence=0.8,
                relevance=0.7,
                provenance=[{"signal_id": "sig-1"}],
                sensitivity="sensitive",
                valid_until=None,
                warnings=[],
                signal_ids=["sig-1"],
            )
        ]


class Multimodal:
    def participants(self, session_id: str) -> list[str]:
        if session_id == "missing":
            raise NotFound("Multimodal session not found: missing")
        return ["user"]


class Status:
    def health_summary(self) -> dict:
        return {"status": "healthy"}

    def readiness_summary(self) -> dict:
        return {"ready": True}


class Memory:
    def retrieve(self, *_args) -> list[MemoryContextRead]:
        return [MemoryContextRead("mem-1", "session", "remembered fact", 10, None, 2, "manual")]


class DuplicateMemory(Memory):
    def retrieve(self, *_args) -> list[MemoryContextRead]:
        return [MemoryContextRead("mem-duplicate", "session", "hello", 10, None, 1, "manual")]


class RecordingMemory(Memory):
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], int, dict | None]] = []

    def retrieve(
        self,
        _permission_context,
        query: str,
        scopes: list[str],
        _owner_ids: list[str],
        limit: int,
        filters: dict | None = None,
    ) -> list[MemoryContextRead]:
        self.calls.append((query, scopes, limit, filters))
        return [
            MemoryContextRead(
                f"knowledge-{index}",
                "knowledge",
                f"selected evidence {index}",
                10,
                None,
                index,
                f"project_document:doc:v1:chunk{index}",
                ["project_knowledge", "project:project-a"],
                {
                    "document_id": "doc",
                    "version_id": "v1",
                    "chunk_id": f"chunk{index}",
                    "trusted_instruction": False,
                },
            )
            for index in range(limit)
        ]


def make_runtime(
    tmp_path: Path,
    *,
    conversations=None,
    perception=None,
    memory=None,
    timeout: float = 1,
) -> ContextFusionRuntime:
    return ContextFusionRuntime(
        ContextFusionSettings(tmp_path / "snapshots", timeout),
        Events(),
        conversations or Conversations(),
        Missions(),
        perception or Perception(),
        Multimodal(),
        Status(),
        memory,
    )


def stable(result) -> dict:
    payload = asdict(result)
    payload.pop("trace_id")
    payload.pop("generated_at")
    interaction = payload["snapshot"]["interaction_context"]
    for key in ("context_id", "created_at", "updated_at"):
        interaction.pop(key)
    payload["consistency"]["metadata"].pop("context_id")
    return payload


def test_all_sources_preserve_order_provenance_sensitivity_and_confidence(tmp_path: Path) -> None:
    result = make_runtime(tmp_path, perception=Perception(True), memory=Memory()).build_context(
        conversation_id="c1",
        session_id="s1",
        incoming_message="current input",
        permission_context=PermissionContext(actor_id="owner"),
        persist_snapshot=False,
    )
    assert [item.id for item in result.items] == [
        "incoming_message:current",
        "conversation_summary:c1",
        "conversation_message:m1",
        "memory:mem-1",
        "perception:obs-1",
    ]
    signal = result.snapshot.signal_group.speech_signals[0]
    assert signal.provenance == [{"provider": "mock"}]
    assert signal.sensitivity == "sensitive"
    assert signal.confidence == 0.8


def test_optional_memory_absent_and_empty_perception_are_nonfatal(tmp_path: Path) -> None:
    result = make_runtime(tmp_path).build_context(conversation_id="c1", persist_snapshot=False)
    assert [item.id for item in result.items] == [
        "conversation_summary:c1",
        "conversation_message:m1",
    ]
    assert result.consistency.missing_sources == ["signals"]


@pytest.mark.parametrize("missing_index", range(5))
def test_each_required_source_absent_is_structured(
    tmp_path: Path, missing_index: int
) -> None:
    required = [Conversations(), Missions(), Perception(), Multimodal(), Status()]
    required[missing_index] = None
    with pytest.raises(ContextSourceUnavailable) as raised:
        ContextFusionRuntime(
            ContextFusionSettings(tmp_path), Events(), *required, None
        )
    assert raised.value.to_dict()["code"] == "context_source_unavailable"


def test_source_exception_preserves_existing_propagation(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, conversations=Conversations(failure=RuntimeError("failed")))
    with pytest.raises(RuntimeError, match="failed"):
        runtime.build_context(conversation_id="c1", persist_snapshot=False)


def test_source_timeout_does_not_block_indefinitely(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, conversations=Conversations(delay=0.2), timeout=0.01)
    started = time.perf_counter()
    with pytest.raises(TimeoutError, match="conversation"):
        runtime.build_context(conversation_id="c1", persist_snapshot=False)
    assert time.perf_counter() - started < 0.1


def test_small_budget_and_deduplication_match_baseline(tmp_path: Path) -> None:
    result = make_runtime(tmp_path, memory=Memory()).build_context(
        conversation_id="c1", session_id="s1", incoming_message="current input",
        permission_context=PermissionContext(actor_id="owner"),
        options={"budget": 8, "response_reserve": 1}, persist_snapshot=False,
    )
    assert [item.id for item in result.items] == [
        "incoming_message:current", "conversation_summary:c1"
    ]
    assert [item.id for item in result.omitted_items] == [
        "conversation_message:m1", "memory:mem-1"
    ]


def test_cross_source_deduplication_keeps_higher_priority_item(tmp_path: Path) -> None:
    result = make_runtime(tmp_path, memory=DuplicateMemory()).build_context(
        conversation_id="c1",
        permission_context=PermissionContext(actor_id="owner"),
        persist_snapshot=False,
    )
    assert "conversation_message:m1" in [item.id for item in result.items]
    assert "memory:mem-duplicate" not in [item.id for item in result.items]


def test_project_knowledge_context_uses_selected_evidence_budget(tmp_path: Path) -> None:
    memory = RecordingMemory()
    result = make_runtime(tmp_path, memory=memory).build_context(
        conversation_id="c1",
        incoming_message="/project alpha",
        permission_context=PermissionContext(actor_id="owner"),
        options={
            "include_project_knowledge": True,
            "retrieval_query": "alpha",
            "retrieval_intent": {
                "allowed": True,
                "project_id": "project-a",
            },
        },
        persist_snapshot=False,
    )

    assert memory.calls == [
        (
            "alpha",
            ["system", "user", "agent", "conversation", "session", "task", "mission", "knowledge"],
            5,
            {"tags": ["project_knowledge", "project:project-a"]},
        )
    ]
    knowledge_items = [item for item in result.items if item.source_type == "memory" and item.scope == "knowledge"]
    assert len(knowledge_items) == 5
    assert all(item.metadata["trusted_instruction"] is False for item in knowledge_items)


def test_invalid_port_result_is_rejected(tmp_path: Path) -> None:
    conversations = Conversations()
    conversations.read = lambda _conversation_id: {"invalid": True}  # type: ignore[method-assign]
    runtime = make_runtime(tmp_path, conversations=conversations)
    with pytest.raises(AttributeError):
        runtime.build_context(conversation_id="c1", persist_snapshot=False)


def test_correlation_id_crosses_timeout_boundary(tmp_path: Path) -> None:
    conversations = Conversations()
    runtime = make_runtime(tmp_path, conversations=conversations)
    with correlation_scope(new_correlation("test", correlation_id="corr-fixed")):
        runtime.build_context(conversation_id="c1", persist_snapshot=False)
    assert conversations.correlation_id == "corr-fixed"


def test_deterministic_result_shape_across_rebuilds(tmp_path: Path) -> None:
    first = stable(make_runtime(tmp_path).build_context(conversation_id="c1", persist_snapshot=False))
    second = stable(make_runtime(tmp_path).build_context(conversation_id="c1", persist_snapshot=False))
    assert first == second
