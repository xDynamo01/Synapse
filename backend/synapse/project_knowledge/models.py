from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

PROJECT_KNOWLEDGE_SCHEMA_VERSION = 1
PARSER_VERSION = "text-parser-v1"
CHUNKER_VERSION = "fixed-window-v1"
INDEXER_VERSION = "deterministic-lexical-v1"
RANKER_VERSION = "deterministic-ranking-v1"
EMBEDDING_MODEL_ID = "synapse-local-canonical-embedding"
EMBEDDING_MODEL_VERSION = "v1"
EMBEDDING_DIMENSION = 32
SEMANTIC_INDEX_VERSION = "deterministic-semantic-index-v1"


class IngestionStatus(str, Enum):
    QUEUED = "queued"
    READING = "reading"
    CHUNKING = "chunking"
    INDEXING = "indexing"
    READY = "ready"
    FAILED = "failed"
    STALE = "stale"
    REMOVED = "removed"


class EmbeddingCapabilityStatus(str, Enum):
    AVAILABLE = "available"
    LOADING = "loading"
    READY = "ready"
    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"


@dataclass(frozen=True)
class ProjectDocument:
    document_id: str
    project_id: str
    workspace_id: str
    display_name: str
    created_at: str
    current_version_id: str | None = None
    status: IngestionStatus = IngestionStatus.QUEUED


@dataclass(frozen=True)
class ProjectDocumentVersion:
    version_id: str
    document_id: str
    project_id: str
    workspace_id: str
    attachment_id: str
    conversation_id: str | None
    session_id: str | None
    source_checksum: str
    parser_version: str
    chunker_version: str
    indexer_version: str
    status: IngestionStatus
    queued_at: str
    started_at: str | None = None
    completed_at: str | None = None
    chunk_count: int = 0
    failure_code: str | None = None
    failure_message: str | None = None
    superseded_by: str | None = None


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    version_id: str
    project_id: str
    attachment_id: str
    sequence: int
    start_offset: int
    end_offset: int
    content: str
    source_checksum: str


@dataclass(frozen=True)
class IndexEntry:
    entry_id: str
    chunk_id: str
    document_id: str
    version_id: str
    project_id: str
    indexer_version: str
    embedding_ref: str
    terms: tuple[str, ...]
    status: IngestionStatus


@dataclass(frozen=True)
class RetrievalRankingConfig:
    max_chunks: int = 5
    max_characters: int = 12_000
    max_chunks_per_document: int = 2
    min_lexical_score: float = 0.15
    include_neighbors: bool = True
    semantic_enabled: bool = False
    min_semantic_score: float = 0.20


@dataclass(frozen=True)
class IndexedCandidate:
    chunk_id: str
    document_id: str
    version_id: str
    project_id: str
    attachment_id: str
    sequence: int
    start_offset: int
    end_offset: int
    content: str
    source_checksum: str
    matched_terms: tuple[str, ...]
    lexical_score: float
    semantic_score: float | None
    lexical_rank: int | None
    semantic_rank: int | None
    freshness_score: float
    locality_score: float
    duplicate_key: str


@dataclass(frozen=True)
class EmbeddingCapability:
    status: EmbeddingCapabilityStatus
    provider_id: str
    model_id: str
    model_version: str
    dimension: int
    semantic_index_version: str
    normalization_version: str = "v1"
    learned_semantic: bool = False
    configured: bool = False
    loaded: bool = False
    device: str = "cpu"
    reason: str | None = None


@dataclass(frozen=True)
class RetrievedEvidence:
    evidence_id: str
    chunk_id: str
    document_id: str
    version_id: str
    project_id: str
    content: str
    relevance_score: float
    relevance_facts: dict[str, Any]
    provenance: dict[str, Any]
    trusted_instruction: bool = False


@dataclass(frozen=True)
class IngestionRecord:
    document: ProjectDocument
    version: ProjectDocumentVersion
    chunks: tuple[DocumentChunk, ...] = ()
    index_entries: tuple[IndexEntry, ...] = ()
    facts: dict[str, Any] = field(default_factory=dict)
