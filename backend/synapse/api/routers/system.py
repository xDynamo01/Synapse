from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request, Response

from synapse.api.common import runtime_from

router = APIRouter()


@router.get("/health")
def health(request: Request, response: Response) -> dict[str, Any]:
    response.headers["X-Synapse-Service"] = "synapse-backend"
    runtime = runtime_from(request)
    return asdict(runtime.health.summary())


@router.get("/sidecar/startup-ready")
def sidecar_startup_ready(request: Request, response: Response) -> dict[str, Any]:
    response.headers["X-Synapse-Service"] = "synapse-backend"
    startup_report = getattr(request.app.state, "startup_report", None)
    if startup_report is None:
        response.status_code = 503
        return {
            "schema": "synapse-sidecar-startup-ready-v1",
            "ready": False,
            "startup_status": "missing-startup-report",
            "resources": [],
        }
    ready = startup_report.status in {"ready", "degraded"}
    if not ready:
        response.status_code = 503
    application = getattr(request.app.state, "application", None)
    required_by_resource = {
        resource.name: resource.required
        for resource in getattr(getattr(application, "lifecycle", None), "resources", ())
    }
    return {
        "schema": "synapse-sidecar-startup-ready-v1",
        "ready": ready,
        "startup_status": startup_report.status,
        "resources": [
            {
                **asdict(item),
                "required": required_by_resource.get(item.resource, True),
            }
            for item in startup_report.results
        ],
    }


@router.get("/system/insight")
def system_insight(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.inspect())


@router.get("/system")
def system_information(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.system.inspect())


@router.get("/hardware")
def hardware_information(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.hardware.inspect())


@router.get("/gpu")
def gpu_information(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).system_insight.hardware.inspect().gpus]


@router.get("/cpu")
def cpu_information(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.hardware.inspect().cpu)


@router.get("/system/memory")
def memory_information(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.hardware.inspect().memory)


@router.get("/storage")
def storage_information(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.disk.inspect())


@router.get("/processes")
def process_information(request: Request, limit: int = 100) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.processes.inspect(limit=limit))


@router.get("/insight/providers")
def insight_providers(request: Request) -> list[dict[str, Any]]:
    return runtime_from(request).system_insight.provider_statuses()


@router.get("/models/recommendations")
def model_recommendations(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.model_capabilities.inspect())


@router.get("/insight/diagnostics")
def insight_diagnostics(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.report(persist=False).diagnostics)


@router.get("/insight/report")
def insight_report(request: Request) -> dict[str, Any]:
    return asdict(runtime_from(request).system_insight.report())


@router.get("/readiness")
def readiness(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return asdict(runtime.readiness.evaluate())


@router.get("/readiness/issues")
def readiness_issues(request: Request) -> list[dict[str, Any]]:
    runtime = runtime_from(request)
    return [asdict(issue) for issue in runtime.readiness.blocking_issues()]


@router.get("/readiness/actions")
def readiness_actions(request: Request) -> list[str]:
    runtime = runtime_from(request)
    return runtime.readiness.recommended_actions()


@router.get("/health/components")
def health_components(request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).health.component_health()]


@router.get("/health/modules/{module}")
def health_module(module: str, request: Request) -> list[dict[str, Any]]:
    return [asdict(item) for item in runtime_from(request).health.module_health(module)]


@router.get("/diagnostics")
def diagnostics(request: Request) -> dict[str, Any]:
    return runtime_from(request).health.diagnostics()


@router.get("/health/dependencies")
def health_dependencies(request: Request) -> dict[str, list[str]]:
    return runtime_from(request).health.dependency_graph()


@router.get("/agent-multimodal-policy")
def agent_multimodal_policy(request: Request) -> dict[str, Any]:
    runtime = runtime_from(request)
    return runtime.worker.multimodal_context_policy()
