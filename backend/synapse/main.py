from __future__ import annotations

from fastapi import FastAPI

from synapse.api import router
from synapse.core.app import create_runtime


def create_app() -> FastAPI:
    app = FastAPI(
        title="Synapse V2 Runtime API",
        version="0.1.0",
        description="Local-first personal agent OS runtime API.",
    )
    app.state.runtime = create_runtime()
    app.include_router(router, prefix="/api")
    return app


app = create_app()

