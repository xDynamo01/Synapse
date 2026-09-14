from __future__ import annotations

from dataclasses import asdict
from enum import Enum
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from synapse.api.common import api_error, runtime_from

router = APIRouter(prefix="/project-knowledge", tags=["project-knowledge"])


class ProjectKnowledgeListQuery(BaseModel):
    workspace_id: str = "default"
    project_id: str


class ProjectKnowledgeMutationPayload(BaseModel):
    workspace_id: str = "default"


@router.get("/documents")
def list_project_knowledge_documents(
    project_id: str,
    request: Request,
    workspace_id: str = "default",
) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        documents = runtime.project_knowledge.list_documents(project_id)
        records = []
        for document in documents:
            try:
                record = runtime.project_knowledge.status(document.document_id)
                records.append(
                    {
                        "document": jsonable(asdict(record.document)),
                        "version": jsonable(asdict(record.version)),
                        "facts": record.facts,
                    }
                )
            except Exception as exc:  # Keep list available even if one record is corrupt.
                records.append(
                    {
                        "document": jsonable(asdict(document)),
                        "version": None,
                        "facts": {
                            "document_indexed": False,
                            "chunk_count": 0,
                            "safe_failure": True,
                            "failure_code": "document_status_unavailable",
                            "failure_message": str(exc),
                        },
                    }
                )
        canonical = runtime.project_knowledge.embedding_capability()
        learned = runtime.project_knowledge.learned_embedding_capability()
        return {
            "schema": "project-knowledge-documents-v1",
            "workspace_id": workspace_id,
            "project_id": project_id,
            "documents": records,
            "capabilities": {
                "lexical": {"available": True, "status": "available"},
                "canonical": jsonable(asdict(canonical)),
                "learned_semantic": jsonable(asdict(learned)),
                "hybrid": {
                    "available": canonical.status.value in {"available", "ready"}
                    or learned.status.value in {"available", "ready"},
                    "fallback_available": True,
                },
            },
            "retrieval_policy": {
                "explicit_retrieval_required": True,
                "listing_queries_knowledge": False,
                "listing_generates_query_embedding": False,
            },
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.get("/documents/{document_id}")
def get_project_knowledge_document_status(
    document_id: str,
    request: Request,
    workspace_id: str = "default",
) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        record = runtime.project_knowledge.status(document_id)
        return {
            "schema": "project-knowledge-document-status-v1",
            "workspace_id": workspace_id,
            "document": jsonable(asdict(record.document)),
            "version": jsonable(asdict(record.version)),
            "facts": record.facts,
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/documents/{document_id}/remove")
def remove_project_knowledge_document(
    document_id: str,
    payload: ProjectKnowledgeMutationPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        document = runtime.project_knowledge.remove_document(document_id)
        return {
            "schema": "project-knowledge-document-remove-result-v1",
            "workspace_id": payload.workspace_id,
            "document": jsonable(asdict(document)),
        }
    except Exception as exc:
        raise api_error(exc) from exc


@router.post("/documents/{document_id}/reindex")
def reindex_project_knowledge_document(
    document_id: str,
    payload: ProjectKnowledgeMutationPayload,
    request: Request,
) -> dict[str, Any]:
    try:
        runtime = runtime_from(request)
        version = runtime.project_knowledge.reindex_document(document_id)
        return {
            "schema": "project-knowledge-document-reindex-result-v1",
            "workspace_id": payload.workspace_id,
            "version": jsonable(asdict(version)),
        }
    except Exception as exc:
        raise api_error(exc) from exc


def jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [jsonable(item) for item in value]
    return value
