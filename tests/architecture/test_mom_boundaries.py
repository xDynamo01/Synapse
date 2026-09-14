from .support import SOURCE_ROOT, cyclic_components, import_edges, imports_for
from .test_audio_speech_boundary import _runtime_context_graph


def test_mom_domain_depends_only_on_its_contracts_and_core_services():
    for path in (SOURCE_ROOT / "mom").glob("*.py"):
        for module in imports_for(path):
            if module.startswith("synapse."):
                assert module.split(".")[1] in {"mom", "core"}, (path, module)


def test_mom_has_no_swarm_worker_or_agent_execution_backdoor():
    incoming = {edge.source_context for edge in import_edges() if edge.target_context == "mom"}
    assert incoming <= {"bootstrap", "api"}
    for context in ("swarm", "workers", "ephemeral_agents", "agents"):
        for path in (SOURCE_ROOT / context).glob("*.py"):
            assert not any(module.startswith("synapse.mom") for module in imports_for(path))


def test_mom_graph_delta_is_exact_and_does_not_change_cycles():
    graph = _runtime_context_graph()
    delta = {edge for edge in graph if "mom" in edge}
    assert delta == {("api", "mom"), ("mom", "core")}
    assert cyclic_components(graph) == cyclic_components(graph - delta)
