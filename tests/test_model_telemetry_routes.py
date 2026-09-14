from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from synapse.api.routes import router
from synapse.core.data_dir import DataDir
from synapse.model_providers.synapse_local import SynapseLocalModelAdapter


def test_frontend_telemetry_url_reaches_native_log(tmp_path: Path) -> None:
    adapter = SynapseLocalModelAdapter(DataDir(tmp_path))
    log = tmp_path / "logs/synapse-local-models/DeepSeek-Q4.log"
    log.parent.mkdir(parents=True)
    log.write_text("prompt eval time = 452.88 ms\neval time = 6003.87 ms\n", encoding="utf-8")
    app = FastAPI()
    app.state.runtime = SimpleNamespace(models=SimpleNamespace(adapters={"synapse_local": adapter}))
    app.include_router(router, prefix="/api")
    source = (Path(__file__).parents[1] / "apps/frontend-v2/src/shared/frontendClient.ts").read_text(encoding="utf-8")
    # Check the actual frontend URL against the registered backend route.
    url = source.split("return this.get<LMStudioStatus>(`", 1)[1].split("${search}", 1)[0]
    with TestClient(app) as client:
        response = client.get(url, params={"model": "DeepSeek-Q4"})
        assert response.status_code == 200, response.text
        assert [entry["raw_line"] for entry in response.json()["telemetry"]["recent"]] == [
            "prompt eval time = 452.88 ms", "eval time = 6003.87 ms"
        ]
        assert client.get("/api/models/providers/synapse-local/status").status_code == 404
