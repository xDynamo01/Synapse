from __future__ import annotations

from dataclasses import replace
from typing import Any

from synapse.model_hub.models import LLMRecommendation, ModelCatalogEntry, ModelProviderInfo

_CATEGORY_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "Geral": [
        {
            "model_name": "Qwen 2.5 7B Instruct Q4_K_M",
            "estimated_ram_gb": 7.5,
            "estimated_vram_gb": 4.5,
            "runtime": "LM Studio",
        },
        {
            "model_name": "Phi-3.5 Mini Instruct",
            "estimated_ram_gb": 3.5,
            "estimated_vram_gb": 2.0,
            "runtime": "llama.cpp",
        },
    ],
    "Programação": [
        {
            "model_name": "Qwen 2.5 Coder 7B Instruct Q4_K_M",
            "estimated_ram_gb": 8.0,
            "estimated_vram_gb": 4.8,
            "runtime": "LM Studio",
        },
        {
            "model_name": "DeepSeek Coder 3B Instruct Q4",
            "estimated_ram_gb": 4.0,
            "estimated_vram_gb": 2.5,
            "runtime": "Ollama",
        },
    ],
    "Rápido": [
        {
            "model_name": "Phi-3.5 Mini Instruct",
            "estimated_ram_gb": 3.5,
            "estimated_vram_gb": 2.0,
            "runtime": "llama.cpp",
        },
        {
            "model_name": "Llama 3.2 3B Instruct",
            "estimated_ram_gb": 3.0,
            "estimated_vram_gb": 2.0,
            "runtime": "LM Studio",
        },
    ],
    "Qualidade": [
        {
            "model_name": "Qwen 2.5 14B Instruct Q4_K_M",
            "estimated_ram_gb": 16.0,
            "estimated_vram_gb": 10.0,
            "runtime": "LM Studio",
        },
        {
            "model_name": "Llama 3.1 8B Instruct Q4_K_M",
            "estimated_ram_gb": 8.5,
            "estimated_vram_gb": 5.5,
            "runtime": "LM Studio",
        },
    ],
    "Baixa memória": [
        {
            "model_name": "Llama 3.2 1B Instruct",
            "estimated_ram_gb": 1.5,
            "estimated_vram_gb": 1.0,
            "runtime": "llama.cpp",
        },
        {
            "model_name": "Phi-3.5 Mini Instruct",
            "estimated_ram_gb": 3.5,
            "estimated_vram_gb": 2.0,
            "runtime": "llama.cpp",
        },
    ],
    "CPU only": [
        {
            "model_name": "TinyLlama 1.1B Chat",
            "estimated_ram_gb": 1.0,
            "estimated_vram_gb": 0.0,
            "runtime": "llama.cpp",
        },
        {
            "model_name": "Phi-3.5 Mini Instruct",
            "estimated_ram_gb": 3.5,
            "estimated_vram_gb": 0.0,
            "runtime": "llama.cpp",
        },
    ],
    "GPU recommended": [
        {
            "model_name": "Qwen 2.5 14B Instruct Q4_K_M",
            "estimated_ram_gb": 16.0,
            "estimated_vram_gb": 10.0,
            "runtime": "LM Studio",
        },
        {
            "model_name": "Qwen 2.5 Coder 7B Instruct Q4_K_M",
            "estimated_ram_gb": 8.0,
            "estimated_vram_gb": 4.8,
            "runtime": "Ollama",
        },
    ],
}


