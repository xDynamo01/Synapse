import pytest

from synapse.swarm.request_policy import classify_swarm_request


def test_normal_chat_does_not_request_swarm():
    decision = classify_swarm_request("Analise este arquivo")
    assert not decision.requested
    assert not decision.requires_confirmation


def test_question_about_swarm_is_not_an_execution_request():
    decision = classify_swarm_request("O que é um Swarm e quando devo usar?")
    assert not decision.requested


def test_explicit_swarm_command_authorizes_automatic_workforce():
    decision = classify_swarm_request("Use um Swarm para analisar o projeto")
    assert decision.requested
    assert decision.requested_agents is None
    assert not decision.requires_confirmation


def test_explicit_count_is_preserved_without_forcing_the_count():
    decision = classify_swarm_request("Crie 5 agentes para o Swarm")
    assert decision.requested
    assert decision.requested_agents == 5
    assert not decision.requires_confirmation


def test_explicit_models_are_captured():
    decision = classify_swarm_request("Use um Swarm com modelos Qwen e DeepSeek")
    assert decision.requested
    assert decision.explicit_models == ("Qwen", "DeepSeek")


@pytest.mark.parametrize("description", [
    "mais recomendados para cada ação", "melhores para cada tarefa", "locais disponíveis",
    "leves e adequados", "que você recomendar", "instalados", "menos pesados",
])
def test_model_selection_description_is_not_an_explicit_model(description):
    decision = classify_swarm_request(f"Faça um swarm com 4 agentes e utilize os modelos {description}")
    assert decision.requested_agents == 4
    assert decision.explicit_models == ()


def test_reported_four_agent_project_request_uses_automatic_model_selection():
    decision = classify_swarm_request(
        r"esse projeto E:\Projetos\conversor-app , tem varios erros, ele nao converte nada, "
        "faça um swarm com 4 agentes para consertar esse projeto, utilize os modelos "
        "mais recomendados para cada açao, use o modo economico para nao sobrecarregar o sistema"
    )
    assert decision.requested
    assert decision.requested_agents == 4
    assert decision.explicit_models == ()


def test_explicit_names_survive_recommendation_phrases_and_comma_spacing():
    decision = classify_swarm_request("Faça um swarm com modelos locais; use modelos Qwen, DeepSeek e Gemma")
    assert decision.explicit_models == ("Qwen", "DeepSeek", "Gemma")
    assert classify_swarm_request("Use um swarm com modelo unknown-custom-7b").explicit_models == ("unknown-custom-7b",)
