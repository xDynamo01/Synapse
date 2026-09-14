from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from acceptance.agent_kinds_support import runtime_at
from synapse.api.routes import router


def client_for(runtime) -> TestClient:
    app = FastAPI()
    app.state.runtime = runtime
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_project_knowledge_document_status_remove_and_reindex_api(tmp_path: Path) -> None:
    runtime = runtime_at(tmp_path / "data", clean=True)
    client = client_for(runtime)
    content = b"fencing rollback project knowledge"
    conversation = runtime.conversations.create_conversation(
        runtime.context(),
        participants=["local_chat"],
        metadata={"workspace_id": "default", "project_id": "project-a"},
    )
    attachment = runtime.conversations.stage_and_register_attachment(
        runtime.context(),
        conversation.conversation_id,
        filename="briefing.txt",
        mime_type="text/plain",
        content=content,
        owner_id=runtime.context().actor_id,
    )
    record = runtime.project_knowledge.ingest_attachment(
        runtime.context(),
        attachment,
        workspace_id="default",
        project_id="project-a",
        session_id=None,
    )

    listed = client.get("/api/project-knowledge/documents", params={"project_id": "project-a"})
    status = client.get(f"/api/project-knowledge/documents/{record.document.document_id}")
    reindexed = client.post(
        f"/api/project-knowledge/documents/{record.document.document_id}/reindex",
        json={"workspace_id": "default"},
    )
    removed = client.post(
        f"/api/project-knowledge/documents/{record.document.document_id}/remove",
        json={"workspace_id": "default"},
    )

    assert listed.status_code == 200, listed.text
    listed_payload = listed.json()
    assert listed_payload["documents"][0]["document"]["document_id"] == record.document.document_id
    assert listed_payload["documents"][0]["version"]["status"] == "ready"
    assert listed_payload["documents"][0]["facts"]["document_indexed"] is True
    assert listed_payload["capabilities"]["lexical"]["available"] is True
    assert listed_payload["capabilities"]["learned_semantic"]["status"] in {
        "unconfigured",
        "available",
        "loading",
        "ready",
        "unavailable",
        "incompatible",
        "failed",
    }
    assert listed_payload["retrieval_policy"] == {
        "explicit_retrieval_required": True,
        "listing_queries_knowledge": False,
        "listing_generates_query_embedding": False,
    }
    assert status.status_code == 200, status.text
    assert status.json()["facts"]["document_indexed"] is True
    assert reindexed.status_code == 200, reindexed.text
    assert reindexed.json()["version"]["status"] == "ready"
    assert removed.status_code == 200, removed.text
    assert removed.json()["document"]["status"] == "removed"
