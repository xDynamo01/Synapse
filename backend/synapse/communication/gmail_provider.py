from __future__ import annotations

from synapse.communication.models import DraftMessage, EmailMessage
from synapse.core.exceptions import ToolExecutionError


class GmailCommunicationProvider:
    name = "gmail"

    def list_messages(self) -> list[EmailMessage]:
        raise ToolExecutionError("Gmail provider is prepared but not configured yet.")

    def read_message(self, message_id: str) -> EmailMessage:
        raise ToolExecutionError("Gmail provider is prepared but not configured yet.")

    def create_draft(
        self,
        subject: str,
        recipients: list[str],
        body: str,
        created_by_agent: str,
    ) -> DraftMessage:
        raise ToolExecutionError("Gmail provider is prepared but not configured yet.")

    def list_drafts(self) -> list[DraftMessage]:
        raise ToolExecutionError("Gmail provider is prepared but not configured yet.")

    def health_check(self) -> dict[str, object]:
        return {"provider": self.name, "status": "unconfigured"}
