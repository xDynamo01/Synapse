from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest

from synapse.core.data_dir import DataDir
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter, _ManagedServer
from synapse.models.errors import ModelError
from synapse.models.types import ModelRequest, ModelResponse


class Process:
    def __init__(self):
        self.alive = True

    def poll(self):
        return None if self.alive else 0

    def terminate(self):
        self.alive = False

    def kill(self):
        self.alive = False

    def wait(self, timeout):
        assert not self.alive
        return 0


def pool(tmp_path, monkeypatch, limit=1):
    adapter = SynapseLocalModelAdapter(DataDir(tmp_path), max_loaded_models=limit)
    created = []
    monkeypatch.setattr(adapter, "_resolve_model_path", lambda model: tmp_path / (Path(model).stem + ".gguf"))

    def ensure(model, timeout):
        if model not in adapter._servers:
            server = _ManagedServer(model, tmp_path / f"{model}.gguf",
                                    f"http://127.0.0.1:{9000 + len(created)}", Process())
            created.append(server)
            adapter._servers[model] = server
        return adapter._servers[model]

    monkeypatch.setattr(adapter, "_ensure_server", ensure)
    return adapter, created


def test_two_models_generate_concurrently_without_crossing_requests(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    barrier = Barrier(2, timeout=5)

    def generate(request):
        barrier.wait()
        assert request.context == {"identity": request.agent_id}
        assert Path(request.metadata["synapse_local_model_path"]).stem == request.model
        return ModelResponse(content=request.user_message, provider=request.provider, model=request.model)

    monkeypatch.setattr(adapter._openai, "generate", generate)
    requests = [ModelRequest(agent_id=f"agent-{model}", provider="synapse_local", model=model,
                             user_message=f"message-{model}", context={"identity": f"agent-{model}"})
                for model in ("deepseek", "qwen")]
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(adapter.generate, requests))
        assert [result.model for result in results] == ["deepseek", "qwen"]
        assert [result.content for result in results] == ["message-deepseek", "message-qwen"]
        assert len(created) == 2
        assert all(server.process.alive and not server.active for server in created)
    finally:
        adapter.shutdown()


def test_busy_model_is_not_evicted_and_wait_has_deadline(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch)
    try:
        with adapter._lease("deepseek", 1) as first:
            with ThreadPoolExecutor(max_workers=1) as executor:
                def wait():
                    with adapter._lease("qwen", 0.03):
                        pytest.fail("Busy model was evicted")
                future = executor.submit(wait)
                with pytest.raises(ModelError, match="capacity"):
                    future.result(timeout=2)
            assert first.process.alive
            assert len(created) == 1
        with adapter._lease("qwen", 1):
            assert not first.process.alive
            assert len(adapter._servers) == 1
    finally:
        adapter.shutdown()


def test_aliases_reuse_process_and_failure_releases_lease(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    try:
        with pytest.raises(RuntimeError):
            with adapter._lease("deepseek.gguf", 1):
                raise RuntimeError("generation failed")
        with adapter._lease("deepseek", 1):
            assert len(created) == 1
        adapter.shutdown()
        with pytest.raises(ModelError, match="shut down"):
            with adapter._lease("qwen", 1):
                pytest.fail("Shutdown runtime was reopened")
    finally:
        adapter.shutdown()


def test_same_model_waits_then_reuses_resident_process(tmp_path, monkeypatch):
    adapter, created = pool(tmp_path, monkeypatch, 2)
    entered = Event()
    release = Event()
    attempted = Event()
    resolve = adapter._resolve_model_path

    def resolve_alias(model):
        if model.endswith(".gguf"):
            attempted.set()
        return resolve(model)

    monkeypatch.setattr(adapter, "_resolve_model_path", resolve_alias)

    def first():
        with adapter._lease("deepseek", 3):
            entered.set()
            assert release.wait(2)

    def second():
        with adapter._lease("deepseek.gguf", 3):
            assert release.is_set()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            a = executor.submit(first)
            assert entered.wait(2)
            b = executor.submit(second)
            try:
                assert attempted.wait(2)
                assert not b.done()
            finally:
                release.set()
            a.result(timeout=3)
            b.result(timeout=3)
        assert len(created) == 1
    finally:
        adapter.shutdown()


def test_waiting_for_startup_lock_is_bounded(tmp_path, monkeypatch):
    adapter, _ = pool(tmp_path, monkeypatch)
    held = Event()
    release = Event()

    def loading():
        with adapter._condition:
            held.set()
            assert release.wait(2)

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(loading)
            assert held.wait(2)
            try:
                with pytest.raises(ModelError, match="loading"):
                    with adapter._lease("deepseek", 0.03):
                        pytest.fail("Startup lock deadline ignored")
            finally:
                release.set()
            future.result(timeout=3)
    finally:
        adapter.shutdown()


def test_failed_model_loading_stops_owned_process(tmp_path, monkeypatch):
    adapter = SynapseLocalModelAdapter(DataDir(tmp_path))
    process = Process()
    monkeypatch.setattr(adapter, "_resolve_model_path", lambda model: tmp_path / "deepseek.gguf")
    monkeypatch.setattr(adapter, "_resolve_llama_server", lambda: tmp_path / "llama-server.exe")
    monkeypatch.setattr("synapse.model_providers.synapse_local.subprocess.Popen", lambda *args, **kwargs: process)
    def fail(*args):
        raise ModelError("generation_timeout", "load failed")
    monkeypatch.setattr(adapter, "_wait_until_ready", fail)
    with pytest.raises(ModelError, match="load failed"):
        with adapter._lease("deepseek", 1):
            pytest.fail("Failed startup admitted")
    assert not process.alive
    assert not adapter._servers
    adapter.shutdown()


@pytest.mark.parametrize("limit", [0, 3, True, -1])
def test_invalid_capacity_rejected(tmp_path, limit):
    with pytest.raises(ModelError, match="limit"):
        SynapseLocalModelAdapter(DataDir(tmp_path), max_loaded_models=limit)
