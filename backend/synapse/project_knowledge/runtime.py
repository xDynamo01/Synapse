from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from threading import Thread
from typing import Iterator

from synapse.conversations.models import ConversationAttachment
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext
from synapse.memory.store import MemoryStore
from synapse.project_knowledge.embedding_providers import (
    EmbeddingProvider,
    UnconfiguredLearnedEmbeddingProvider,
    canonical_embedding_capability,
)
from synapse.project_knowledge.models import (
    CHUNKER_VERSION,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_VERSION,
    INDEXER_VERSION,
    PARSER_VERSION,
    PROJECT_KNOWLEDGE_SCHEMA_VERSION,
    RANKER_VERSION,
    SEMANTIC_INDEX_VERSION,
    DocumentChunk,
    EmbeddingCapability,
    EmbeddingCapabilityStatus,
    IndexedCandidate,
    IndexEntry,
    IngestionRecord,
    IngestionStatus,
    ProjectDocument,
    ProjectDocumentVersion,
    RetrievalRankingConfig,
    RetrievedEvidence,
)

TEXT_ATTACHMENT_MIME_TYPES = {
    "application/json",
    "text/csv",
    "text/markdown",
    "text/plain",
}
MAX_DOCUMENT_CHARS = 120_000
CHUNK_CHARS = 3_200
CHUNK_OVERLAP = 240


class ProjectKnowledgeRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        memory: MemoryStore | None = None,
        semantic_enabled: bool = False,
        semantic_capability_status: EmbeddingCapabilityStatus = EmbeddingCapabilityStatus.AVAILABLE,
        learned_embedding_provider: EmbeddingProvider | None = None,
        learned_semantic_threshold: float = 0.82,
        canonical_semantic_threshold: float = 0.55,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.memory = memory
        self.semantic_enabled = semantic_enabled
        self.semantic_capability_status = semantic_capability_status
        self.learned_embedding_provider = learned_embedding_provider or UnconfiguredLearnedEmbeddingProvider()
        self.learned_semantic_threshold = learned_semantic_threshold
        self.canonical_semantic_threshold = canonical_semantic_threshold
        self.db_path = data_dir.resolve("project_knowledge/project_knowledge.sqlite3")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def schedule_attachment_ingestion(
        self,
        context: PermissionContext,
        attachment: ConversationAttachment,
        *,
        workspace_id: str,
        project_id: str | None,
        session_id: str | None,
    ) -> str:
        if attachment.mime_type not in TEXT_ATTACHMENT_MIME_TYPES:
            return "unsupported_attachment_type"
        if not project_id:
            return "missing_project_scope"
        self._create_or_get_queued_version(
            attachment,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
        )
        self.events.emit(
            "project_knowledge.ingestion_scheduled",
            "project_knowledge",
            {
                "attachment_id": attachment.attachment_id,
                "conversation_id": attachment.conversation_id,
                "project_id": project_id,
            },
        )
        return "scheduled"

    def schedule_attachment_ingestion_async(
        self,
        context: PermissionContext,
        attachment: ConversationAttachment,
        *,
        workspace_id: str,
        project_id: str | None,
        session_id: str | None,
    ) -> str:
        status = self.schedule_attachment_ingestion(
            context,
            attachment,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
        )
        if status != "scheduled" or project_id is None:
            return status

        def ingest() -> None:
            try:
                self.ingest_attachment(
                    context,
                    attachment,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    session_id=session_id,
                )
            except Exception as exc:
                self.events.emit(
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

    def ingest_attachment(
        self,
        context: PermissionContext,
        attachment: ConversationAttachment,
        *,
        workspace_id: str,
        project_id: str,
        session_id: str | None,
    ) -> IngestionRecord:
        document, version = self._create_or_get_queued_version(
            attachment,
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
        )
        if version.status is IngestionStatus.READY:
            return self._record(document.document_id, version.version_id)
        try:
            self._set_version_status(version.version_id, IngestionStatus.READING)
            content = self._read_attachment_text(attachment)
            self._set_version_status(version.version_id, IngestionStatus.CHUNKING)
            chunks = self._chunk(content[:MAX_DOCUMENT_CHARS], document, version)
            self._set_version_status(version.version_id, IngestionStatus.INDEXING)
            entries = self._index(chunks, version)
            self._replace_chunks_and_index(version.version_id, chunks, entries)
            semantic_entries = self._semantic_index(chunks, capability=self.embedding_capability())
            semantic_entries.extend(
                self._semantic_index(
                    chunks,
                    capability=self.learned_embedding_capability(),
                    provider=self.learned_embedding_provider,
                )
            )
            self._replace_semantic_index(version.version_id, semantic_entries)
            self._mark_previous_versions_stale(document.document_id, version.version_id)
            completed = _now()
            with self._connect() as db:
                db.execute(
                    """
                    UPDATE project_document_versions
                    SET status=?, completed_at=?, chunk_count=?
                    WHERE version_id=?
                    """,
                    (IngestionStatus.READY.value, completed, len(chunks), version.version_id),
                )
                db.execute(
                    """
                    UPDATE project_documents
                    SET current_version_id=?, status=?
                    WHERE document_id=?
                    """,
                    (version.version_id, IngestionStatus.READY.value, document.document_id),
                )
            self._mirror_ready_chunks_to_memory(
                chunks,
                attachment,
                workspace_id,
                session_id,
                context,
            )
            self.events.emit(
                "project_knowledge.ingestion_ready",
                "project_knowledge",
                {
                    "document_id": document.document_id,
                    "version_id": version.version_id,
                    "project_id": project_id,
                    "chunk_count": len(chunks),
                },
            )
            return self._record(document.document_id, version.version_id)
        except Exception as exc:
            self._fail_version(version.version_id, type(exc).__name__, str(exc))
            raise

    def retrieve(
        self,
        context: PermissionContext,
        *,
        query: str,
        project_id: str,
        limit: int = 5,
        max_characters: int = 12_000,
        max_chunks_per_document: int = 2,
        include_neighbors: bool = True,
        semantic_enabled: bool | None = None,
        retrieval_mode: str = "hybrid",
    ) -> list[RetrievedEvidence]:
        del context
        use_semantic = self.semantic_enabled if semantic_enabled is None else semantic_enabled
        mode = _requested_retrieval_mode(retrieval_mode)
        capability = (
            self.embedding_capability()
            if use_semantic and mode in {"canonical", "semantic", "hybrid"}
            else self._semantic_unavailable("disabled")
        )
        learned_capability = (
            self.learned_embedding_capability()
            if use_semantic and mode in {"learned", "hybrid"}
            else self._learned_unavailable("disabled")
        )
        config = RetrievalRankingConfig(
            max_chunks=limit,
            max_characters=max_characters,
            max_chunks_per_document=max_chunks_per_document,
            include_neighbors=include_neighbors,
            semantic_enabled=_capability_ready(capability.status),
        )
        lexical_candidates = (
            self._generate_candidates(query=query, project_id=project_id)
            if mode in {"lexical", "hybrid"}
            else []
        )
        canonical_candidates = (
            self._generate_semantic_candidates(
                query=query,
                project_id=project_id,
                capability=capability,
                threshold=self.canonical_semantic_threshold,
            )
            if _capability_ready(capability.status)
            and (
                mode in {"canonical", "semantic"}
                or (
                    mode == "hybrid"
                    and not _capability_ready(learned_capability.status)
                )
            )
            else []
        )
        semantic_candidates = (
            self._generate_learned_semantic_candidates(
                query=query,
                project_id=project_id,
                capability=learned_capability,
            )
            if _capability_ready(learned_capability.status)
            and mode in {"learned", "hybrid"}
            else []
        )
        candidates = (
            self._fuse_candidates(lexical_candidates, [*semantic_candidates, *canonical_candidates])
            if mode == "hybrid"
            else [*lexical_candidates, *canonical_candidates, *semantic_candidates]
        )
        ranked = self._rank_candidates(candidates, config)
        selected = self._select_evidence(ranked, query=query, config=config)
        if config.include_neighbors:
            selected = self._include_chunk_neighborhood(selected, query=query, config=config)
        for evidence in selected:
            evidence.relevance_facts["semantic_capability_status"] = capability.status.value
            evidence.relevance_facts["semantic_fallback_reason"] = capability.reason
            evidence.relevance_facts["learned_semantic_capability_status"] = learned_capability.status.value
            evidence.relevance_facts["learned_semantic_fallback_reason"] = learned_capability.reason
            evidence.relevance_facts["learned_semantic_provider_id"] = learned_capability.provider_id
            evidence.relevance_facts["learned_semantic_model_id"] = learned_capability.model_id
            evidence.relevance_facts["learned_semantic_model_version"] = (
                learned_capability.model_version
            )
            evidence.relevance_facts["learned_semantic_configured"] = learned_capability.configured
            evidence.relevance_facts["learned_semantic_loaded"] = learned_capability.loaded
            evidence.relevance_facts["learned_semantic_device"] = learned_capability.device
            evidence.relevance_facts["retrieval_mode"] = _retrieval_mode(
                evidence.relevance_facts.get("lexical_rank"),
                evidence.relevance_facts.get("semantic_rank"),
            )
            evidence.relevance_facts["requested_retrieval_mode"] = mode
            evidence.relevance_facts["candidate_counts"] = {
                "lexical": len(lexical_candidates),
                "canonical": len(canonical_candidates),
                "learned_semantic": len(semantic_candidates),
                "hybrid": len(candidates) if mode == "hybrid" else 0,
                "selected": len(selected),
            }
        return selected

    def embedding_capability(self) -> EmbeddingCapability:
        if not self.semantic_enabled:
            return self._semantic_unavailable("disabled")
        return canonical_embedding_capability(self.semantic_capability_status)

    def learned_embedding_capability(self) -> EmbeddingCapability:
        if not self.semantic_enabled:
            return self._learned_unavailable("disabled")
        return self.learned_embedding_provider.capability()

    @staticmethod
    def _semantic_unavailable(reason: str) -> EmbeddingCapability:
        return EmbeddingCapability(
            status=EmbeddingCapabilityStatus.UNAVAILABLE,
            provider_id="synapse_canonical_similarity",
            model_id=EMBEDDING_MODEL_ID,
            model_version=EMBEDDING_MODEL_VERSION,
            dimension=EMBEDDING_DIMENSION,
            semantic_index_version=SEMANTIC_INDEX_VERSION,
            reason=reason,
        )

    @staticmethod
    def _learned_unavailable(reason: str) -> EmbeddingCapability:
        return EmbeddingCapability(
            status=EmbeddingCapabilityStatus.UNAVAILABLE,
            provider_id="synapse_learned_local",
            model_id="unconfigured",
            model_version="unconfigured",
            dimension=0,
            semantic_index_version=SEMANTIC_INDEX_VERSION,
            normalization_version="learned-normalized-v1",
            learned_semantic=True,
            configured=False,
            loaded=False,
            device="cpu",
            reason=reason,
        )

    def _generate_candidates(self, *, query: str, project_id: str) -> list[IndexedCandidate]:
        terms = _terms(query)
        if not terms:
            raise ValidationError("empty_retrieval_query")
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.chunk_id, c.document_id, c.version_id, c.project_id, c.attachment_id,
                       c.sequence, c.start_offset, c.end_offset, c.content, c.source_checksum,
                       e.terms
                FROM document_chunks c
                JOIN index_entries e ON e.chunk_id = c.chunk_id
                JOIN project_document_versions v ON v.version_id = c.version_id
                JOIN project_documents d ON d.document_id = c.document_id
                WHERE c.project_id=?
                  AND v.status=?
                  AND d.status=?
                  AND e.status=?
                  AND d.current_version_id = v.version_id
                """,
                (
                    project_id,
                    IngestionStatus.READY.value,
                    IngestionStatus.READY.value,
                    IngestionStatus.READY.value,
                ),
            ).fetchall()
        candidates: list[IndexedCandidate] = []
        for rank, row in enumerate(rows, start=1):
            row_terms = set(json.loads(str(row["terms"])))
            hits = tuple(sorted(terms & row_terms))
            if not hits:
                continue
            lexical_score = len(hits) / max(len(terms), 1)
            sequence = int(row["sequence"])
            candidates.append(
                IndexedCandidate(
                    chunk_id=str(row["chunk_id"]),
                    document_id=str(row["document_id"]),
                    version_id=str(row["version_id"]),
                    project_id=str(row["project_id"]),
                    attachment_id=str(row["attachment_id"]),
                    sequence=sequence,
                    start_offset=int(row["start_offset"]),
                    end_offset=int(row["end_offset"]),
                    content=str(row["content"]),
                    source_checksum=str(row["source_checksum"]),
                    matched_terms=hits,
                    lexical_score=lexical_score,
                    semantic_score=None,
                    lexical_rank=rank,
                    semantic_rank=None,
                    freshness_score=1.0,
                    locality_score=1.0 / (1 + sequence),
                    duplicate_key=_duplicate_key(str(row["content"])),
                )
            )
        return candidates

    def _generate_semantic_candidates(
        self,
        *,
        query: str,
        project_id: str,
        capability: EmbeddingCapability,
        threshold: float,
    ) -> list[IndexedCandidate]:
        query_vector = self._embedding_for_text(
            query,
            capability=capability,
            provider=self.learned_embedding_provider if capability.learned_semantic else None,
            kind="query",
        )
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT c.chunk_id, c.document_id, c.version_id, c.project_id, c.attachment_id,
                       c.sequence, c.start_offset, c.end_offset, c.content, c.source_checksum,
                       s.vector_json
                FROM semantic_index_entries s
                JOIN document_chunks c ON c.chunk_id = s.chunk_id
                JOIN project_document_versions v ON v.version_id = c.version_id
                JOIN project_documents d ON d.document_id = c.document_id
                WHERE c.project_id=?
                  AND v.status=?
                  AND d.status=?
                  AND s.status=?
                  AND d.current_version_id = v.version_id
                  AND s.embedding_model_id=?
                  AND s.embedding_model_version=?
                  AND s.embedding_dimension=?
                  AND s.semantic_index_version=?
                """,
                (
                    project_id,
                    IngestionStatus.READY.value,
                    IngestionStatus.READY.value,
                    IngestionStatus.READY.value,
                    capability.model_id,
                    capability.model_version,
                    capability.dimension,
                    capability.semantic_index_version,
                ),
            ).fetchall()
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            score = _cosine(query_vector, tuple(json.loads(str(row["vector_json"]))))
            if score >= threshold:
                scored.append((score, row))
        candidates: list[IndexedCandidate] = []
        for rank, (score, row) in enumerate(
            sorted(
                scored,
                key=lambda item: (
                    -item[0],
                    str(item[1]["document_id"]),
                    str(item[1]["version_id"]),
                    int(item[1]["sequence"]),
                    str(item[1]["chunk_id"]),
                ),
            ),
            start=1,
        ):
            candidates.append(
                IndexedCandidate(
                    chunk_id=str(row["chunk_id"]),
                    document_id=str(row["document_id"]),
                    version_id=str(row["version_id"]),
                    project_id=str(row["project_id"]),
                    attachment_id=str(row["attachment_id"]),
                    sequence=int(row["sequence"]),
                    start_offset=int(row["start_offset"]),
                    end_offset=int(row["end_offset"]),
                    content=str(row["content"]),
                    source_checksum=str(row["source_checksum"]),
                    matched_terms=(),
                    lexical_score=0.0,
                    semantic_score=score,
                    lexical_rank=None,
                    semantic_rank=rank,
                    freshness_score=1.0,
                    locality_score=1.0 / (1 + int(row["sequence"])),
                    duplicate_key=_duplicate_key(str(row["content"])),
                )
            )
        return candidates

    def _generate_learned_semantic_candidates(
        self,
        *,
        query: str,
        project_id: str,
        capability: EmbeddingCapability,
    ) -> list[IndexedCandidate]:
        return self._generate_semantic_candidates(
            query=query,
            project_id=project_id,
            capability=capability,
            threshold=self.learned_semantic_threshold,
        )

    @staticmethod
    def _fuse_candidates(
        lexical_candidates: list[IndexedCandidate],
        semantic_candidates: list[IndexedCandidate],
    ) -> list[IndexedCandidate]:
        by_chunk: dict[str, IndexedCandidate] = {}
        for candidate in lexical_candidates:
            by_chunk[candidate.chunk_id] = candidate
        for candidate in semantic_candidates:
            existing = by_chunk.get(candidate.chunk_id)
            if existing is None:
                by_chunk[candidate.chunk_id] = candidate
                continue
            by_chunk[candidate.chunk_id] = IndexedCandidate(
                chunk_id=existing.chunk_id,
                document_id=existing.document_id,
                version_id=existing.version_id,
                project_id=existing.project_id,
                attachment_id=existing.attachment_id,
                sequence=existing.sequence,
                start_offset=existing.start_offset,
                end_offset=existing.end_offset,
                content=existing.content,
                source_checksum=existing.source_checksum,
                matched_terms=existing.matched_terms,
                lexical_score=existing.lexical_score,
                semantic_score=candidate.semantic_score,
                lexical_rank=existing.lexical_rank,
                semantic_rank=candidate.semantic_rank,
                freshness_score=existing.freshness_score,
                locality_score=existing.locality_score,
                duplicate_key=existing.duplicate_key,
            )
        return list(by_chunk.values())

    def _rank_candidates(
        self,
        candidates: list[IndexedCandidate],
        config: RetrievalRankingConfig,
    ) -> list[tuple[float, IndexedCandidate, dict[str, object]]]:
        duplicate_counts: dict[str, int] = {}
        duplicate_sources: dict[str, list[dict[str, object]]] = {}
        for candidate in candidates:
            duplicate_counts[candidate.duplicate_key] = duplicate_counts.get(candidate.duplicate_key, 0) + 1
            duplicate_sources.setdefault(candidate.duplicate_key, []).append(
                {
                    "document_id": candidate.document_id,
                    "version_id": candidate.version_id,
                    "chunk_id": candidate.chunk_id,
                    "attachment_id": candidate.attachment_id,
                    "source_checksum": candidate.source_checksum,
                    "sequence": candidate.sequence,
                }
            )

        ranked: list[tuple[float, IndexedCandidate, dict[str, object]]] = []
        for candidate in candidates:
            semantic_score = candidate.semantic_score
            if (
                candidate.lexical_score < config.min_lexical_score
                and (semantic_score is None or semantic_score < config.min_semantic_score)
            ):
                continue
            duplicate_penalty = 0.1 if duplicate_counts[candidate.duplicate_key] > 1 else 0.0
            diversity_contribution = 0.0
            lexical_rrf = _rrf(candidate.lexical_rank)
            semantic_rrf = _rrf(candidate.semantic_rank)
            fused_retrieval_score = (lexical_rrf * 0.45) + (semantic_rrf * 0.45)
            ranking_score = (
                fused_retrieval_score
                + candidate.freshness_score * 0.12
                + candidate.locality_score * 0.10
                + diversity_contribution
                - duplicate_penalty
            )
            ranked.append(
                (
                    ranking_score,
                    candidate,
                    {
                        "ranker_version": RANKER_VERSION,
                        "lexical_score": candidate.lexical_score,
                        "semantic_score": semantic_score,
                        "lexical_rank": candidate.lexical_rank,
                        "semantic_rank": candidate.semantic_rank,
                        "lexical_rrf": lexical_rrf,
                        "semantic_rrf": semantic_rrf,
                        "fusion_strategy": "reciprocal_rank_fusion",
                        "freshness_contribution": candidate.freshness_score * 0.12,
                        "locality_contribution": candidate.locality_score * 0.10,
                        "diversity_contribution": diversity_contribution,
                        "duplicate_penalty": duplicate_penalty,
                        "duplicate_count": duplicate_counts[candidate.duplicate_key],
                        "duplicate_sources": sorted(
                            duplicate_sources[candidate.duplicate_key],
                            key=lambda source: (
                                str(source["document_id"]),
                                str(source["version_id"]),
                                str(source["sequence"]),
                                str(source["chunk_id"]),
                            ),
                        ),
                        "retrieval_policy": "explicit_project_knowledge",
                        "final_ranking_score": ranking_score,
                    },
                )
            )
        return sorted(
            ranked,
            key=lambda item: (
                -item[0],
                item[1].document_id,
                item[1].version_id,
                item[1].sequence,
                item[1].chunk_id,
            ),
        )

    def _select_evidence(
        self,
        ranked: list[tuple[float, IndexedCandidate, dict[str, object]]],
        *,
        query: str,
        config: RetrievalRankingConfig,
    ) -> list[RetrievedEvidence]:
        selected: list[RetrievedEvidence] = []
        selected_duplicate_keys: set[str] = set()
        document_counts: dict[str, int] = {}
        used_characters = 0
        for ranking_score, candidate, facts in ranked:
            if len(selected) >= config.max_chunks:
                break
            if candidate.duplicate_key in selected_duplicate_keys:
                continue
            if document_counts.get(candidate.document_id, 0) >= config.max_chunks_per_document:
                continue
            if used_characters + len(candidate.content) > config.max_characters:
                continue
            selected.append(self._candidate_to_evidence(candidate, query, ranking_score, facts))
            selected_duplicate_keys.add(candidate.duplicate_key)
            document_counts[candidate.document_id] = document_counts.get(candidate.document_id, 0) + 1
            used_characters += len(candidate.content)
        return selected

    def _include_chunk_neighborhood(
        self,
        selected: list[RetrievedEvidence],
        *,
        query: str,
        config: RetrievalRankingConfig,
    ) -> list[RetrievedEvidence]:
        if len(selected) >= config.max_chunks:
            return selected
        used_ids = {item.chunk_id for item in selected}
        used_duplicates = {_duplicate_key(item.content) for item in selected}
        document_counts: dict[str, int] = {}
        used_characters = 0
        for item in selected:
            document_counts[item.document_id] = document_counts.get(item.document_id, 0) + 1
            used_characters += len(item.content)
        expanded = list(selected)
        for item in selected:
            lexical_score = float(item.relevance_facts.get("lexical_score", 0.0))
            if lexical_score < 0.66:
                continue
            sequence = int(item.provenance["sequence"])
            for neighbor_sequence in (sequence - 1, sequence + 1):
                if len(expanded) >= config.max_chunks:
                    return expanded
                if document_counts.get(item.document_id, 0) >= config.max_chunks_per_document:
                    continue
                neighbor = self._neighbor_candidate(
                    item.document_id,
                    item.version_id,
                    neighbor_sequence,
                )
                if neighbor is None or neighbor.chunk_id in used_ids:
                    continue
                duplicate_key = _duplicate_key(neighbor.content)
                if duplicate_key in used_duplicates:
                    continue
                if used_characters + len(neighbor.content) > config.max_characters:
                    continue
                facts = {
                    "ranker_version": RANKER_VERSION,
                    "lexical_score": 0.0,
                    "semantic_score": None,
                    "freshness_contribution": 0.0,
                    "locality_contribution": 0.0,
                    "diversity_contribution": 0.0,
                    "duplicate_penalty": 0.0,
                    "duplicate_count": 1,
                    "retrieval_policy": "explicit_project_knowledge",
                    "final_ranking_score": 0.0,
                    "retrieval_reason": "adjacent_context_for_selected_chunk",
                }
                evidence = self._candidate_to_evidence(neighbor, query, 0.0, facts)
                expanded.append(evidence)
                used_ids.add(neighbor.chunk_id)
                used_duplicates.add(duplicate_key)
                document_counts[item.document_id] = document_counts.get(item.document_id, 0) + 1
                used_characters += len(neighbor.content)
        return expanded

    def _neighbor_candidate(
        self,
        document_id: str,
        version_id: str,
        sequence: int,
    ) -> IndexedCandidate | None:
        if sequence < 0:
            return None
        with self._connect() as db:
            row = db.execute(
                """
                SELECT chunk_id, document_id, version_id, project_id, attachment_id, sequence,
                       start_offset, end_offset, content, source_checksum
                FROM document_chunks
                WHERE document_id=? AND version_id=? AND sequence=?
                """,
                (document_id, version_id, sequence),
            ).fetchone()
        if row is None:
            return None
        return IndexedCandidate(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            version_id=str(row["version_id"]),
            project_id=str(row["project_id"]),
            attachment_id=str(row["attachment_id"]),
            sequence=int(row["sequence"]),
            start_offset=int(row["start_offset"]),
            end_offset=int(row["end_offset"]),
            content=str(row["content"]),
            source_checksum=str(row["source_checksum"]),
            matched_terms=(),
            lexical_score=0.0,
            semantic_score=None,
            lexical_rank=None,
            semantic_rank=None,
            freshness_score=1.0,
            locality_score=0.0,
            duplicate_key=_duplicate_key(str(row["content"])),
        )

    @staticmethod
    def _candidate_to_evidence(
        candidate: IndexedCandidate,
        query: str,
        ranking_score: float,
        facts: dict[str, object],
    ) -> RetrievedEvidence:
        relevance_facts = {
            "matched_terms": list(candidate.matched_terms),
            "indexer_version": INDEXER_VERSION,
            "retrieval_reason": facts.get("retrieval_reason", "ranked_candidate_selected"),
            **facts,
        }
        return RetrievedEvidence(
            evidence_id=_stable_id("evidence", candidate.chunk_id, query),
            chunk_id=candidate.chunk_id,
            document_id=candidate.document_id,
            version_id=candidate.version_id,
            project_id=candidate.project_id,
            content=candidate.content,
            relevance_score=ranking_score,
            relevance_facts=relevance_facts,
            provenance={
                "attachment_id": candidate.attachment_id,
                "source_checksum": candidate.source_checksum,
                "sequence": candidate.sequence,
                "start_offset": candidate.start_offset,
                "end_offset": candidate.end_offset,
            },
            trusted_instruction=False,
        )

    def list_documents(self, project_id: str) -> list[ProjectDocument]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT * FROM project_documents WHERE project_id=? ORDER BY created_at DESC",
                (project_id,),
            ).fetchall()
        return [self._document_from_row(row) for row in rows]

    def remove_document(self, document_id: str) -> ProjectDocument:
        with self._connect() as db:
            db.execute(
                "UPDATE project_documents SET status=? WHERE document_id=?",
                (IngestionStatus.REMOVED.value, document_id),
            )
            db.execute(
                "UPDATE project_document_versions SET status=? WHERE document_id=? AND status != ?",
                (
                    IngestionStatus.REMOVED.value,
                    document_id,
                    IngestionStatus.FAILED.value,
                ),
            )
            db.execute(
                "UPDATE index_entries SET status=? WHERE document_id=?",
                (IngestionStatus.REMOVED.value, document_id),
            )
            db.execute(
                "UPDATE semantic_index_entries SET status=? WHERE document_id=?",
                (IngestionStatus.REMOVED.value, document_id),
            )
        return self.get_document(document_id)

    def reindex_document(self, document_id: str) -> ProjectDocumentVersion:
        current = self.get_current_version(document_id)
        new_version_id = _stable_id(
            "version",
            document_id,
            current.source_checksum,
            PARSER_VERSION,
            CHUNKER_VERSION,
            INDEXER_VERSION,
            _now(),
        )
        old_record = self._record(document_id, current.version_id)
        now = _now()
        chunks = tuple(
            DocumentChunk(
                chunk_id=_stable_id("chunk", new_version_id, str(chunk.sequence), chunk.content),
                document_id=chunk.document_id,
                version_id=new_version_id,
                project_id=chunk.project_id,
                attachment_id=chunk.attachment_id,
                sequence=chunk.sequence,
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
                content=chunk.content,
                source_checksum=chunk.source_checksum,
            )
            for chunk in old_record.chunks
        )
        new_version = ProjectDocumentVersion(
            version_id=new_version_id,
            document_id=current.document_id,
            project_id=current.project_id,
            workspace_id=current.workspace_id,
            attachment_id=current.attachment_id,
            conversation_id=current.conversation_id,
            session_id=current.session_id,
            source_checksum=current.source_checksum,
            parser_version=PARSER_VERSION,
            chunker_version=CHUNKER_VERSION,
            indexer_version=INDEXER_VERSION,
            status=IngestionStatus.READY,
            queued_at=now,
            started_at=now,
            completed_at=now,
            chunk_count=len(chunks),
        )
        entries = self._index(chunks, new_version)
        semantic_entries = self._semantic_index(chunks, capability=self.embedding_capability())
        semantic_entries.extend(
            self._semantic_index(
                chunks,
                capability=self.learned_embedding_capability(),
                provider=self.learned_embedding_provider,
            )
        )
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO project_document_versions (
                    version_id, document_id, project_id, workspace_id, attachment_id,
                    conversation_id, session_id, source_checksum, parser_version,
                    chunker_version, indexer_version, status, queued_at, started_at,
                    completed_at, chunk_count, failure_code, failure_message, superseded_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
                """,
                (
                    new_version_id,
                    current.document_id,
                    current.project_id,
                    current.workspace_id,
                    current.attachment_id,
                    current.conversation_id,
                    current.session_id,
                    current.source_checksum,
                    PARSER_VERSION,
                    CHUNKER_VERSION,
                    INDEXER_VERSION,
                    IngestionStatus.READY.value,
                    now,
                    now,
                    now,
                    len(chunks),
                ),
            )
        self._replace_chunks_and_index(new_version_id, chunks, entries)
        self._replace_semantic_index(new_version_id, semantic_entries)
        self._mark_previous_versions_stale(document_id, new_version_id)
        with self._connect() as db:
            db.execute(
                "UPDATE project_documents SET current_version_id=?, status=? WHERE document_id=?",
                (new_version_id, IngestionStatus.READY.value, document_id),
            )
        return self.get_version(new_version_id)

    def reconcile_semantic_index_versions(self) -> int:
        canonical = self.embedding_capability()
        learned = self.learned_embedding_capability()
        compatible = {
            (
                canonical.model_id,
                canonical.model_version,
                canonical.dimension,
                canonical.semantic_index_version,
            ),
            (
                learned.model_id,
                learned.model_version,
                learned.dimension,
                learned.semantic_index_version,
            ),
        }
        with self._connect() as db:
            rows = db.execute(
                """
                SELECT entry_id, embedding_model_id, embedding_model_version,
                       embedding_dimension, semantic_index_version
                FROM semantic_index_entries
                WHERE status=?
                """,
                (IngestionStatus.READY.value,),
            ).fetchall()
            stale_ids = [
                str(row["entry_id"])
                for row in rows
                if (
                    str(row["embedding_model_id"]),
                    str(row["embedding_model_version"]),
                    int(row["embedding_dimension"]),
                    str(row["semantic_index_version"]),
                )
                not in compatible
            ]
            if not stale_ids:
                return 0
            db.executemany(
                "UPDATE semantic_index_entries SET status=? WHERE entry_id=?",
                [(IngestionStatus.STALE.value, entry_id) for entry_id in stale_ids],
            )
        return len(stale_ids)

    def get_document(self, document_id: str) -> ProjectDocument:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM project_documents WHERE document_id=?", (document_id,)
            ).fetchone()
        if row is None:
            raise ValidationError("document_not_found")
        return self._document_from_row(row)

    def get_current_version(self, document_id: str) -> ProjectDocumentVersion:
        document = self.get_document(document_id)
        if not document.current_version_id:
            raise ValidationError("document_has_no_ready_version")
        return self.get_version(document.current_version_id)

    def get_version(self, version_id: str) -> ProjectDocumentVersion:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM project_document_versions WHERE version_id=?", (version_id,)
            ).fetchone()
        if row is None:
            raise ValidationError("version_not_found")
        return self._version_from_row(row)

    def status(self, document_id: str) -> IngestionRecord:
        document = self.get_document(document_id)
        version_id = document.current_version_id
        if version_id is None:
            with self._connect() as db:
                row = db.execute(
                    """
                    SELECT * FROM project_document_versions
                    WHERE document_id=?
                    ORDER BY queued_at DESC
                    LIMIT 1
                    """,
                    (document_id,),
                ).fetchone()
            if row is None:
                raise ValidationError("document_has_no_versions")
            version_id = str(row["version_id"])
        return self._record(document_id, version_id)

    def _create_or_get_queued_version(
        self,
        attachment: ConversationAttachment,
        *,
        workspace_id: str,
        project_id: str,
        session_id: str | None,
    ) -> tuple[ProjectDocument, ProjectDocumentVersion]:
        checksum = attachment.checksum
        document_id = _stable_id("document", project_id, attachment.filename)
        version_id = _stable_id(
            "version", document_id, checksum, PARSER_VERSION, CHUNKER_VERSION, INDEXER_VERSION
        )
        now = _now()
        with self._connect() as db:
            existing_version = db.execute(
                "SELECT * FROM project_document_versions WHERE version_id=?", (version_id,)
            ).fetchone()
            db.execute(
                """
                INSERT OR IGNORE INTO project_documents (
                    document_id, project_id, workspace_id, display_name,
                    created_at, current_version_id, status
                ) VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    document_id,
                    project_id,
                    workspace_id,
                    attachment.filename,
                    now,
                    IngestionStatus.QUEUED.value,
                ),
            )
            if existing_version is None:
                db.execute(
                    """
                    INSERT INTO project_document_versions (
                        version_id, document_id, project_id, workspace_id, attachment_id,
                        conversation_id, session_id, source_checksum, parser_version,
                        chunker_version, indexer_version, status, queued_at, started_at,
                        completed_at, chunk_count, failure_code, failure_message, superseded_by
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, NULL, NULL, NULL)
                    """,
                    (
                        version_id,
                        document_id,
                        project_id,
                        workspace_id,
                        attachment.attachment_id,
                        attachment.conversation_id,
                        session_id,
                        checksum,
                        PARSER_VERSION,
                        CHUNKER_VERSION,
                        INDEXER_VERSION,
                        IngestionStatus.QUEUED.value,
                        now,
                    ),
                )
        return self.get_document(document_id), self.get_version(version_id)

    def _record(self, document_id: str, version_id: str) -> IngestionRecord:
        document = self.get_document(document_id)
        version = self.get_version(version_id)
        with self._connect() as db:
            chunk_rows = db.execute(
                "SELECT * FROM document_chunks WHERE version_id=? ORDER BY sequence",
                (version_id,),
            ).fetchall()
            index_rows = db.execute(
                "SELECT * FROM index_entries WHERE version_id=? ORDER BY entry_id",
                (version_id,),
            ).fetchall()
            semantic_index_count = db.execute(
                "SELECT COUNT(*) FROM semantic_index_entries WHERE version_id=? AND status=?",
                (version_id, IngestionStatus.READY.value),
            ).fetchone()[0]
        chunks = tuple(self._chunk_from_row(row) for row in chunk_rows)
        entries = tuple(self._entry_from_row(row) for row in index_rows)
        capability = self.embedding_capability()
        learned_capability = self.learned_embedding_capability()
        return IngestionRecord(
            document=document,
            version=version,
            chunks=chunks,
            index_entries=entries,
            facts={
                "schema_version": PROJECT_KNOWLEDGE_SCHEMA_VERSION,
                "document_indexed": version.status is IngestionStatus.READY,
                "chunk_count": len(chunks),
                "index_entry_count": len(entries),
                "semantic_capability_status": capability.status.value,
                "semantic_fallback_reason": capability.reason,
                "semantic_index_entry_count": int(semantic_index_count),
                "semantic_index_version": SEMANTIC_INDEX_VERSION,
                "embedding_model_id": EMBEDDING_MODEL_ID,
                "embedding_model_version": EMBEDDING_MODEL_VERSION,
                "embedding_dimension": EMBEDDING_DIMENSION,
                "canonical_vector_similarity_is_learned": False,
                "learned_semantic_capability_status": learned_capability.status.value,
                "learned_semantic_fallback_reason": learned_capability.reason,
                "learned_semantic_provider_id": learned_capability.provider_id,
                "learned_semantic_model_id": learned_capability.model_id,
                "learned_semantic_model_version": learned_capability.model_version,
                "learned_semantic_dimension": learned_capability.dimension,
                "learned_semantic_configured": learned_capability.configured,
                "learned_semantic_loaded": learned_capability.loaded,
                "learned_semantic_device": learned_capability.device,
            },
        )

    def _read_attachment_text(self, attachment: ConversationAttachment) -> str:
        path = self.data_dir.resolve(attachment.storage_ref)
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()).strip()

    def _chunk(
        self,
        content: str,
        document: ProjectDocument,
        version: ProjectDocumentVersion,
    ) -> tuple[DocumentChunk, ...]:
        chunks: list[DocumentChunk] = []
        start = 0
        sequence = 0
        while start < len(content):
            end = min(start + CHUNK_CHARS, len(content))
            chunk = content[start:end].strip()
            if chunk:
                chunks.append(
                    DocumentChunk(
                        chunk_id=_stable_id("chunk", version.version_id, str(sequence), chunk),
                        document_id=document.document_id,
                        version_id=version.version_id,
                        project_id=document.project_id,
                        attachment_id=version.attachment_id,
                        sequence=sequence,
                        start_offset=start,
                        end_offset=end,
                        content=chunk,
                        source_checksum=version.source_checksum,
                    )
                )
                sequence += 1
            next_start = start + CHUNK_CHARS - CHUNK_OVERLAP
            if next_start <= start:
                break
            start = next_start
        return tuple(chunks)

    def _index(
        self, chunks: tuple[DocumentChunk, ...], version: ProjectDocumentVersion
    ) -> tuple[IndexEntry, ...]:
        entries = []
        for chunk in chunks:
            terms = tuple(sorted(_terms(chunk.content)))
            entries.append(
                IndexEntry(
                    entry_id=_stable_id("index", chunk.chunk_id, INDEXER_VERSION),
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    version_id=chunk.version_id,
                    project_id=chunk.project_id,
                    indexer_version=INDEXER_VERSION,
                    embedding_ref=f"lexical://{chunk.chunk_id}",
                    terms=terms,
                    status=IngestionStatus.READY,
                )
            )
        return tuple(entries)

    def _semantic_index(
        self,
        chunks: tuple[DocumentChunk, ...],
        *,
        capability: EmbeddingCapability,
        provider: EmbeddingProvider | None = None,
    ) -> list[dict[str, object]]:
        if not _capability_ready(capability.status):
            return []
        entries: list[dict[str, object]] = []
        for chunk in chunks:
            content_fingerprint = _content_fingerprint(chunk.content, capability=capability)
            vector = self._embedding_for_text(
                chunk.content,
                capability=capability,
                provider=provider,
                kind="passage",
            )
            entries.append(
                {
                    "entry_id": _stable_id(
                        "semantic",
                        chunk.chunk_id,
                        capability.provider_id,
                        capability.model_id,
                        capability.model_version,
                        str(capability.dimension),
                        capability.normalization_version,
                        capability.semantic_index_version,
                    ),
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "version_id": chunk.version_id,
                    "project_id": chunk.project_id,
                    "embedding_model_id": capability.model_id,
                    "embedding_model_version": capability.model_version,
                    "embedding_dimension": capability.dimension,
                    "semantic_index_version": capability.semantic_index_version,
                    "source_checksum": chunk.source_checksum,
                    "content_fingerprint": content_fingerprint,
                    "vector_json": json.dumps(vector),
                    "status": IngestionStatus.READY.value,
                }
            )
        return entries

    def _embedding_for_text(
        self,
        text: str,
        *,
        capability: EmbeddingCapability,
        provider: EmbeddingProvider | None = None,
        kind: str = "query",
    ) -> tuple[float, ...]:
        content_fingerprint = _content_fingerprint(text, capability=capability)
        with self._connect() as db:
            row = db.execute(
                """
                SELECT vector_json FROM semantic_embedding_cache
                WHERE content_fingerprint=?
                  AND embedding_model_id=?
                  AND embedding_model_version=?
                  AND embedding_dimension=?
                """,
                (
                    content_fingerprint,
                    capability.model_id,
                    capability.model_version,
                    capability.dimension,
                ),
            ).fetchone()
            if row is not None:
                return tuple(float(value) for value in json.loads(str(row["vector_json"])))
            vector = provider.embed(text, kind=kind) if provider is not None else _local_embedding(text)
            if len(vector) != capability.dimension:
                raise RuntimeError("embedding_dimension_mismatch")
            db.execute(
                """
                INSERT INTO semantic_embedding_cache (
                    content_fingerprint, embedding_model_id, embedding_model_version,
                    embedding_dimension, vector_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    content_fingerprint,
                    capability.model_id,
                    capability.model_version,
                    capability.dimension,
                    json.dumps(vector),
                    _now(),
                ),
            )
        return vector

    def _replace_chunks_and_index(
        self,
        version_id: str,
        chunks: tuple[DocumentChunk, ...],
        entries: tuple[IndexEntry, ...],
    ) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM document_chunks WHERE version_id=?", (version_id,))
            db.execute("DELETE FROM index_entries WHERE version_id=?", (version_id,))
            db.executemany(
                """
                INSERT INTO document_chunks (
                    chunk_id, document_id, version_id, project_id, attachment_id, sequence,
                    start_offset, end_offset, content, source_checksum
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        chunk.chunk_id,
                        chunk.document_id,
                        chunk.version_id,
                        chunk.project_id,
                        chunk.attachment_id,
                        chunk.sequence,
                        chunk.start_offset,
                        chunk.end_offset,
                        chunk.content,
                        chunk.source_checksum,
                    )
                    for chunk in chunks
                ],
            )
            db.executemany(
                """
                INSERT INTO index_entries (
                    entry_id, chunk_id, document_id, version_id, project_id,
                    indexer_version, embedding_ref, terms, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry.entry_id,
                        entry.chunk_id,
                        entry.document_id,
                        entry.version_id,
                        entry.project_id,
                        entry.indexer_version,
                        entry.embedding_ref,
                        json.dumps(entry.terms),
                        entry.status.value,
                    )
                    for entry in entries
                ],
            )

    def _replace_semantic_index(
        self,
        version_id: str,
        entries: list[dict[str, object]],
    ) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM semantic_index_entries WHERE version_id=?", (version_id,))
            db.executemany(
                """
                INSERT INTO semantic_index_entries (
                    entry_id, chunk_id, document_id, version_id, project_id,
                    embedding_model_id, embedding_model_version, embedding_dimension,
                    semantic_index_version, source_checksum, content_fingerprint,
                    vector_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        entry["entry_id"],
                        entry["chunk_id"],
                        entry["document_id"],
                        entry["version_id"],
                        entry["project_id"],
                        entry["embedding_model_id"],
                        entry["embedding_model_version"],
                        entry["embedding_dimension"],
                        entry["semantic_index_version"],
                        entry["source_checksum"],
                        entry["content_fingerprint"],
                        entry["vector_json"],
                        entry["status"],
                    )
                    for entry in entries
                ],
            )

    def _mark_previous_versions_stale(self, document_id: str, current_version_id: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE project_document_versions
                SET status=?, superseded_by=?
                WHERE document_id=? AND version_id != ? AND status=?
                """,
                (
                    IngestionStatus.STALE.value,
                    current_version_id,
                    document_id,
                    current_version_id,
                    IngestionStatus.READY.value,
                ),
            )
            db.execute(
                """
                UPDATE index_entries
                SET status=?
                WHERE document_id=? AND version_id != ?
                """,
                (IngestionStatus.STALE.value, document_id, current_version_id),
            )
            db.execute(
                """
                UPDATE semantic_index_entries
                SET status=?
                WHERE document_id=? AND version_id != ?
                """,
                (IngestionStatus.STALE.value, document_id, current_version_id),
            )

    def _mirror_ready_chunks_to_memory(
        self,
        chunks: tuple[DocumentChunk, ...],
        attachment: ConversationAttachment,
        workspace_id: str,
        session_id: str | None,
        context: PermissionContext,
    ) -> None:
        if self.memory is None:
            return
        for chunk in chunks:
            self.memory.create(
                context,
                scope="knowledge",
                owner_id=context.actor_id,
                source=f"project_document:{chunk.document_id}:{chunk.version_id}:{chunk.chunk_id}",
                content=chunk.content,
                content_type="text/plain",
                importance=60,
                tags=[
                    "rag",
                    "project_knowledge",
                    f"project:{chunk.project_id}",
                    f"document:{chunk.document_id}",
                    f"version:{chunk.version_id}",
                    f"chunk:{chunk.chunk_id}",
                ],
                metadata={
                    "document_id": chunk.document_id,
                    "version_id": chunk.version_id,
                    "chunk_id": chunk.chunk_id,
                    "attachment_id": attachment.attachment_id,
                    "conversation_id": attachment.conversation_id,
                    "session_id": session_id,
                    "workspace_id": workspace_id,
                    "project_id": chunk.project_id,
                    "source_checksum": chunk.source_checksum,
                    "chunk_sequence": chunk.sequence,
                    "start_offset": chunk.start_offset,
                    "end_offset": chunk.end_offset,
                    "rag_retrieval": False,
                    "trusted_instruction": False,
                },
            )

    def _set_version_status(self, version_id: str, status: IngestionStatus) -> None:
        started_at = _now() if status is IngestionStatus.READING else None
        with self._connect() as db:
            if started_at:
                db.execute(
                    "UPDATE project_document_versions SET status=?, started_at=? WHERE version_id=?",
                    (status.value, started_at, version_id),
                )
            else:
                db.execute(
                    "UPDATE project_document_versions SET status=? WHERE version_id=?",
                    (status.value, version_id),
                )

    def _fail_version(self, version_id: str, code: str, message: str) -> None:
        with self._connect() as db:
            db.execute(
                """
                UPDATE project_document_versions
                SET status=?, completed_at=?, failure_code=?, failure_message=?
                WHERE version_id=?
                """,
                (IngestionStatus.FAILED.value, _now(), code, message[:300], version_id),
            )

    def _ensure_schema(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_documents (
                    document_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    current_version_id TEXT,
                    status TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS project_document_versions (
                    version_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    workspace_id TEXT NOT NULL,
                    attachment_id TEXT NOT NULL,
                    conversation_id TEXT,
                    session_id TEXT,
                    source_checksum TEXT NOT NULL,
                    parser_version TEXT NOT NULL,
                    chunker_version TEXT NOT NULL,
                    indexer_version TEXT NOT NULL,
                    status TEXT NOT NULL,
                    queued_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    chunk_count INTEGER NOT NULL,
                    failure_code TEXT,
                    failure_message TEXT,
                    superseded_by TEXT
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    chunk_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    attachment_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    start_offset INTEGER NOT NULL,
                    end_offset INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    source_checksum TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS index_entries (
                    entry_id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    indexer_version TEXT NOT NULL,
                    embedding_ref TEXT NOT NULL,
                    terms TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_embedding_cache (
                    content_fingerprint TEXT NOT NULL,
                    embedding_model_id TEXT NOT NULL,
                    embedding_model_version TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    vector_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (
                        content_fingerprint,
                        embedding_model_id,
                        embedding_model_version,
                        embedding_dimension
                    )
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS semantic_index_entries (
                    entry_id TEXT PRIMARY KEY,
                    chunk_id TEXT NOT NULL,
                    document_id TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    embedding_model_id TEXT NOT NULL,
                    embedding_model_version TEXT NOT NULL,
                    embedding_dimension INTEGER NOT NULL,
                    semantic_index_version TEXT NOT NULL,
                    source_checksum TEXT NOT NULL,
                    content_fingerprint TEXT NOT NULL,
                    vector_json TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _document_from_row(row: sqlite3.Row) -> ProjectDocument:
        return ProjectDocument(
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            workspace_id=str(row["workspace_id"]),
            display_name=str(row["display_name"]),
            created_at=str(row["created_at"]),
            current_version_id=row["current_version_id"],
            status=IngestionStatus(str(row["status"])),
        )

    @staticmethod
    def _version_from_row(row: sqlite3.Row) -> ProjectDocumentVersion:
        return ProjectDocumentVersion(
            version_id=str(row["version_id"]),
            document_id=str(row["document_id"]),
            project_id=str(row["project_id"]),
            workspace_id=str(row["workspace_id"]),
            attachment_id=str(row["attachment_id"]),
            conversation_id=row["conversation_id"],
            session_id=row["session_id"],
            source_checksum=str(row["source_checksum"]),
            parser_version=str(row["parser_version"]),
            chunker_version=str(row["chunker_version"]),
            indexer_version=str(row["indexer_version"]),
            status=IngestionStatus(str(row["status"])),
            queued_at=str(row["queued_at"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            chunk_count=int(row["chunk_count"]),
            failure_code=row["failure_code"],
            failure_message=row["failure_message"],
            superseded_by=row["superseded_by"],
        )

    @staticmethod
    def _chunk_from_row(row: sqlite3.Row) -> DocumentChunk:
        return DocumentChunk(
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            version_id=str(row["version_id"]),
            project_id=str(row["project_id"]),
            attachment_id=str(row["attachment_id"]),
            sequence=int(row["sequence"]),
            start_offset=int(row["start_offset"]),
            end_offset=int(row["end_offset"]),
            content=str(row["content"]),
            source_checksum=str(row["source_checksum"]),
        )

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> IndexEntry:
        return IndexEntry(
            entry_id=str(row["entry_id"]),
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            version_id=str(row["version_id"]),
            project_id=str(row["project_id"]),
            indexer_version=str(row["indexer_version"]),
            embedding_ref=str(row["embedding_ref"]),
            terms=tuple(json.loads(str(row["terms"]))),
            status=IngestionStatus(str(row["status"])),
        )


def _terms(value: str) -> set[str]:
    normalized = value.casefold()
    return {term for term in re.findall(r"[\wÀ-ÿ]+", normalized) if len(term) > 2}


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _duplicate_key(value: str) -> str:
    normalized = " ".join(_semantic_terms(value))
    if len(normalized) > 280:
        normalized = normalized[:280]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _content_fingerprint(value: str, capability: EmbeddingCapability | None = None) -> str:
    normalized = " ".join(sorted(_semantic_terms(value)))
    binding = ""
    if capability is not None:
        binding = "\0".join(
            (
                capability.provider_id,
                capability.model_id,
                capability.model_version,
                str(capability.dimension),
                capability.normalization_version,
            )
        )
    return hashlib.sha256(f"{binding}\0{normalized}".encode("utf-8")).hexdigest()


def _local_embedding(value: str) -> tuple[float, ...]:
    vector = [0.0] * EMBEDDING_DIMENSION
    for term in _semantic_terms(value):
        digest = hashlib.sha256(term.encode("utf-8")).digest()
        index = digest[0] % EMBEDDING_DIMENSION
        weight = 1.0 + (digest[1] / 2550.0)
        vector[index] += weight
    norm = math.sqrt(sum(component * component for component in vector))
    if norm == 0:
        return tuple(vector)
    return tuple(component / norm for component in vector)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _rrf(rank: int | None) -> float:
    if rank is None:
        return 0.0
    return 1.0 / (60.0 + rank)


def _retrieval_mode(lexical_rank: object, semantic_rank: object) -> str:
    if lexical_rank is not None and semantic_rank is not None:
        return "hybrid"
    if semantic_rank is not None:
        return "semantic"
    return "lexical"


def _requested_retrieval_mode(value: str) -> str:
    aliases = {
        "semantic": "canonical",
        "canonical_similarity": "canonical",
        "learned_semantic": "learned",
        "learned_hybrid": "hybrid",
    }
    mode = aliases.get(value, value)
    if mode not in {"lexical", "canonical", "learned", "hybrid"}:
        raise ValidationError("invalid_retrieval_mode")
    return mode


def _capability_ready(status: EmbeddingCapabilityStatus) -> bool:
    return status in {EmbeddingCapabilityStatus.AVAILABLE, EmbeddingCapabilityStatus.READY}


def _canonical_term(term: str) -> str:
    synonyms = {
        "automovel": "vehicle",
        "automóvel": "vehicle",
        "carro": "vehicle",
        "veiculo": "vehicle",
        "veículo": "vehicle",
        "vehicle": "vehicle",
        "rapido": "fast",
        "rápido": "fast",
        "veloz": "fast",
        "fast": "fast",
        "corrigir": "repair",
        "consertar": "repair",
        "repair": "repair",
        "fix": "repair",
        "erro": "failure",
        "falha": "failure",
        "failure": "failure",
        "módulo": "module",
        "modulo": "module",
        "module": "module",
        "cachorro": "dog",
        "cão": "dog",
        "cao": "dog",
        "dog": "dog",
        "protege": "protect",
        "proteger": "protect",
        "guards": "protect",
        "protect": "protect",
    }
    return synonyms.get(term, term)


def _semantic_terms(value: str) -> set[str]:
    return {_canonical_term(term) for term in _terms(value)}


def _now() -> str:
    return datetime.now(UTC).isoformat()
