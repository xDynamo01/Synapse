from __future__ import annotations

from dataclasses import asdict
from typing import Any

from synapse.communication.models import (
    EMAIL_CATEGORIES,
    CommunicationBriefing,
    DraftMessage,
    EmailMessage,
)
from synapse.communication.provider import CommunicationProvider
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.lifecycle.runtime import LifecycleRuntime
from synapse.observability.correlation import current_correlation
from synapse.presence.runtime import PresenceRuntime


class CommunicationRuntime:
    def __init__(
        self,
        providers: dict[str, CommunicationProvider],
        event_bus: EventBus,
        presence: PresenceRuntime,
        lifecycle: LifecycleRuntime,
        default_provider: str = "mock",
    ):
        self.providers = providers
        self.event_bus = event_bus
        self.presence = presence
        self.lifecycle = lifecycle
        self.default_provider = default_provider

    def list_messages(self, provider: str | None = None) -> list[EmailMessage]:
        return self._provider(provider).list_messages()

    def read_message(self, message_id: str, provider: str | None = None) -> EmailMessage:
        message = self._provider(provider).read_message(message_id)
        self.event_bus.emit("communication.message_read", "communication", asdict(message))
        return message

    def summarize_message(self, message_id: str, provider: str | None = None) -> dict[str, Any]:
        message = self.read_message(message_id, provider)
        summary = self._summary_for(message)
        payload = {"message_id": message.id, "summary": summary, "provider": message.provider}
        self.event_bus.emit("communication.summary_generated", "communication", payload)
        return payload

    def classify_message(self, message_id: str, provider: str | None = None) -> dict[str, Any]:
        message = self.read_message(message_id, provider)
        category = self._classify(message)
        payload = {
            "message_id": message.id,
            "provider": message.provider,
            "category": category,
        }
        self.event_bus.emit("communication.message_classified", "communication", payload)
        return payload

    def create_draft(
        self,
        subject: str,
        recipients: list[str],
        body: str,
        created_by_agent: str = "hermes",
        provider: str | None = None,
    ) -> DraftMessage:
        if not recipients:
            raise ValidationError("create_draft requires recipients")
        draft = self._provider(provider).create_draft(
            subject=subject,
            recipients=recipients,
            body=body,
            created_by_agent=created_by_agent,
        )
        self.event_bus.emit("communication.draft_created", created_by_agent, asdict(draft))
        return draft

    def list_drafts(self, provider: str | None = None) -> list[DraftMessage]:
        return self._provider(provider).list_drafts()

    def daily_summary(self, provider: str | None = None) -> dict[str, Any]:
        messages = self.list_messages(provider)
        categories = {category: 0 for category in sorted(EMAIL_CATEGORIES)}
        for message in messages:
            categories[self._classify(message)] += 1
        payload = {
            "provider": provider or self.default_provider,
            "total_messages": len(messages),
            "categories": categories,
            "summary": self._format_summary(len(messages), categories),
        }
        self.event_bus.emit("communication.summary_generated", "communication", payload)
        return payload

    def generate_briefing(
        self,
        agent_id: str = "hermes",
        provider: str | None = None,
    ) -> CommunicationBriefing:
        provider_id = provider or self.default_provider
        self.lifecycle.wake(agent_id, "Checking Email")
        self.presence.set_state(agent_id, "working", "Checking Email", {"actor_id": agent_id})
        try:
            messages = self.list_messages(provider_id)
            categories = {category: 0 for category in sorted(EMAIL_CATEGORIES)}
            important: list[str] = []
            low_priority: list[str] = []
            for message in messages:
                category = self._classify(message)
                categories[category] += 1
                self.event_bus.emit(
                    "communication.message_classified",
                    agent_id,
                    {
                        "message_id": message.id,
                        "provider": message.provider,
                        "category": category,
                    },
                )
                if category in {"recruitment", "project", "personal"}:
                    important.append(f"{message.sender}: {message.subject}")
                else:
                    low_priority.append(message.subject)
            correlation = current_correlation()
            briefing = CommunicationBriefing(
                provider=provider_id,
                agent_id=agent_id,
                total_messages=len(messages),
                categories=categories,
                important=important,
                low_priority=low_priority,
                summary=(
                    f"Hermes analyzed {len(messages)} emails. "
                    f"Important: {len(important)}. Low priority: {len(low_priority)}."
                ),
                correlation_id=correlation.correlation_id if correlation else None,
            )
            self.event_bus.emit("communication.briefing_generated", agent_id, asdict(briefing))
            return briefing
        except Exception as exc:
            self.lifecycle.error(agent_id, str(exc) or type(exc).__name__)
            raise
        finally:
            if self.lifecycle.get(agent_id).state != "error":
                self.lifecycle.sleep(agent_id)
                self.presence.set_state(agent_id, "idle", "Email check completed", {"actor_id": agent_id})

    def _provider(self, provider: str | None = None) -> CommunicationProvider:
        provider_id = provider or self.default_provider
        item = self.providers.get(provider_id)
        if not item:
            raise ValidationError(f"Communication provider not found: {provider_id}")
        return item

    @staticmethod
    def _summary_for(message: EmailMessage) -> str:
        sentence = message.body.strip().split(".")[0].strip()
        return sentence or message.subject

    @staticmethod
    def _classify(message: EmailMessage) -> str:
        text = " ".join([message.subject, message.sender, message.body, *message.labels]).lower()
        if any(token in text for token in ["recruit", "application", "opportunity", "interview"]):
            return "recruitment"
        if any(token in text for token in ["project", "milestone", "client", "rws"]):
            return "project"
        if any(token in text for token in ["newsletter", "weekly", "digest"]):
            return "newsletter"
        if any(token in text for token in ["security", "notification", "no-reply", "system"]):
            return "system"
        if any(token in text for token in ["family", "personal", "friend"]):
            return "personal"
        return "unknown"

    @staticmethod
    def _format_summary(total: int, categories: dict[str, int]) -> str:
        lines = [f"{total} emails found"]
        for category in ["recruitment", "project", "personal", "newsletter", "system", "unknown"]:
            lines.append(f"{categories.get(category, 0)} {category}")
        return "\n".join(lines)
