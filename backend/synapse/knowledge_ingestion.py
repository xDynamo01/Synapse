from __future__ import annotations

from threading import Thread

from synapse.conversations.models import ConversationAttachment
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext
from synapse.memory.store import MemoryStore
from synapse.project_knowledge.runtime import ProjectKnowledgeRuntime


def schedule_attachment_knowledge_ingestion(
    *,
    data_dir: DataDir,
    events: EventBus,
    memory: MemoryStore | None,
    context: PermissionContext,
    attachment: ConversationAttachment,
    workspace_id: str,
    project_id: str | None,
    session_id: str | None,
) -> str:
    runtime = ProjectKnowledgeRuntime(data_dir, events, memory)
    status = runtime.schedule_attachment_ingestion(
        context,
        attachment,
        workspace_id=workspace_id,
        project_id=project_id,
        session_id=session_id,
    )
    if status != "scheduled" or project_id is None:
        return status

    worker_context = context

    def ingest() -> None:
        try:
            runtime.ingest_attachment(
                worker_context,
                attachment,
                workspace_id=workspace_id,
                project_id=project_id,
                session_id=session_id,
            )
        except Exception as exc:
            events.emit(
                "project_knowledge.ingestion_failed",
                "project_knowledge",
                {
                    "attachment_id": attachment.attachment_id,
                    "conversation_id": attachment.conversation_id,
                    "project_id": project_id,
                    "error_type": type(exc).__name__,
                },
            )

    Thread(
        target=ingest,
        name=f"synapse-project-knowledge-ingest-{attachment.attachment_id}",
        daemon=True,
    ).start()
    return "scheduled"