def build_llm_recommendations(
    *,
    memory_total_bytes: int | None,
    memory_available_bytes: int | None,
    gpu: str | None,
    gpu_memory_total_bytes: int | None,
    gpu_memory_free_bytes: int | None,
    catalog: list[ModelCatalogEntry],
    providers: list[ModelProviderInfo],
) -> list[LLMRecommendation]:
    active_runtime = _preferred_runtime(providers, catalog)
    budget_gb = _memory_budget_gb(memory_total_bytes, memory_available_bytes)
    gpu_budget_gb = _gpu_budget_gb(gpu_memory_total_bytes, gpu_memory_free_bytes)

    recommendations: list[LLMRecommendation] = []
    for category, templates in _CATEGORY_TEMPLATES.items():
        best_catalog_entry = _best_catalog_entry(category, catalog, budget_gb, gpu_budget_gb, gpu)
        if best_catalog_entry is not None:
            recommendations.append(
                _installed_recommendation(
                    category, best_catalog_entry, budget_gb, gpu_budget_gb, gpu
                )
            )
            continue
        template = _best_template(
            category, templates, budget_gb, gpu_budget_gb, gpu, active_runtime
        )
        recommendations.append(template)

    recommendations.extend(
        _assess_installed_models(
            catalog,
            providers,
            budget_gb,
            gpu_budget_gb,
            gpu,
            active_runtime,
        )
    )
    return _annotate_highlights(recommendations)


def _assess_installed_models(
    catalog: list[ModelCatalogEntry],
    providers: list[ModelProviderInfo],
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
    preferred_runtime: str,
) -> list[LLMRecommendation]:
    if not catalog:
        return []
    provider_state = {provider.provider_id: provider.active for provider in providers}
    assessments: list[LLMRecommendation] = []
    for entry in catalog:
        status, reason, category = _classify_entry(
            entry, budget_gb, gpu_budget_gb, gpu, provider_state
        )
        assessments.append(
            LLMRecommendation(
                category=category,
                model_name=entry.name,
                status=status,
                reason=reason,
                runtime_suggested=_runtime_for_provider(entry.provider, preferred_runtime),
                estimated_ram_gb=entry.estimated_ram_gb,
                estimated_vram_gb=entry.estimated_vram_gb,
                model_id=entry.id,
                provider=entry.provider,
                source="installed",
            )
        )
    return assessments


def _installed_recommendation(
    category: str,
    entry: ModelCatalogEntry,
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
) -> LLMRecommendation:
    provider_state = {entry.provider: True}
    status, reason, _ = _classify_entry(entry, budget_gb, gpu_budget_gb, gpu, provider_state)
    return LLMRecommendation(
        category=category,
        model_name=entry.name,
        status=status,
        reason=reason,
        runtime_suggested=_runtime_for_provider(entry.provider, entry.runtime),
        estimated_ram_gb=entry.estimated_ram_gb,
        estimated_vram_gb=entry.estimated_vram_gb,
        model_id=entry.id,
        provider=entry.provider,
        source="installed",
    )


def _best_template(
    category: str,
    templates: list[dict[str, Any]],
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
    preferred_runtime: str,
) -> LLMRecommendation:
    selected = templates[0]
    for candidate in templates:
        if _fits_budget(
            candidate["estimated_ram_gb"],
            candidate["estimated_vram_gb"],
            budget_gb,
            gpu_budget_gb,
            gpu,
        ):
            selected = candidate
            break
    status = (
        "recommended"
        if _fits_budget(
            selected["estimated_ram_gb"],
            selected["estimated_vram_gb"],
            budget_gb,
            gpu_budget_gb,
            gpu,
        )
        else "limited"
    )
    reason = _template_reason(selected["estimated_ram_gb"], budget_gb, gpu_budget_gb, gpu)
    return LLMRecommendation(
        category=category,
        model_name=selected["model_name"],
        status=status,
        reason=reason,
        runtime_suggested=selected.get("runtime") or preferred_runtime,
        estimated_ram_gb=selected["estimated_ram_gb"],
        estimated_vram_gb=selected["estimated_vram_gb"],
        source="suggested",
    )


def _best_catalog_entry(
    category: str,
    catalog: list[ModelCatalogEntry],
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
) -> ModelCatalogEntry | None:
    candidates = [entry for entry in catalog if _category_score(entry, category) > 0]
    if not candidates:
        candidates = list(catalog)
    best_entry: ModelCatalogEntry | None = None
    best_score = -1.0
    for entry in candidates:
        score = _category_score(entry, category)
        score += _fit_score(entry, budget_gb, gpu_budget_gb, gpu)
        if score > best_score:
            best_score = score
            best_entry = entry
    return best_entry


