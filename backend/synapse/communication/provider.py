from __future__ import annotations

from typing import Protocol

from synapse.communication.models import DraftMessage, EmailMessage


class CommunicationProvider(Protocol):
    name: str

    def list_messages(self) -> list[EmailMessage]:
        ...

    def read_message(self, message_id: str) -> EmailMessage:
        ...

    def create_draft(
        self,
        subject: str,
        recipients: list[str],
        body: str,
        created_by_agent: str,
    ) -> DraftMessage:
        ...

    def list_drafts(self) -> list[DraftMessage]:
        ...

    def health_check(self) -> dict[str, object]:
        ...
