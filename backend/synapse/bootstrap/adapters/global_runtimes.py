"""Construction helpers for globally governed bounded-context runtimes."""

from pathlib import Path

from synapse.bootstrap.adapters.coding_sessions import DeferredCodingSessionsRuntime
from synapse.bootstrap.adapters.deployment import build_deployment_health_contributor
from synapse.bootstrap.adapters.private_evals import (
    DeferredPrivateEvalsRuntime,
    build_deferred_private_evals,
)
from synapse.bootstrap.adapters.repository_runtime import DeferredRepositoryRuntime
from synapse.bootstrap.adapters.sandbox import DeferredSandboxRuntime
from synapse.bootstrap.adapters.skills_phase2 import DeferredSkillsPhase2Runtime
from synapse.bootstrap.lifecycle import LifecycleManager, LifecycleResource
from synapse.core.data_dir import DataDir
from synapse.deployment_composition import (
    DeploymentRuntime,
    DeploymentRuntimeConfig,
    build_deployment_runtime,
)
from synapse.health.registry import HealthContributorRegistry


def build_all(
    data_dir: DataDir, project_root: Path,
) -> tuple[DeploymentRuntime, DeferredPrivateEvalsRuntime, DeferredCodingSessionsRuntime, DeferredSkillsPhase2Runtime, DeferredSandboxRuntime, DeferredRepositoryRuntime]:
    deployment = build_deployment_runtime(
        DeploymentRuntimeConfig(data_dir.resolve("deployment-runtime.sqlite3"))
    )
    private_evals = build_deferred_private_evals(
        data_dir.resolve("private-evals-runtime.sqlite3")
    )
    coding_sessions = DeferredCodingSessionsRuntime(data_dir.resolve("coding-sessions-runtime.sqlite3"))
    skills_phase2 = DeferredSkillsPhase2Runtime(data_dir.resolve("skills-phase2-runtime.sqlite3"))
    sandbox = DeferredSandboxRuntime(data_dir.resolve("sandbox-runtime.sqlite3"))
    repository = DeferredRepositoryRuntime(project_root, data_dir.root)
    return deployment, private_evals, coding_sessions, skills_phase2, sandbox, repository


def bind_health(
    registry: HealthContributorRegistry,
    deployment: DeploymentRuntime,
    private_evals: DeferredPrivateEvalsRuntime,
    coding_sessions: DeferredCodingSessionsRuntime,
    skills_phase2: DeferredSkillsPhase2Runtime,
    sandbox: DeferredSandboxRuntime,
    repository: DeferredRepositoryRuntime,
) -> None:
    registry.register(build_deployment_health_contributor(deployment))
    registry.register(private_evals.health_contributor())
    registry.register(coding_sessions.health_contributor())
    registry.register(skills_phase2.health_contributor())
    registry.register(sandbox.health_contributor())
    registry.register(repository.health_contributor())


def bind_lifecycle(
    lifecycle: LifecycleManager,
    deployment: DeploymentRuntime,
    private_evals: DeferredPrivateEvalsRuntime,
    coding_sessions: DeferredCodingSessionsRuntime,
    skills_phase2: DeferredSkillsPhase2Runtime,
    sandbox: DeferredSandboxRuntime,
    repository: DeferredRepositoryRuntime,
) -> None:
    lifecycle.register(
        LifecycleResource(
            name="deployment-runtime",
            feature="global-composition-root",
            reason="Initialize Deployment append-only persistence and fencing authority.",
            start=deployment.start,
            close=deployment.close,
            required=True,
            metadata={"failure_behavior": "rollback startup and fail the lifespan"},
        )
    )
    lifecycle.register(private_evals.lifecycle_resource())
    lifecycle.register(coding_sessions.lifecycle_resource())
    lifecycle.register(skills_phase2.lifecycle_resource())
    lifecycle.register(sandbox.lifecycle_resource())
    lifecycle.register(repository.lifecycle_resource())