def _category_score(entry: ModelCatalogEntry, category: str) -> float:
    name = f"{entry.name} {entry.provider} {entry.runtime}".lower()
    score = 0.0
    if category == "Programação":
        if any(token in name for token in ("coder", "code", "deepseek", "program")):
            score += 3.0
    elif category == "Rápido":
        if any(token in name for token in ("mini", "small", "fast", "phi", "3b", "1b")):
            score += 3.0
    elif category == "Qualidade":
        if any(token in name for token in ("14b", "13b", "8b", "large", "instruct")):
            score += 2.5
    elif category == "Baixa memória":
        if any(token in name for token in ("1b", "3b", "mini", "tiny")):
            score += 3.0
    elif category == "CPU only":
        if entry.cpu_compatible:
            score += 2.5
    elif category == "GPU recommended":
        if entry.gpu_compatible:
            score += 2.5
    else:
        score += 1.0
    return score


def _fit_score(
    entry: ModelCatalogEntry,
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
) -> float:
    score = 0.0
    estimated_ram = entry.estimated_ram_gb or 0.0
    estimated_vram = entry.estimated_vram_gb or 0.0
    if _fits_budget(estimated_ram, estimated_vram, budget_gb, gpu_budget_gb, gpu):
        score += 2.0
    elif estimated_ram <= budget_gb * 1.25:
        score += 1.0
    if estimated_ram <= budget_gb * 0.55:
        score += 0.5
    if entry.cpu_compatible:
        score += 0.25
    return score


def _classify_entry(
    entry: ModelCatalogEntry,
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
    provider_state: dict[str, bool],
) -> tuple[str, str, str]:
    estimated_ram = entry.estimated_ram_gb or 0.0
    estimated_vram = entry.estimated_vram_gb or 0.0
    provider_active = provider_state.get(entry.provider, True)
    if not provider_active:
        if _fits_budget(estimated_ram, estimated_vram, budget_gb, gpu_budget_gb, gpu):
            return (
                "limited",
                f"O runtime {entry.provider} nao esta ativo; o modelo parece caber nesta maquina, mas depende do servidor ficar disponivel.",
                _category_from_entry(entry),
            )
        return (
            "not_recommended",
            f"O runtime {entry.provider} nao esta ativo e o modelo ainda excede a estimativa desta maquina.",
            _category_from_entry(entry),
        )
    if _fits_budget(estimated_ram, estimated_vram, budget_gb, gpu_budget_gb, gpu):
        return (
            "recommended",
            _template_reason(estimated_ram, budget_gb, gpu_budget_gb, gpu),
            _category_from_entry(entry),
        )
    if estimated_ram <= budget_gb * 1.25:
        return (
            "limited",
            _template_reason(estimated_ram, budget_gb, gpu_budget_gb, gpu),
            _category_from_entry(entry),
        )
    return (
        "not_recommended",
        _template_reason(estimated_ram, budget_gb, gpu_budget_gb, gpu),
        _category_from_entry(entry),
    )


def _category_from_entry(entry: ModelCatalogEntry) -> str:
    score_categories = [
        "Programação",
        "Rápido",
        "Qualidade",
        "Baixa memória",
        "CPU only",
        "GPU recommended",
    ]
    best = "Geral"
    best_score = -1.0
    for category in score_categories:
        score = _category_score(entry, category)
        if score > best_score:
            best_score = score
            best = category
    return best


