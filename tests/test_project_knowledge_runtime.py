from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from synapse.conversations.models import ConversationAttachment
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.memory.store import MemoryStore
from synapse.project_knowledge.embedding_providers import (
    LearnedEmbeddingModelConfig,
    LocalSentenceTransformersEmbeddingProvider,
    StaticLearnedEmbeddingProvider,
    UnconfiguredLearnedEmbeddingProvider,
)
from synapse.project_knowledge.models import EmbeddingCapabilityStatus, IngestionStatus
from synapse.project_knowledge.runtime import ProjectKnowledgeRuntime


class ProjectKnowledgeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = Settings(
            project_root=Path(__file__).resolve().parents[1],
            data_dir=Path(self.directory.name) / "data",
            host="127.0.0.1",
            port=8717,
            default_actor_id="local_owner",
        )
        self.data_dir = DataDir(settings.data_dir)
        self.events = EventBus(settings.data_dir)
        permissions_path = settings.data_dir / "config" / "permissions.yaml"
        permissions_path.parent.mkdir(parents=True, exist_ok=True)
        permissions_path.write_text(
            json.dumps({"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}}),
            encoding="utf-8",
        )
        self.permissions = PermissionManager(settings.data_dir, self.events)
        self.context = PermissionContext(actor_id="local_owner", actor_type="user")
        self.memory = MemoryStore(self.data_dir, self.permissions, self.events)
        self.runtime = ProjectKnowledgeRuntime(self.data_dir, self.events, self.memory)

    def semantic_runtime(
        self,
        status: EmbeddingCapabilityStatus = EmbeddingCapabilityStatus.AVAILABLE,
        learned_embedding_provider=None,
    ) -> ProjectKnowledgeRuntime:
        return ProjectKnowledgeRuntime(
            self.data_dir,
            self.events,
            self.memory,
            semantic_enabled=True,
            semantic_capability_status=status,
            learned_embedding_provider=learned_embedding_provider,
        )

    def attachment(
        self,
        name: str,
        content: str,
        *,
        conversation_id: str = "conversation-a",
        mime_type: str = "text/plain",
    ) -> ConversationAttachment:
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        storage_ref = f"conversations/{conversation_id}/attachments/storage/{checksum}-{name}"
        path = self.data_dir.resolve(storage_ref)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ConversationAttachment(
            attachment_id=f"attachment-{checksum[:8]}",
            filename=name,
            mime_type=mime_type,
            size=len(content.encode("utf-8")),
            storage_ref=storage_ref,
            checksum=checksum,
            conversation_id=conversation_id,
            owner_id="local_owner",
        )

    def test_schedule_is_not_indexed_and_restart_preserves_incomplete_state(self) -> None:
        attachment = self.attachment("briefing.txt", "fencing rollback memoria")

        status = self.runtime.schedule_attachment_ingestion(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id="session-a",
        )

        self.assertEqual(status, "scheduled")
        document = self.runtime.list_documents("project-a")[0]
        record = self.runtime.status(document.document_id)
        self.assertEqual(record.version.status, IngestionStatus.QUEUED)
        self.assertFalse(record.facts["document_indexed"])
        restarted = ProjectKnowledgeRuntime(self.data_dir, self.events, self.memory)
        restarted_record = restarted.status(document.document_id)
        self.assertEqual(restarted_record.version.status, IngestionStatus.QUEUED)
        self.assertEqual(restarted_record.chunks, ())

    def test_ingestion_lifecycle_chunks_index_and_retrieves_ready_evidence(self) -> None:
        attachment = self.attachment("briefing.md", "fencing rollback memoria projeto", mime_type="text/markdown")

        record = self.runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id="session-a",
        )

        self.assertEqual(record.document.status, IngestionStatus.READY)
        self.assertEqual(record.version.status, IngestionStatus.READY)
        self.assertEqual(record.version.chunk_count, 1)
        self.assertEqual(len(record.chunks), 1)
        self.assertEqual(len(record.index_entries), 1)
        chunk = record.chunks[0]
        entry = record.index_entries[0]
        self.assertNotEqual(record.document.document_id, record.version.version_id)
        self.assertNotEqual(record.version.version_id, chunk.chunk_id)
        self.assertNotEqual(chunk.chunk_id, entry.entry_id)
        self.assertEqual(chunk.source_checksum, attachment.checksum)

        evidence = self.runtime.retrieve(
            self.context,
            query="rollback",
            project_id="project-a",
            limit=5,
        )

        self.assertEqual(len(evidence), 1)
        self.assertNotEqual(evidence[0].evidence_id, record.document.document_id)
        self.assertEqual(evidence[0].document_id, record.document.document_id)
        self.assertEqual(evidence[0].version_id, record.version.version_id)
        self.assertFalse(evidence[0].trusted_instruction)

    def test_same_checksum_deduplicates_version_but_changed_content_stales_previous(self) -> None:
        first = self.attachment("briefing.txt", "usar motor alpha")
        first_record = self.runtime.ingest_attachment(
            self.context,
            first,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        duplicate_record = self.runtime.ingest_attachment(
            self.context,
            first,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        self.assertEqual(first_record.version.version_id, duplicate_record.version.version_id)

        changed = self.attachment("briefing.txt", "usar motor beta")
        changed_record = self.runtime.ingest_attachment(
            self.context,
            changed,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        self.assertNotEqual(first_record.version.version_id, changed_record.version.version_id)
        stale = self.runtime.get_version(first_record.version.version_id)
        self.assertEqual(stale.status, IngestionStatus.STALE)
        evidence = self.runtime.retrieve(self.context, query="alpha", project_id="project-a")
        self.assertEqual(evidence, [])
        self.assertEqual(
            self.runtime.retrieve(self.context, query="beta", project_id="project-a")[0].content,
            "usar motor beta",
        )

    def test_project_isolation_ready_only_remove_and_reindex(self) -> None:
        project_a = self.attachment("a.json", '{"topic":"fencing"}', mime_type="application/json")
        project_b = self.attachment("b.csv", "topic\nfencing", conversation_id="conversation-b", mime_type="text/csv")
        record_a = self.runtime.ingest_attachment(
            self.context,
            project_a,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        self.runtime.ingest_attachment(
            self.context,
            project_b,
            workspace_id="default",
            project_id="project-b",
            session_id=None,
        )

        self.assertEqual(
            {item.project_id for item in self.runtime.retrieve(self.context, query="fencing", project_id="project-a")},
            {"project-a"},
        )
        reindexed = self.runtime.reindex_document(record_a.document.document_id)
        self.assertEqual(reindexed.status, IngestionStatus.READY)
        self.assertNotEqual(reindexed.version_id, record_a.version.version_id)
        self.assertEqual(self.runtime.get_version(record_a.version.version_id).status, IngestionStatus.STALE)

        removed = self.runtime.remove_document(record_a.document.document_id)
        self.assertEqual(removed.status, IngestionStatus.REMOVED)
        self.assertEqual(
            self.runtime.retrieve(self.context, query="fencing", project_id="project-a"),
            [],
        )

    def test_ingestion_failure_is_persistent_and_not_ready(self) -> None:
        attachment = ConversationAttachment(
            attachment_id="missing",
            filename="missing.txt",
            mime_type="text/plain",
            size=10,
            storage_ref="missing/file.txt",
            checksum="checksum",
            conversation_id="conversation-a",
            owner_id="local_owner",
        )

        with self.assertRaises(FileNotFoundError):
            self.runtime.ingest_attachment(
                self.context,
                attachment,
                workspace_id="default",
                project_id="project-a",
                session_id=None,
            )

        document = self.runtime.list_documents("project-a")[0]
        record = self.runtime.status(document.document_id)
        self.assertEqual(record.version.status, IngestionStatus.FAILED)
        self.assertEqual(record.version.failure_code, "FileNotFoundError")
        self.assertEqual(self.runtime.retrieve(self.context, query="checksum", project_id="project-a"), [])

    def test_ranking_dedup_budget_and_diversity_are_deterministic(self) -> None:
        first = self.attachment("a.txt", "alpha beta gamma factual source one")
        second = self.attachment("b.txt", "alpha beta gamma factual source one")
        third = self.attachment("c.txt", "alpha beta delta distinct source two")
        repeated = self.attachment(
            "d.txt",
            "alpha beta repeated block\n\nalpha beta repeated block\n\nalpha beta repeated block",
        )
        for item in (first, second, third, repeated):
            self.runtime.ingest_attachment(
                self.context,
                item,
                workspace_id="default",
                project_id="project-a",
                session_id=None,
            )

        first_selection = self.runtime.retrieve(
            self.context,
            query="alpha beta gamma",
            project_id="project-a",
            limit=3,
            max_chunks_per_document=1,
        )
        second_selection = self.runtime.retrieve(
            self.context,
            query="alpha beta gamma",
            project_id="project-a",
            limit=3,
            max_chunks_per_document=1,
        )

        self.assertEqual([item.chunk_id for item in first_selection], [item.chunk_id for item in second_selection])
        self.assertLessEqual(len(first_selection), 3)
        self.assertEqual(len({item.document_id for item in first_selection}), len(first_selection))
        self.assertTrue(all(item.relevance_facts["ranker_version"] for item in first_selection))
        self.assertTrue(all(item.relevance_facts["semantic_score"] is None for item in first_selection))
        duplicate = next(item for item in first_selection if item.relevance_facts["duplicate_count"] == 2)
        self.assertEqual(len(duplicate.relevance_facts["duplicate_sources"]), 2)
        self.assertFalse(duplicate.trusted_instruction)

    def test_context_budget_and_chunk_neighborhood_are_controlled(self) -> None:
        content = "\n".join(
            [
                "alpha beta gamma " * 260,
                "neighbor context explains structural detail",
                "alpha beta gamma " * 260,
            ]
        )
        attachment = self.attachment("long.txt", content)
        self.runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        evidence = self.runtime.retrieve(
            self.context,
            query="alpha beta gamma",
            project_id="project-a",
            limit=2,
            max_characters=4_000,
            max_chunks_per_document=2,
            include_neighbors=True,
        )

        self.assertLessEqual(len(evidence), 2)
        self.assertLessEqual(sum(len(item.content) for item in evidence), 4_000)
        self.assertLessEqual(len({item.chunk_id for item in evidence}), 2)

    def test_weak_query_and_cross_project_duplicate_do_not_leak(self) -> None:
        project_a = self.attachment("a.txt", "alpha project only")
        project_b = self.attachment("b.txt", "alpha project only", conversation_id="conversation-b")
        self.runtime.ingest_attachment(
            self.context,
            project_a,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        self.runtime.ingest_attachment(
            self.context,
            project_b,
            workspace_id="default",
            project_id="project-b",
            session_id=None,
        )

        self.assertEqual(self.runtime.retrieve(self.context, query="missing", project_id="project-a"), [])
        evidence = self.runtime.retrieve(self.context, query="alpha", project_id="project-a")
        self.assertEqual({item.project_id for item in evidence}, {"project-a"})

    def test_semantic_embedding_generation_cache_and_paraphrase_retrieval(self) -> None:
        runtime = self.semantic_runtime()
        attachment = self.attachment("cars.txt", "carro rápido precisa de conserto")
        record = runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        self.assertEqual(record.facts["semantic_capability_status"], "available")
        self.assertEqual(record.facts["semantic_index_entry_count"], 1)
        evidence = runtime.retrieve(
            self.context,
            query="automóvel veloz precisa repair",
            project_id="project-a",
            semantic_enabled=True,
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].document_id, record.document.document_id)
        self.assertEqual(evidence[0].relevance_facts["retrieval_mode"], "hybrid")
        self.assertIsNotNone(evidence[0].relevance_facts["semantic_score"])
        self.assertFalse(evidence[0].trusted_instruction)

        cache_count_before = self._semantic_cache_count()
        runtime.retrieve(
            self.context,
            query="automóvel veloz precisa repair",
            project_id="project-a",
            semantic_enabled=True,
        )
        self.assertEqual(self._semantic_cache_count(), cache_count_before)

    def test_semantic_unavailable_falls_back_to_lexical(self) -> None:
        runtime = self.semantic_runtime(EmbeddingCapabilityStatus.UNAVAILABLE)
        attachment = self.attachment("lexical.txt", "fencing rollback exact keyword")
        record = runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        self.assertEqual(record.facts["semantic_capability_status"], "unavailable")
        self.assertEqual(record.facts["semantic_index_entry_count"], 0)
        evidence = runtime.retrieve(
            self.context,
            query="rollback",
            project_id="project-a",
            semantic_enabled=True,
        )

        self.assertEqual(len(evidence), 1)
        self.assertIn(evidence[0].relevance_facts["retrieval_mode"], {"lexical", "hybrid"})
        self.assertEqual(evidence[0].relevance_facts["semantic_capability_status"], "unavailable")

    def test_learned_embedding_provider_retrieves_paraphrase_without_canonical_match(self) -> None:
        learned = StaticLearnedEmbeddingProvider(
            {
                "authentication middleware refreshes expired tokens": (1.0, 0.0, 0.0, 0.0, 0.0, 0.0),
                "login session renews stale credentials": (0.98, 0.02, 0.0, 0.0, 0.0, 0.0),
                "unrelated gardening notes": (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
            }
        )
        runtime = self.semantic_runtime(learned_embedding_provider=learned)
        record = runtime.ingest_attachment(
            self.context,
            self.attachment("auth.txt", "authentication middleware refreshes expired tokens"),
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        lexical = runtime.retrieve(
            self.context,
            query="login session renews stale credentials",
            project_id="project-a",
            semantic_enabled=False,
            retrieval_mode="lexical",
        )
        learned_results = runtime.retrieve(
            self.context,
            query="login session renews stale credentials",
            project_id="project-a",
            semantic_enabled=True,
            retrieval_mode="learned",
        )

        self.assertEqual(lexical, [])
        self.assertEqual(len(learned_results), 1)
        self.assertEqual(learned_results[0].document_id, record.document.document_id)
        self.assertEqual(
            learned_results[0].relevance_facts["learned_semantic_capability_status"],
            "available",
        )
        self.assertEqual(learned_results[0].relevance_facts["requested_retrieval_mode"], "learned")
        self.assertFalse(learned_results[0].trusted_instruction)

    def test_learned_embedding_cache_is_isolated_from_canonical_similarity(self) -> None:
        learned = StaticLearnedEmbeddingProvider(
            {"carro rápido precisa de conserto": (1.0, 0.0, 0.0, 0.0, 0.0, 0.0)}
        )
        runtime = self.semantic_runtime(learned_embedding_provider=learned)
        runtime.ingest_attachment(
            self.context,
            self.attachment("cars.txt", "carro rápido precisa de conserto"),
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        with runtime._connect() as db:
            rows = db.execute(
                """
                SELECT embedding_model_id, embedding_model_version, embedding_dimension
                FROM semantic_embedding_cache
                ORDER BY embedding_model_id
                """
            ).fetchall()

        cache_keys = {(str(row[0]), str(row[1]), int(row[2])) for row in rows}
        self.assertIn(("synapse-local-canonical-embedding", "v1", 32), cache_keys)
        self.assertIn(("test-learned-local", "v1", 6), cache_keys)

    def test_learned_embedding_unconfigured_does_not_block_lexical_fallback(self) -> None:
        runtime = self.semantic_runtime(
            learned_embedding_provider=UnconfiguredLearnedEmbeddingProvider()
        )
        record = runtime.ingest_attachment(
            self.context,
            self.attachment("briefing.txt", "rollback journal receipts"),
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )

        evidence = runtime.retrieve(
            self.context,
            query="rollback",
            project_id="project-a",
            semantic_enabled=True,
            retrieval_mode="hybrid",
        )

        self.assertEqual(evidence[0].document_id, record.document.document_id)
        self.assertEqual(
            evidence[0].relevance_facts["learned_semantic_capability_status"],
            "unconfigured",
        )
        self.assertIn(evidence[0].relevance_facts["retrieval_mode"], {"lexical", "hybrid"})

    def test_local_sentence_transformers_provider_lazy_loads_and_applies_e5_prefixes(self) -> None:
        model_path = Path(self.directory.name) / "embedding-model"
        model_path.mkdir()
        calls: list[str] = []

        class FakeModel:
            def encode(self, values, normalize_embeddings: bool):
                calls.append(values[0])
                self_normalized = normalize_embeddings
                if not self_normalized:
                    raise AssertionError("expected normalized embeddings")
                return [[1.0, 0.0, 0.0]]

        load_calls: list[str] = []

        def load_model(path: str):
            load_calls.append(path)
            return FakeModel()

        provider = LocalSentenceTransformersEmbeddingProvider(
            LearnedEmbeddingModelConfig(
                model_id="intfloat/multilingual-e5-small",
                model_version="test-revision",
                dimension=3,
                model_path=model_path,
            ),
            model_loader=load_model,
        )

        initial_capability = provider.capability()
        self.assertEqual(initial_capability.status, EmbeddingCapabilityStatus.AVAILABLE)
        self.assertTrue(initial_capability.configured)
        self.assertFalse(initial_capability.loaded)
        self.assertEqual(load_calls, [])
        self.assertEqual(provider.embed("como buscar contexto", kind="query"), (1.0, 0.0, 0.0))
        self.assertEqual(provider.embed("documento de contexto", kind="passage"), (1.0, 0.0, 0.0))
        self.assertTrue(provider.capability().loaded)
        self.assertEqual(load_calls, [str(model_path)])
        self.assertEqual(calls, ["query: como buscar contexto", "passage: documento de contexto"])

    def test_semantic_project_isolation_top_k_and_removal(self) -> None:
        runtime = self.semantic_runtime()
        project_a = self.attachment("a.txt", "carro rápido")
        project_b = self.attachment("b.txt", "carro rápido", conversation_id="conversation-b")
        runtime.ingest_attachment(
            self.context,
            project_a,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        record_b = runtime.ingest_attachment(
            self.context,
            project_b,
            workspace_id="default",
            project_id="project-b",
            session_id=None,
        )

        evidence = runtime.retrieve(
            self.context,
            query="automóvel veloz",
            project_id="project-a",
            limit=1,
            semantic_enabled=True,
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual({item.project_id for item in evidence}, {"project-a"})
        runtime.remove_document(record_b.document.document_id)
        self.assertEqual(
            runtime.retrieve(
                self.context,
                query="automóvel veloz",
                project_id="project-b",
                semantic_enabled=True,
            ),
            [],
        )

    def test_semantic_version_mismatch_and_reindex_do_not_rechunk(self) -> None:
        runtime = self.semantic_runtime()
        attachment = self.attachment("versioned.txt", "carro rápido")
        record = runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        original_chunk_ids = [chunk.chunk_id for chunk in record.chunks]
        with runtime._connect() as db:
            db.execute(
                "UPDATE semantic_index_entries SET embedding_model_version=? WHERE version_id=?",
                ("old-version", record.version.version_id),
            )

        self.assertEqual(runtime.reconcile_semantic_index_versions(), 1)
        self.assertEqual(
            runtime.retrieve(
                self.context,
                query="automóvel veloz",
                project_id="project-a",
                semantic_enabled=True,
            ),
            [],
        )
        reindexed = runtime.reindex_document(record.document.document_id)
        refreshed = runtime.status(record.document.document_id)
        self.assertEqual(reindexed.status, IngestionStatus.READY)
        self.assertEqual(len(refreshed.chunks), len(original_chunk_ids))
        self.assertNotEqual([chunk.chunk_id for chunk in refreshed.chunks], original_chunk_ids)
        self.assertEqual(refreshed.facts["semantic_index_entry_count"], 1)

    def test_lexical_only_mode_does_not_generate_query_embedding(self) -> None:
        runtime = self.semantic_runtime()
        attachment = self.attachment("lexical-only.txt", "fencing rollback")
        runtime.ingest_attachment(
            self.context,
            attachment,
            workspace_id="default",
            project_id="project-a",
            session_id=None,
        )
        cache_count_before = self._semantic_cache_count()

        evidence = runtime.retrieve(
            self.context,
            query="rollback",
            project_id="project-a",
            semantic_enabled=False,
        )

        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0].relevance_facts["retrieval_mode"], "lexical")
        self.assertEqual(self._semantic_cache_count(), cache_count_before)

    def _semantic_cache_count(self) -> int:
        with self.runtime._connect() as db:
            row = db.execute("SELECT COUNT(*) FROM semantic_embedding_cache").fetchone()
        return int(row[0])


if __name__ == "__main__":
    unittest.main()
