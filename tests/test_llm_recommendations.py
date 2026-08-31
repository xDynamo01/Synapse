from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from synapse.model_hub.models import ModelCatalogEntry, ModelProviderInfo
from synapse.model_hub.recommendations import build_llm_recommendations


def provider(provider_id: str, active: bool = True) -> ModelProviderInfo:
    return ModelProviderInfo(
        provider_id=provider_id,
        display_name=provider_id.title(),
        status="available" if active else "unavailable",
        endpoint=None,
        active=active,
        default_model=None,
        model_count=0,
        last_refreshed_at=None,
        metadata={},
    )


def model(
    model_id: str,
    name: str,
    provider: str,
    estimated_ram_gb: float,
    estimated_vram_gb: float,
    cpu_compatible: bool = True,
    gpu_compatible: bool = True,
) -> ModelCatalogEntry:
    return ModelCatalogEntry(
        id=model_id,
        name=name,
        provider=provider,
        runtime=provider,
        origin="test",
        type="chat",
        estimated_ram_gb=estimated_ram_gb,
        estimated_vram_gb=estimated_vram_gb,
        cpu_compatible=cpu_compatible,
        gpu_compatible=gpu_compatible,
        status="available",
        metadata={},
    )


class LLMRecommendationTests(unittest.TestCase):
    def test_recommends_small_models_for_8gb_ram(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=8 * 1024**3,
            memory_available_bytes=7 * 1024**3,
            gpu=None,
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[],
            providers=[provider("lmstudio", False), provider("ollama", False)],
        )

        low_memory = next(item for item in recommendations if item.category == "Baixa memória")
        self.assertIn("1B", low_memory.model_name)
        self.assertEqual(low_memory.status, "recommended")

    def test_recommends_seven_b_models_for_16gb_ram(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=15 * 1024**3,
            gpu=None,
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[],
            providers=[provider("lmstudio"), provider("ollama")],
        )

        general = next(item for item in recommendations if item.category == "Geral")
        code = next(item for item in recommendations if item.category == "Programação")
        self.assertIn("7B", general.model_name)
        self.assertIn("7B", code.model_name)

    def test_recommends_fourteen_b_quality_models_for_32gb_ram(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=32 * 1024**3,
            memory_available_bytes=28 * 1024**3,
            gpu=None,
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[],
            providers=[provider("lmstudio"), provider("ollama")],
        )

        quality = next(item for item in recommendations if item.category == "Qualidade")
        self.assertIn("14B", quality.model_name)
        self.assertEqual(quality.status, "recommended")

    def test_installed_models_are_classified_by_fit(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=15 * 1024**3,
            gpu=None,
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[
                model("ollama:good", "good", "ollama", 4.0, 3.0),
                model("ollama:heavy", "heavy", "ollama", 24.0, 16.0),
            ],
            providers=[provider("ollama")],
        )

        installed = {item.model_name: item for item in recommendations if item.source == "installed"}
        self.assertEqual(installed["good"].status, "recommended")
        self.assertIn(installed["heavy"].status, {"limited", "not_recommended"})

    def test_offline_lmstudio_and_no_gpu_do_not_break_recommendations(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=14 * 1024**3,
            gpu=None,
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[model("lmstudio:local", "local", "lmstudio", 4.0, 2.5)],
            providers=[provider("lmstudio", False)],
        )

        installed = next(item for item in recommendations if item.source == "installed")
        self.assertIn("ram", installed.reason.lower())
        self.assertTrue(any(item.category == "GPU recommended" for item in recommendations))

    def test_gpu_without_vram_still_counts_as_detected_gpu(self) -> None:
        recommendations = build_llm_recommendations(
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=14 * 1024**3,
            gpu="AMD Radeon RX 7600",
            gpu_memory_total_bytes=None,
            gpu_memory_free_bytes=None,
            catalog=[],
            providers=[provider("lmstudio"), provider("ollama")],
        )

        general = next(item for item in recommendations if item.category == "Geral")
        self.assertIn("gpu detectada", general.reason.lower())
        self.assertNotIn("nao foi detectada vram", general.reason.lower())


if __name__ == "__main__":
    unittest.main()
