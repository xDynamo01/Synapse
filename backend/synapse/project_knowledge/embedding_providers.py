from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from synapse.project_knowledge.models import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL_ID,
    EMBEDDING_MODEL_VERSION,
    SEMANTIC_INDEX_VERSION,
    EmbeddingCapability,
    EmbeddingCapabilityStatus,
)

CANONICAL_NORMALIZATION_VERSION = "canonical-hash-v1"
LEARNED_NORMALIZATION_VERSION = "learned-normalized-v1"


class EmbeddingProvider(Protocol):
    def capability(self) -> EmbeddingCapability: ...

    def embed(self, text: str, *, kind: str) -> tuple[float, ...]: ...


@dataclass(frozen=True)
class LearnedEmbeddingModelConfig:
    model_id: str
    model_version: str
    dimension: int
    model_path: Path | None = None
    license: str = "unknown"
    runtime: str = "unconfigured"
    footprint_mb: int | None = None
    normalization_version: str = LEARNED_NORMALIZATION_VERSION
    device: str = "cpu"


class UnconfiguredLearnedEmbeddingProvider:
    def __init__(
        self,
        *,
        model_id: str = "intfloat/multilingual-e5-small",
        model_version: str = "unconfigured",
        dimension: int = 384,
        reason: str = "local learned embedding model is not configured",
    ) -> None:
        self._capability = EmbeddingCapability(
            status=EmbeddingCapabilityStatus.UNCONFIGURED,
            provider_id="synapse_learned_local",
            model_id=model_id,
            model_version=model_version,
            dimension=dimension,
            semantic_index_version=SEMANTIC_INDEX_VERSION,
            normalization_version=LEARNED_NORMALIZATION_VERSION,
            learned_semantic=True,
            configured=False,
            loaded=False,
            device="cpu",
            reason=reason,
        )

    def capability(self) -> EmbeddingCapability:
        return self._capability

    def embed(self, text: str, *, kind: str) -> tuple[float, ...]:
        del text
        del kind
        raise RuntimeError("learned embedding provider is unconfigured")


class LocalSentenceTransformersEmbeddingProvider:
    """Lazy adapter for a local SentenceTransformers-compatible model path."""

    def __init__(
        self,
        config: LearnedEmbeddingModelConfig,
        model_loader: Callable[[str], object] | None = None,
    ) -> None:
        self.config = config
        self._model: object | None = None
        self._failed_reason: str | None = None
        self._model_loader = model_loader

    def capability(self) -> EmbeddingCapability:
        if self.config.model_path is None:
            status = EmbeddingCapabilityStatus.UNCONFIGURED
            reason = "model_path is not configured"
        elif not self.config.model_path.exists():
            status = EmbeddingCapabilityStatus.UNAVAILABLE
            reason = "configured model_path does not exist"
        elif self._failed_reason:
            status = EmbeddingCapabilityStatus.FAILED
            reason = self._failed_reason
        else:
            status = EmbeddingCapabilityStatus.AVAILABLE
            reason = None
        return EmbeddingCapability(
            status=status,
            provider_id="synapse_learned_local",
            model_id=self.config.model_id,
            model_version=self.config.model_version,
            dimension=self.config.dimension,
            semantic_index_version=SEMANTIC_INDEX_VERSION,
            normalization_version=self.config.normalization_version,
            learned_semantic=True,
            configured=self.config.model_path is not None and self.config.model_path.exists(),
            loaded=self._model is not None,
            device=self.config.device,
            reason=reason,
        )

    def embed(self, text: str, *, kind: str) -> tuple[float, ...]:
        capability = self.capability()
        if capability.status not in {
            EmbeddingCapabilityStatus.AVAILABLE,
            EmbeddingCapabilityStatus.READY,
        }:
            raise RuntimeError(capability.reason or capability.status.value)
        try:
            model = self._load_model()
            raw = model.encode([self._format_text(text, kind=kind)], normalize_embeddings=True)[0]  # type: ignore[attr-defined]
            vector = tuple(float(value) for value in raw)
        except Exception as exc:  # pragma: no cover - depends on optional local runtime
            self._failed_reason = type(exc).__name__
            raise
        if len(vector) != self.config.dimension:
            self._failed_reason = "embedding_dimension_mismatch"
            raise RuntimeError("embedding_dimension_mismatch")
        return vector

    def _load_model(self) -> object:
        if self._model is None:
            assert self.config.model_path is not None
            if self._model_loader is not None:
                self._model = self._model_loader(str(self.config.model_path))
            else:
                try:
                    from sentence_transformers import SentenceTransformer
                except Exception as exc:  # pragma: no cover - optional dependency
                    self._failed_reason = "sentence_transformers_not_available"
                    raise RuntimeError("sentence_transformers_not_available") from exc
                self._model = SentenceTransformer(
                    str(self.config.model_path),
                    local_files_only=True,
                    device=self.config.device,
                )
        return self._model

    @staticmethod
    def _format_text(text: str, *, kind: str) -> str:
        if kind == "query":
            return f"query: {text}"
        if kind == "passage":
            return f"passage: {text}"
        raise RuntimeError("invalid_embedding_kind")


