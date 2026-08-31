from __future__ import annotations

from contextvars import copy_context
from dataclasses import asdict
from queue import Queue
from threading import Thread
from typing import Any, Callable, TypeVar

from synapse.context_fusion.contracts import (
    ContextFusionSettings,
    ConversationContextReader,
    MemoryContextReader,
    MissionContextReader,
    MultimodalContextReader,
    PerceptionContextReader,
    PerceptionSignalRead,
    RuntimeStatusContextReader,
)
from synapse.context_fusion.errors import ContextBudgetExceeded, ContextSourceUnavailable
from synapse.context_fusion.models import (
    ContextConsistency,
    ContextFusionResult,
    ContextItem,
    ContextSignalGroup,
    ContextSnapshot,
    InteractionContext,
)
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext
from synapse.core.serialization import dump_structured_file

T = TypeVar("T")


class ContextFusionRuntime:
    def __init__(
        self,
        settings: ContextFusionSettings,
        events: EventBus,
        conversations: ConversationContextReader,
        missions: MissionContextReader,
        perception: PerceptionContextReader,
        multimodal: MultimodalContextReader,
        runtime_status: RuntimeStatusContextReader,
        memory: MemoryContextReader | None = None,
    ) -> None:
        required = {
            "conversations": conversations,
            "missions": missions,
            "perception": perception,
            "multimodal": multimodal,
            "runtime_status": runtime_status,
        }
        missing = [name for name, source in required.items() if source is None]
        if missing:
            raise ContextSourceUnavailable(
                f"Required Context Fusion source unavailable: {', '.join(missing)}"
            )
        self.settings = settings
        self.events = events
        self.conversations = conversations
        self.missions = missions
        self.perception = perception
        self.multimodal = multimodal
        self.runtime_status = runtime_status
        self.memory = memory

    def _read(self, source: str, operation: Callable[[], T]) -> T:
        result: Queue[tuple[bool, object]] = Queue(maxsize=1)
        context = copy_context()

        def invoke() -> None:
            try:
                result.put((True, context.run(operation)))
            except BaseException as exc:
                result.put((False, exc))

        thread = Thread(target=invoke, name=f"context-fusion-{source}", daemon=True)
        thread.start()
        thread.join(self.settings.source_timeout_seconds)
        if thread.is_alive():
            raise TimeoutError(f"Context Fusion source timed out: {source}")
        succeeded, value = result.get_nowait()
        if succeeded:
            return value  # type: ignore[return-value]
        raise value  # type: ignore[misc]

    def build_context(
        self,
        conversation_id: str | None = None,
        multimodal_session_id: str | None = None,
        mission_id: str | None = None,
        agent_id: str | None = None,
        incoming_message: str | None = None,
        session_id: str | None = None,
        files: list[dict[str, Any]] | None = None,
        perception: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        permission_context: PermissionContext | None = None,
        persist_snapshot: bool = True,
    ) -> ContextFusionResult:
        options = options or {}
        self.events.emit(
            "context_fusion.started",
            "context_fusion",
            {
                "conversation_id": conversation_id,
                "multimodal_session_id": multimodal_session_id,
                "mission_id": mission_id,
            },
        )
        self.events.emit(
            "context_build_started",
            "context_fusion",
            {
                "conversation_id": conversation_id,
                "agent_id": agent_id,
                "mission_id": mission_id,
                "session_id": session_id,
            },
        )
        participants = self._participants(conversation_id, multimodal_session_id, mission_id)
        interaction = InteractionContext(
            conversation_id=conversation_id,
            multimodal_session_id=multimodal_session_id,
            mission_id=mission_id,
            participants=participants,
        )
        conversation_payload = (
            self._read(
                "conversation",
                lambda: self.conversations.read(conversation_id),
            )
            if conversation_id
            else None
        )
        latest_summary = (
            conversation_payload.summary
            if conversation_payload is not None
            else self._conversation_summary(conversation_id)
        )
        latest_messages = (
            conversation_payload.messages
            if conversation_payload is not None
            else self._latest_messages(conversation_id)
        )
        signal_group = self._signal_group(conversation_id, multimodal_session_id)
        speech_features = self._speech_features(signal_group)
        mission_summary = self._mission_summary(mission_id)
        delegation_summary = self._delegation_summary(mission_id)
        snapshot = ContextSnapshot(
            interaction_context=interaction,
            latest_conversation_summary=latest_summary,
            latest_messages=latest_messages,
            signal_group=signal_group,
            speech_features=speech_features,
            mission_summary=mission_summary,
            delegation_summary=delegation_summary,
            health_summary=(
                self._read("health", self.runtime_status.health_summary)
                if options.get("include_runtime_health")
                else None
            ),
            readiness_summary=(
                self._read("readiness", self.runtime_status.readiness_summary)
                if options.get("include_runtime_health")
                else None
            ),
            metadata={"source": "context_fusion"},
        )
        consistency = self.validate_context(snapshot)
        perception_items = (
            perception
            if perception is not None
            else self._observation_context(
                conversation_id=conversation_id,
                session_id=session_id,
                multimodal_session_id=multimodal_session_id,
            )
        )
        items = self._context_items(
            snapshot,
            agent_id=agent_id,
            incoming_message=incoming_message,
            session_id=session_id,
            files=files or [],
            perception=perception_items,
            permission_context=permission_context,
        )
        budget = int(options.get("budget", 4096))
        response_reserve = int(options.get("response_reserve", min(1024, budget // 4)))
        try:
            selected, omitted = self._apply_budget(items, max(1, budget - response_reserve))
        except Exception as exc:
            self.events.emit(
                "context_build_failed",
                "context_fusion",
                {"error_type": type(exc).__name__, "conversation_id": conversation_id},
            )
            raise
        rendered = "\n\n".join(
            f"[{item.source_type}:{item.source_id}]\n{item.content}" for item in selected
        )
        result = ContextFusionResult(
            snapshot=snapshot,
            consistency=consistency,
            items=selected,
            rendered_context=rendered,
            total_estimated_tokens=sum(item.estimated_tokens for item in selected),
            budget=budget,
            omitted_items=omitted,
            warnings=[
                *consistency.warnings,
                *(["context budget omitted optional sources"] if omitted else []),
            ],
        )
        for item in selected:
            self.events.emit(
                "context_source_added",
                "context_fusion",
                {"source_type": item.source_type, "source_id": item.source_id, "scope": item.scope},
            )
        for item in omitted:
            self.events.emit(
                "context_source_omitted",
                "context_fusion",
                {"source_type": item.source_type, "source_id": item.source_id, "reason": "budget"},
            )
        if persist_snapshot:
            self._write_snapshot(result)
        self.events.emit("context_fusion.completed", "context_fusion", self._result_payload(result))
        self.events.emit(
            "context_build_completed",
            "context_fusion",
            {
                "trace_id": result.trace_id,
                "item_count": len(result.items),
                "omitted_count": len(result.omitted_items),
                "estimated_tokens": result.total_estimated_tokens,
            },
        )
        return result

    def _context_items(
        self,
        snapshot: ContextSnapshot,
        *,
        agent_id: str | None,
        incoming_message: str | None,
        session_id: str | None,
        files: list[dict[str, Any]],
        perception: list[dict[str, Any]],
        permission_context: PermissionContext | None,
    ) -> list[ContextItem]:
        items: list[ContextItem] = []

        def add(
            source_type: str,
            source_id: str,
            scope: str,
            content: str,
            priority: int,
            *,
            mandatory: bool = False,
            confidence: float | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> None:
            normalized = content.strip()
            if not normalized:
                return
            items.append(
                ContextItem(
                    id=f"{source_type}:{source_id}",
                    source_type=source_type,
                    source_id=source_id,
                    scope=scope,
                    content=normalized,
                    priority=priority,
                    estimated_tokens=max(1, (len(normalized) + 3) // 4),
                    confidence=confidence,
                    mandatory=mandatory,
                    metadata=metadata or {},
                    information_owner=str((metadata or {}).get("information_owner", "user-owned")),
                    classification=str((metadata or {}).get("classification", "internal")),
                    categories=tuple((metadata or {}).get("categories", ())),
                    training_use_policy=str(
                        (metadata or {}).get("training_use_policy", "prohibited")
                    ),
                )
            )

        if incoming_message:
            add("incoming_message", "current", "session", incoming_message, 300, mandatory=True)
        summary = snapshot.latest_conversation_summary or {}
        if summary.get("summary"):
            add(
                "conversation_summary",
                str(summary.get("conversation_id", "summary")),
                "conversation",
                str(summary["summary"]),
                180,
            )
        for message in snapshot.latest_messages:
            body = message.get("payload", {}).get("body", "")
            add(
                "conversation_message",
                str(message.get("message_id", "message")),
                "conversation",
                str(body),
                170,
                metadata={"role": message.get("role")},
            )
        if snapshot.mission_summary:
            add(
                "mission",
                str(snapshot.interaction_context.mission_id),
                "mission",
                str(snapshot.mission_summary),
                200,
            )
        for signal in perception:
            confidence = signal.get("confidence")
            if confidence is not None and float(confidence) < 0.5:
                continue
            add(
                "perception",
                str(signal.get("id", "signal")),
                "session",
                str(signal.get("content", signal)),
                120,
                confidence=confidence,
            )
        for file in files:
            add(
                "file",
                str(file.get("id", file.get("storage_ref", "file"))),
                "session",
                str(file.get("content", file.get("storage_ref", ""))),
                100,
                metadata={"checksum": file.get("checksum")},
            )
        if self.memory and permission_context:
            memory_reader = self.memory
            scopes = [
                "system",
                "user",
                "knowledge",
                "agent",
                "conversation",
                "session",
                "task",
                "mission",
            ]
            owner_ids = [
                value
                for value in [
                    permission_context.actor_id,
                    agent_id,
                    snapshot.interaction_context.conversation_id,
                    session_id,
                    snapshot.interaction_context.mission_id,
                ]
                if value
            ]
            memories = self._read(
                "memory",
                lambda: memory_reader.retrieve(permission_context, scopes, owner_ids, 30),
            )
            for memory_item in memories:
                add(
                    "memory",
                    memory_item.id,
                    memory_item.scope,
                    memory_item.content,
                    150 + memory_item.importance,
                    confidence=memory_item.confidence,
                    metadata={
                        "revision": memory_item.revision,
                        "source": memory_item.source,
                    },
                )
        deduplicated: dict[str, ContextItem] = {}
        for item in sorted(items, key=lambda value: (-value.priority, value.id)):
            key = " ".join(item.content.casefold().split())
            existing = deduplicated.get(key)
            if existing and existing.source_id != item.source_id:
                self.events.emit(
                    "context_source_omitted",
                    "context_fusion",
                    {
                        "source_id": item.source_id,
                        "reason": "duplicate",
                        "kept_source_id": existing.source_id,
                    },
                )
                continue
            deduplicated[key] = item
        return sorted(deduplicated.values(), key=lambda value: (-value.priority, value.id))

    @staticmethod
    def _apply_budget(
        items: list[ContextItem], budget: int
    ) -> tuple[list[ContextItem], list[ContextItem]]:
        mandatory = [item for item in items if item.mandatory]
        if sum(item.estimated_tokens for item in mandatory) > budget:
            raise ContextBudgetExceeded("mandatory context exceeds budget")
        selected, omitted, used = [], [], 0
        for item in items:
            if used + item.estimated_tokens <= budget:
                selected.append(item)
                used += item.estimated_tokens
            else:
                omitted.append(item)
        return selected, omitted

    def build_conversation_context(self, conversation_id: str) -> ContextFusionResult:
        return self.build_context(conversation_id=conversation_id)

    def build_mission_context(self, mission_id: str) -> ContextFusionResult:
        mission = self._read("mission", lambda: self.missions.get_mission(mission_id))
        return self.build_context(
            conversation_id=mission.conversation_id,
            mission_id=mission_id,
        )

    def build_multimodal_context(self, session_id: str) -> ContextFusionResult:
        return self.build_context(multimodal_session_id=session_id)

    def validate_context(self, snapshot: ContextSnapshot) -> ContextConsistency:
        missing: list[str] = []
        warnings: list[str] = []
        context = snapshot.interaction_context
        if context.conversation_id and not self._exists(
            lambda: self._read(
                "conversation",
                lambda: self.conversations.participants(context.conversation_id or ""),
            )
        ):
            missing.append("conversation")
            warnings.append(f"Conversation not found: {context.conversation_id}")
        if context.mission_id and not self._exists(
            lambda: self._read(
                "mission", lambda: self.missions.get_mission(context.mission_id or "")
            )
        ):
            missing.append("mission")
            warnings.append(f"Mission not found: {context.mission_id}")
        if context.multimodal_session_id and not self._exists(
            lambda: self._read(
                "multimodal",
                lambda: self.multimodal.participants(context.multimodal_session_id or ""),
            )
        ):
            missing.append("multimodal_session")
            warnings.append(f"Multimodal session not found: {context.multimodal_session_id}")
        if not context.participants:
            missing.append("participants")
            warnings.append("No participants were found for the context.")
        if self._signal_count(snapshot.signal_group) == 0:
            missing.append("signals")
            warnings.append("No perception signals were found for the context.")
        consistency = ContextConsistency(
            complete=not missing,
            missing_sources=missing,
            warnings=warnings,
            metadata={"context_id": context.context_id},
        )
        self.events.emit(
            "context_fusion.validation_completed", "context_fusion", asdict(consistency)
        )
        return consistency

    def summarize_context(self, result: ContextFusionResult) -> dict[str, Any]:
        snapshot = result.snapshot
        group = snapshot.signal_group
        return {
            "context_id": snapshot.interaction_context.context_id,
            "participants": len(snapshot.interaction_context.participants),
            "messages": len(snapshot.latest_messages),
            "signals": self._signal_count(group),
            "complete": result.consistency.complete,
            "warnings": list(result.consistency.warnings),
        }

    def _participants(
        self,
        conversation_id: str | None,
        multimodal_session_id: str | None,
        mission_id: str | None,
    ) -> list[str]:
        participants: set[str] = set()
        if conversation_id:
            try:
                conversation_participants = self._read(
                    "conversation", lambda: self.conversations.participants(conversation_id)
                )
                participants.update(conversation_participants)
            except NotFound:
                pass
        if multimodal_session_id:
            try:
                participants.update(
                    self._read(
                        "multimodal",
                        lambda: self.multimodal.participants(multimodal_session_id),
                    )
                )
            except NotFound:
                pass
        if mission_id:
            try:
                mission = self._read("mission", lambda: self.missions.get_mission(mission_id))
                if mission.owner_agent_id:
                    participants.add(mission.owner_agent_id)
                task_ids = self._read("mission", lambda: self.missions.list_task_ids(mission_id))
                for task_id in task_ids:
                    try:
                        task = self._read("mission", lambda: self.missions.get_task(task_id))
                        participants.add(task.requester_agent_id)
                        participants.add(task.assignee_agent_id)
                    except NotFound:
                        continue
            except NotFound:
                pass
        return sorted(participants)

    def _conversation_summary(self, conversation_id: str | None) -> dict[str, Any] | None:
        if not conversation_id:
            return None
        try:
            return self._read(
                "conversation", lambda: self.conversations.read(conversation_id)
            ).summary
        except NotFound:
            return None

    def _latest_messages(
        self, conversation_id: str | None, limit: int = 10
    ) -> list[dict[str, Any]]:
        if not conversation_id:
            return []
        try:
            return self._read(
                "conversation", lambda: self.conversations.read(conversation_id)
            ).messages[-limit:]
        except NotFound:
            return []

    def _signal_group(
        self,
        conversation_id: str | None,
        multimodal_session_id: str | None,
    ) -> ContextSignalGroup:
        all_signals = self._read("perception", self.perception.list_signals)
        signals = [
            signal
            for signal in all_signals
            if self._signal_matches(signal, conversation_id, multimodal_session_id)
        ]
        if not conversation_id and not multimodal_session_id:
            signals = []
        return ContextSignalGroup(
            speech_signals=[signal for signal in signals if signal.signal_type == "speech"],
            voice_signals=[signal for signal in signals if signal.signal_type == "voice"],
            face_signals=[signal for signal in signals if signal.signal_type == "face"],
            body_signals=[signal for signal in signals if signal.signal_type == "body"],
            system_signals=[signal for signal in signals if signal.signal_type == "system"],
            metadata={"total_signals": len(signals)},
        )

    def _signal_matches(
        self,
        signal: PerceptionSignalRead,
        conversation_id: str | None,
        multimodal_session_id: str | None,
    ) -> bool:
        if multimodal_session_id and signal.multimodal_session_id == multimodal_session_id:
            return True
        if conversation_id and signal.conversation_id == conversation_id:
            return True
        return False

    def _observation_context(
        self,
        *,
        conversation_id: str | None,
        session_id: str | None,
        multimodal_session_id: str | None,
    ) -> list[dict[str, Any]]:
        if not any((conversation_id, session_id, multimodal_session_id)):
            return []
        observations = self._read(
            "perception",
            lambda: self.perception.list_observations(
                conversation_id=conversation_id,
                session_id=session_id,
            ),
        )
        if multimodal_session_id:
            signal_ids = {
                signal.id
                for signal in self._read("perception", self.perception.list_signals)
                if signal.multimodal_session_id == multimodal_session_id
            }
            observations = [
                item for item in observations if signal_ids.intersection(item.signal_ids)
            ]
        return [
            {
                "id": item.id,
                "content": item.content,
                "type": item.type,
                "confidence": item.confidence,
                "relevance": item.relevance,
                "provenance": item.provenance,
                "sensitivity": item.sensitivity,
                "valid_until": item.valid_until,
                "warnings": item.warnings,
            }
            for item in observations
        ]

    def _mission_summary(self, mission_id: str | None) -> dict[str, Any] | None:
        if not mission_id:
            return None
        try:
            mission = self._read("mission", lambda: self.missions.get_mission(mission_id))
            summary = self._read("mission", lambda: self.missions.summarize(mission_id))
            return {
                "mission": mission.payload,
                "summary": summary.summary,
                "context_summary": summary.context_summary,
            }
        except NotFound:
            return None

    def _delegation_summary(self, mission_id: str | None) -> dict[str, Any] | None:
        if not mission_id:
            return None
        try:
            task_ids = self._read("mission", lambda: self.missions.list_task_ids(mission_id))
        except NotFound:
            return None
        tasks = []
        for task_id in task_ids:
            try:
                tasks.append(self._read("mission", lambda: self.missions.get_task(task_id)))
            except NotFound:
                continue
        by_status: dict[str, int] = {}
        for task in tasks:
            by_status[task.status] = by_status.get(task.status, 0) + 1
        return {
            "total_tasks": len(tasks),
            "by_status": by_status,
            "tasks": [task.payload for task in tasks],
        }

    @staticmethod
    def _signal_count(group: ContextSignalGroup) -> int:
        return (
            len(group.speech_signals)
            + len(group.voice_signals)
            + len(group.face_signals)
            + len(group.body_signals)
            + len(group.system_signals)
        )

    @staticmethod
    def _speech_features(group: ContextSignalGroup) -> list[dict[str, Any]]:
        features: list[dict[str, Any]] = []
        for signal in group.speech_signals:
            payload = signal.payload if isinstance(signal.payload, dict) else {}
            raw_features = payload.get("speech_features")
            if isinstance(raw_features, dict):
                features.append(raw_features)
                continue
            metadata_features = signal.metadata.get("speech_features")
            if isinstance(metadata_features, dict):
                features.append(metadata_features)
        return features

    @staticmethod
    def _exists(loader) -> bool:
        try:
            loader()
            return True
        except NotFound:
            return False

    def _write_snapshot(self, result: ContextFusionResult) -> None:
        context_id = result.snapshot.interaction_context.context_id
        dump_structured_file(
            self.settings.snapshot_root / f"{context_id}.yaml",
            self._result_payload(result),
        )

    @staticmethod
    def _result_payload(result: ContextFusionResult) -> dict[str, Any]:
        return asdict(result)
