from __future__ import annotations

import hashlib
import json
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from synapse.conversations.models import ConversationAttachment
from synapse.core.config import Settings
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.permissions import PermissionContext, PermissionManager
from synapse.memory.store import MemoryStore
from synapse.project_knowledge.models import EmbeddingCapabilityStatus
from synapse.project_knowledge.runtime import ProjectKnowledgeRuntime


@dataclass(frozen=True)
class EvaluationQuery:
    query: str
    project_id: str
    category: str
    expected_documents: frozenset[str]


def make_runtime() -> tuple[tempfile.TemporaryDirectory[str], ProjectKnowledgeRuntime, PermissionContext]:
    directory = tempfile.TemporaryDirectory()
    settings = Settings(
        project_root=Path(__file__).resolve().parents[1],
        data_dir=Path(directory.name) / "data",
        host="127.0.0.1",
        port=8717,
        default_actor_id="local_owner",
    )
    data_dir = DataDir(settings.data_dir)
    events = EventBus(settings.data_dir)
    permissions_path = settings.data_dir / "config" / "permissions.yaml"
    permissions_path.parent.mkdir(parents=True, exist_ok=True)
    permissions_path.write_text(
        json.dumps({"subjects": {"local_owner": ["*"], "user:local_owner": ["*"]}}),
        encoding="utf-8",
    )
    permissions = PermissionManager(settings.data_dir, events)
    memory = MemoryStore(data_dir, permissions, events)
    runtime = ProjectKnowledgeRuntime(data_dir, events, memory, semantic_enabled=True)
    return directory, runtime, PermissionContext(actor_id="local_owner", actor_type="user")


def attachment(data_dir: DataDir, name: str, content: str, conversation_id: str) -> ConversationAttachment:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    storage_ref = f"conversations/{conversation_id}/attachments/storage/{checksum}-{name}"
    path = data_dir.resolve(storage_ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ConversationAttachment(
        attachment_id=f"attachment-{checksum[:8]}",
        filename=name,
        mime_type="text/plain",
        size=len(content.encode("utf-8")),
        storage_ref=storage_ref,
        checksum=checksum,
        conversation_id=conversation_id,
        owner_id="local_owner",
    )


def build_corpus(runtime: ProjectKnowledgeRuntime, context: PermissionContext) -> dict[str, str]:
    documents: dict[str, str] = {}
    specs = [
        ("project-a", "exact-rollback.txt", "fencing rollback preserves receipts and journal evidence"),
        ("project-a", "vehicle-repair.txt", "carro rápido precisa de conserto"),
        ("project-a", "module-failure.txt", "erro crítico exige corrigir módulo"),
        ("project-a", "vehicle-distractor.txt", "carro rápido azul decorativo"),
        ("project-a", "duplicate-a.txt", "fencing rollback preserves receipts and journal evidence"),
        ("project-a", "near-duplicate.txt", "fencing rollback preserves receipt and journal evidence"),
        ("project-b", "cross-project-dog.txt", "cachorro fiel protege casa"),
    ]
    for project_id, filename, content in specs:
        item = attachment(runtime.data_dir, filename, content, f"conversation-{project_id}-{filename}")
        record = runtime.ingest_attachment(
            context,
            item,
            workspace_id="default",
            project_id=project_id,
            session_id=None,
        )
        documents[filename] = record.document.document_id
    return documents


def query_set(documents: dict[str, str]) -> list[EvaluationQuery]:
    return [
        EvaluationQuery(
            "rollback journal receipts",
            "project-a",
            "exact lexical",
            frozenset({documents["exact-rollback.txt"], documents["duplicate-a.txt"], documents["near-duplicate.txt"]}),
        ),
        EvaluationQuery(
            "automóvel veloz repair",
            "project-a",
            "paraphrase",
            frozenset({documents["vehicle-repair.txt"]}),
        ),
        EvaluationQuery(
            "failure repair module",
            "project-a",
            "synonym/concept",
            frozenset({documents["module-failure.txt"]}),
        ),
        EvaluationQuery(
            "automóvel veloz conserto",
            "project-a",
            "distractor",
            frozenset({documents["vehicle-repair.txt"]}),
        ),
        EvaluationQuery("quasar orbital astronomy", "project-a", "weak/unknown", frozenset()),
        EvaluationQuery("dog protect home", "project-a", "cross-project", frozenset()),
    ]


def run_evaluation(
    runtime: ProjectKnowledgeRuntime,
    context: PermissionContext,
    queries: list[EvaluationQuery],
    mode: str,
) -> dict[str, object]:
    started = time.perf_counter()
    rows = []
    for item in queries:
        evidence = runtime.retrieve(
            context,
            query=item.query,
            project_id=item.project_id,
            limit=5,
            semantic_enabled=mode in {"canonical", "semantic", "learned", "hybrid"},
            retrieval_mode=mode,
            include_neighbors=False,
        )
        selected_document_ids = [result.document_id for result in evidence]
        rows.append((item, selected_document_ids, evidence))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "mode": mode,
        "elapsed_ms": elapsed_ms,
        "metrics": metrics(rows),
        "by_category": {
            category: metrics([row for row in rows if row[0].category == category])
            for category in sorted({row[0].category for row in rows})
        },
        "rows": rows,
    }