class StaticLearnedEmbeddingProvider:
    """Test provider that behaves like learned semantic embeddings without framework coupling."""

    def __init__(
        self,
        embeddings: Mapping[str, tuple[float, ...]],
        *,
        model_id: str = "test-learned-local",
        model_version: str = "v1",
        dimension: int = 6,
    ) -> None:
        self.embeddings = dict(embeddings)
        self._capability = EmbeddingCapability(
            status=EmbeddingCapabilityStatus.AVAILABLE,
            provider_id="synapse_learned_local",
            model_id=model_id,
            model_version=model_version,
            dimension=dimension,
            semantic_index_version=SEMANTIC_INDEX_VERSION,
            normalization_version=LEARNED_NORMALIZATION_VERSION,
            learned_semantic=True,
            configured=True,
            loaded=True,
            device="test",
        )

    def capability(self) -> EmbeddingCapability:
        return self._capability

    def embed(self, text: str, *, kind: str) -> tuple[float, ...]:
        normalized = " ".join(text.casefold().split())
        prefixed = f"{kind}: {normalized}"
        vector = self.embeddings.get(prefixed)
        if vector is not None:
            if len(vector) != self._capability.dimension:
                raise RuntimeError("embedding_dimension_mismatch")
            return vector
        vector = self.embeddings.get(normalized)
        if vector is None:
            return (0.0,) * self._capability.dimension
        if len(vector) != self._capability.dimension:
            raise RuntimeError("embedding_dimension_mismatch")
        return vector


def canonical_embedding_capability(status: EmbeddingCapabilityStatus) -> EmbeddingCapability:
    return EmbeddingCapability(
        status=status,
        provider_id="synapse_canonical_similarity",
        model_id=EMBEDDING_MODEL_ID,
        model_version=EMBEDDING_MODEL_VERSION,
        dimension=EMBEDDING_DIMENSION,
        semantic_index_version=SEMANTIC_INDEX_VERSION,
        normalization_version=CANONICAL_NORMALIZATION_VERSION,
        learned_semantic=False,
        configured=True,
        loaded=True,
        device="cpu",
        reason=None if status in {EmbeddingCapabilityStatus.AVAILABLE, EmbeddingCapabilityStatus.READY} else status.value,
    )


def learned_embedding_provider_from_env(
    *,
    data_dir: object,
) -> EmbeddingProvider:
    enabled = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_LEARNED_EMBEDDINGS", "").casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        return UnconfiguredLearnedEmbeddingProvider(reason="learned embeddings are not enabled")
    model_id = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_ID", "intfloat/multilingual-e5-small")
    model_version = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_VERSION", "unknown")
    model_path_value = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_MODEL_PATH")
    configured_path = Path(model_path_value) if model_path_value else None
    model_path = configured_path or _default_model_path(data_dir=data_dir, model_id=model_id)
    if model_version == "unknown" and model_path is not None and model_path.parent.name == "snapshots":
        model_version = model_path.name
    dimension = int(os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_DIMENSION", "384"))
    device = os.environ.get("SYNAPSE_PROJECT_KNOWLEDGE_EMBEDDING_DEVICE", "cpu")
    return LocalSentenceTransformersEmbeddingProvider(
        LearnedEmbeddingModelConfig(
            model_id=model_id,
            model_version=model_version,
            dimension=dimension,
            model_path=model_path,
            license="MIT",
            runtime="sentence-transformers",
            footprint_mb=None,
            device=device,
        )
    )


def _default_model_path(*, data_dir: object, model_id: str) -> Path:
    root = cast(str | Path, getattr(data_dir, "root", data_dir))
    model_root = Path(root).resolve() / "models" / "embeddings"
    direct_path = model_root / model_id.replace("/", "--")
    if direct_path.exists():
        return direct_path
    cache_root = model_root / f"models--{model_id.replace('/', '--')}" / "snapshots"
    if cache_root.exists():
        snapshots = sorted(
            (path for path in cache_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if snapshots:
            return snapshots[0]
    return direct_path
