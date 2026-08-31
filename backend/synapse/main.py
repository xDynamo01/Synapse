from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from synapse.api import router
from synapse.bootstrap.application import build_application
from synapse.core.config import Settings

PRODUCT_VERSION = "0.1.0-rc.2"


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        existing_runtime = getattr(app.state, "runtime", None)
        if existing_runtime is not None:
            yield
            return

        application = build_application(settings)
        app.state.application = application
        app.state.runtime = application.container
        app.state.startup_report = application.start()
        try:
            yield
        finally:
            app.state.shutdown_report = application.close()

    app = FastAPI(
        title="Synapse V2 Runtime API",
        version=PRODUCT_VERSION,
        description="Local-first personal agent OS runtime API.",
        lifespan=lifespan,
    )
    app.include_router(router, prefix="/api")
    return app


app = create_app()