def metrics(rows) -> dict[str, float]:
    if not rows:
        return {
            "HitRate@1": 0.0,
            "HitRate@3": 0.0,
            "HitRate@5": 0.0,
            "MRR": 0.0,
            "Precision": 0.0,
            "ZeroResultCorrectness": 0.0,
            "Recall@5": 0.0,
        }
    h1 = h3 = h5 = reciprocal = precision_total = zero_correct = recall_total = 0.0
    answerable = 0
    weak = 0
    for item, selected, _evidence in rows:
        expected = item.expected_documents
        if not expected:
            weak += 1
            if not selected:
                zero_correct += 1.0
            continue
        answerable += 1
        ranks = [index + 1 for index, document_id in enumerate(selected) if document_id in expected]
        if ranks and ranks[0] <= 1:
            h1 += 1.0
        if ranks and ranks[0] <= 3:
            h3 += 1.0
        if ranks and ranks[0] <= 5:
            h5 += 1.0
        if ranks:
            reciprocal += 1.0 / ranks[0]
        precision_total += (
            sum(1 for document_id in selected if document_id in expected) / len(selected)
            if selected
            else 0.0
        )
        recall_total += len(set(selected) & expected) / len(expected)
    return {
        "HitRate@1": h1 / answerable if answerable else 0.0,
        "HitRate@3": h3 / answerable if answerable else 0.0,
        "HitRate@5": h5 / answerable if answerable else 0.0,
        "MRR": reciprocal / answerable if answerable else 0.0,
        "Precision": precision_total / answerable if answerable else 0.0,
        "ZeroResultCorrectness": zero_correct / weak if weak else 0.0,
        "Recall@5": recall_total / answerable if answerable else 0.0,
    }


def test_retrieval_quality_evaluation_corpus() -> None:
    directory, runtime, context = make_runtime()
    try:
        documents = build_corpus(runtime, context)
        queries = query_set(documents)
        results = {
            mode: run_evaluation(runtime, context, queries, mode)
            for mode in ("lexical", "canonical", "learned", "hybrid")
        }

        lexical = results["lexical"]["metrics"]
        canonical = results["canonical"]["metrics"]
        learned = results["learned"]["metrics"]
        hybrid = results["hybrid"]["metrics"]
        assert lexical["HitRate@1"] >= 0.4
        assert canonical["HitRate@1"] >= lexical["HitRate@1"]
        assert learned["HitRate@1"] == 0.0
        assert hybrid["HitRate@1"] >= lexical["HitRate@1"]
        assert results["lexical"]["by_category"]["paraphrase"]["HitRate@1"] == 0.0
        assert results["canonical"]["by_category"]["paraphrase"]["HitRate@1"] == 1.0
        assert results["learned"]["by_category"]["paraphrase"]["HitRate@1"] == 0.0
        assert results["canonical"]["by_category"]["cross-project"]["ZeroResultCorrectness"] == 1.0
        assert results["learned"]["by_category"]["cross-project"]["ZeroResultCorrectness"] == 1.0
        assert results["hybrid"]["by_category"]["weak/unknown"]["ZeroResultCorrectness"] == 1.0

        first_hybrid = run_evaluation(runtime, context, queries, "hybrid")
        second_hybrid = run_evaluation(runtime, context, queries, "hybrid")
        first_rows = first_hybrid["rows"]
        second_rows = second_hybrid["rows"]
        assert [
            selected
            for _query, selected, _evidence in first_rows
        ] == [
            selected
            for _query, selected, _evidence in second_rows
        ]
        for _query, _selected, evidence in first_rows:
            for item in evidence:
                assert item.trusted_instruction is False
                assert item.document_id
                assert item.version_id
                assert item.chunk_id
                assert item.provenance["source_checksum"]
    finally:
        directory.cleanup()


def test_semantic_unavailable_still_evaluates_lexical_fallback() -> None:
    directory, runtime, context = make_runtime()
    runtime.semantic_capability_status = EmbeddingCapabilityStatus.UNAVAILABLE
    try:
        documents = build_corpus(runtime, context)
        evidence = runtime.retrieve(
            context,
            query="rollback journal receipts",
            project_id="project-a",
            semantic_enabled=True,
            retrieval_mode="hybrid",
        )
        assert evidence
        assert evidence[0].relevance_facts["retrieval_mode"] == "lexical"
        assert evidence[0].relevance_facts["semantic_capability_status"] == "unavailable"
        assert evidence[0].document_id in {
            documents["exact-rollback.txt"],
            documents["duplicate-a.txt"],
            documents["near-duplicate.txt"],
        }
    finally:
        directory.cleanup()