def _annotate_highlights(recommendations: list[LLMRecommendation]) -> list[LLMRecommendation]:
    installed = [item for item in recommendations if item.source == "installed"]
    if not installed:
        return recommendations

    ranked = sorted(
        installed,
        key=lambda item: (
            0 if item.status == "recommended" else 1 if item.status == "limited" else 2,
            item.estimated_ram_gb or 999.0,
            item.model_name.lower(),
        ),
    )
    if ranked:
        recommendations = [
            replace(item, highlight="best_choice") if item.model_id == ranked[0].model_id else item
            for item in recommendations
        ]
    fastest = min(
        installed,
        key=lambda item: ((item.estimated_ram_gb or 999.0), item.model_name.lower()),
    )
    recommendations = [
        replace(item, highlight=(item.highlight or "fastest"))
        if item.model_id == fastest.model_id
        else item
        for item in recommendations
    ]
    code_candidates = [item for item in installed if item.category == "Programação"]
    if code_candidates:
        code_best = min(
            code_candidates,
            key=lambda item: ((item.estimated_ram_gb or 999.0), item.model_name.lower()),
        )
        recommendations = [
            replace(item, highlight=(item.highlight or "best_for_code"))
            if item.model_id == code_best.model_id
            else item
            for item in recommendations
        ]
    weak_candidates = [
        item
        for item in installed
        if item.status != "not_recommended" and item.source == "installed"
    ]
    if weak_candidates:
        weak_best = min(
            weak_candidates,
            key=lambda item: ((item.estimated_ram_gb or 999.0), item.model_name.lower()),
        )
        recommendations = [
            replace(item, highlight=(item.highlight or "best_for_weak_machine"))
            if item.model_id == weak_best.model_id
            else item
            for item in recommendations
        ]
    return recommendations


def _memory_budget_gb(memory_total_bytes: int | None, memory_available_bytes: int | None) -> float:
    total = _bytes_to_gb(memory_available_bytes or memory_total_bytes)
    if total <= 0:
        return 8.0
    if total < 8.0:
        return max(3.0, total * 0.8)
    if total < 16.0:
        return 7.5
    if total < 32.0:
        return 16.0
    if total < 48.0:
        return 24.0
    return min(total * 0.75, 32.0)


def _gpu_budget_gb(gpu_total_bytes: int | None, gpu_free_bytes: int | None) -> float | None:
    if gpu_free_bytes:
        return max(_bytes_to_gb(gpu_free_bytes), 0.0)
    if gpu_total_bytes:
        return max(_bytes_to_gb(gpu_total_bytes), 0.0)
    return None


def _fits_budget(
    estimated_ram_gb: float,
    estimated_vram_gb: float,
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
) -> bool:
    if estimated_ram_gb > budget_gb * 1.25:
        return False
    if gpu_budget_gb is None:
        return True
    return estimated_vram_gb <= gpu_budget_gb * 0.9 or estimated_vram_gb <= 0


def _template_reason(
    estimated_ram_gb: float,
    budget_gb: float,
    gpu_budget_gb: float | None,
    gpu: str | None,
) -> str:
    memory_message = (
        f"Estimativa de RAM de {estimated_ram_gb:.1f} GB frente a {budget_gb:.1f} GB disponiveis."
    )
    if gpu_budget_gb is None:
        if gpu:
            return f"{memory_message} GPU detectada ({gpu}), mas VRAM nao foi informada."
        return f"{memory_message} Nao foi detectada VRAM util para ajuste."
    if gpu:
        return f"{memory_message} VRAM detectada em torno de {gpu_budget_gb:.1f} GB."
    return f"{memory_message} Sem GPU detectada; priorize modelos CPU-friendly."


def _runtime_for_provider(provider: str | None, fallback: str) -> str:
    if provider == "lmstudio":
        return "LM Studio"
    if provider == "ollama":
        return "Ollama"
    if provider in {"local_folder", "llama.cpp"}:
        return "llama.cpp"
    if provider in {"openai", "anthropic", "gemini", "groq", "openrouter", "openai_compatible"}:
        return "API externa"
    return fallback


def _preferred_runtime(providers: list[ModelProviderInfo], catalog: list[ModelCatalogEntry]) -> str:
    active_provider_ids = {provider.provider_id for provider in providers if provider.active}
    if "lmstudio" in active_provider_ids:
        return "LM Studio"
    if "ollama" in active_provider_ids:
        return "Ollama"
    if any(entry.provider == "local_folder" for entry in catalog):
        return "llama.cpp"
    return "API externa"


def _bytes_to_gb(value: int | None) -> float:
    if not value:
        return 0.0
    return value / 1024 / 1024 / 1024
