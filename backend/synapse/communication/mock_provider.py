from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime

from synapse.communication.models import DraftMessage, EmailMessage
from synapse.core.data_dir import DataDir
from synapse.core.exceptions import NotFound
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.observability.correlation import current_correlation


class MockCommunicationProvider:
    name = "mock"

    def __init__(self, data_dir: DataDir):
        self.data_dir = data_dir

    def list_messages(self) -> list[EmailMessage]:
        return self._seed_messages()

    def read_message(self, message_id: str) -> EmailMessage:
        for message in self.list_messages():
            if message.id == message_id:
                return message
        raise NotFound(f"Email message not found: {message_id}")

    def create_draft(
        self,
        subject: str,
        recipients: list[str],
        body: str,
        created_by_agent: str,
    ) -> DraftMessage:
        correlation = current_correlation()
        draft = DraftMessage(
            provider=self.name,
            subject=subject,
            recipients=recipients,
            body=body,
            created_by_agent=created_by_agent,
            correlation_id=correlation.correlation_id if correlation else None,
        )
        dump_structured_file(self._draft_path(draft.id), asdict(draft))
        return draft

    def list_drafts(self) -> list[DraftMessage]:
        drafts_dir = self.data_dir.resolve(f"communication/{self.name}/drafts")
        return [
            self._read_draft(path)
            for path in sorted(drafts_dir.glob("*.yaml"))
        ]

    def health_check(self) -> dict[str, object]:
        return {"provider": self.name, "status": "ok", "offline": True}

    def _draft_path(self, draft_id: str):
        return self.data_dir.resolve(f"communication/{self.name}/drafts/{draft_id}.yaml")

    @staticmethod
    def _read_draft(path) -> DraftMessage:
        raw = load_structured_file(path)
        raw.setdefault("correlation_id", None)
        return DraftMessage(**raw)

    def _seed_messages(self) -> list[EmailMessage]:
        now = datetime.now(UTC).isoformat()
        return [
            EmailMessage(
                id="mock-amazon-recruitment",
                provider=self.name,
                thread_id="thread-amazon",
                subject="Amazon application update",
                sender="recruiting@amazon.example",
                recipients=["arthur@example.local"],
                received_at=now,
                body=(
                    "Thank you for applying. Your application moved to the next review stage. "
                    "Please confirm availability for an interview."
                ),
                labels=["inbox", "recruitment"],
                metadata={"priority": "important"},
            ),
            EmailMessage(
                id="mock-rws-project",
                provider=self.name,
                thread_id="thread-rws",
                subject="RWS project status update",
                sender="pm@rws.example",
                recipients=["arthur@example.local"],
                received_at=now,
                body="The localization project schedule changed. Please review the updated milestones.",
                labels=["inbox", "project"],
                metadata={"priority": "important"},
            ),
            EmailMessage(
                id="mock-flyrank-recruitment",
                provider=self.name,
                thread_id="thread-flyrank",
                subject="FlyRank new opportunity",
                sender="talent@flyrank.example",
                recipients=["arthur@example.local"],
                received_at=now,
                body="A new remote AI operations role matches your profile. Reply if interested.",
                labels=["inbox", "recruitment"],
                metadata={"priority": "important"},
            ),
            EmailMessage(
                id="mock-newsletter",
                provider=self.name,
                subject="Weekly AI newsletter",
                sender="newsletter@example",
                recipients=["arthur@example.local"],
                received_at=now,
                body="This week in AI: model releases, agent frameworks, and tooling notes.",
                labels=["newsletter"],
                metadata={"priority": "low"},
            ),
            EmailMessage(
                id="mock-system",
                provider=self.name,
                subject="Security notification",
                sender="no-reply@system.example",
                recipients=["arthur@example.local"],
                received_at=now,
                body="A new sign-in was detected on your account.",
                labels=["system"],
                metadata={"priority": "low"},
            ),
        ]
