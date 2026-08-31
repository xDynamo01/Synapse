"""Factual supervision for a process already contained in a Windows Job."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, Protocol

from synapse.sandbox import OpaqueReference, SandboxArtifactFingerprint, SandboxWorkspaceId

from .windows_authority import (
    WindowsAuthorityContextV1,
    WindowsExecutionAuthorityGuard,
    WindowsExecutionGrantV1,
)
from .windows_command import ResolvedCommandV1
from .windows_process import ManagedWindowsProcess, WindowsExecutionAuthorizationPort
from .windows_workspace import SandboxFencingValidationPort


class WindowsSupervisionApi(Protocol):
    def process_state(self, process: int) -> tuple[bool, int | None]: ...
    def active_processes(self, job: int) -> tuple[int, tuple[int, ...]]: ...
    def terminate_job(self, job: int, exit_code: int) -> bool: ...


class WindowsRuntimeState(StrEnum):
    RUNNING = "running"
    EXITED = "exited"
    UNKNOWN = "unknown"
    ORPHANED = "orphaned"


@dataclass(frozen=True, slots=True)
class WindowsRuntimeObservationV1:
    attempt_reference: OpaqueReference
    process_reference: OpaqueReference
    state: WindowsRuntimeState
    root_active: bool | None
    root_exit_code: int | None
    active_process_count: int | None
    descendant_process_ids: tuple[int, ...]
    observation_available: bool
    elapsed_seconds: float
    timeout_observed: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsCancellationResult:
    accepted: bool
    already_requested: bool
    termination_requested: bool
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsTerminationProofV1:
    attempt_reference: OpaqueReference
    process_reference: OpaqueReference
    root_exit_code: int | None
    zero_active_processes: bool
    proof_fingerprint: SandboxArtifactFingerprint


@dataclass(frozen=True, slots=True)
class WindowsTerminationConfirmation:
    proven: bool
    proof: WindowsTerminationProofV1 | None
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsSupervisionHealth:
    runtime_observation: bool = True
    descendant_observation: bool = True
    timeout_observation: bool = True
    cancellation_control: bool = True
    job_termination_request: bool = True
    termination_confirmation: bool = True
    full_restart_recovery: bool = False
    network_isolation: bool = False


class WindowsProcessSupervisor:
    def __init__(
        self,
        resource: ManagedWindowsProcess | None,
        api: WindowsSupervisionApi,
        authorization: WindowsExecutionAuthorizationPort,
        fencing: SandboxFencingValidationPort,
        workspace_id: SandboxWorkspaceId,
        grant_reference: OpaqueReference,
        command: ResolvedCommandV1,
        authority_context: WindowsAuthorityContextV1 | None = None,
        *,
        started_monotonic: float | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._resource = resource
        self._api = api
        self._authorization = authorization
        self._fencing = fencing
        self._workspace = workspace_id
        self._grant = grant_reference
        self._command = command
        self._authority_context = authority_context
        self._clock = monotonic
        self._started = monotonic() if started_monotonic is None else started_monotonic
        self._cancellations: set[OpaqueReference] = set()
        self._termination_requested = False

    def health(self) -> WindowsSupervisionHealth:
        return WindowsSupervisionHealth()

    def observe(self, *, timeout_seconds: float | None = None) -> WindowsRuntimeObservationV1:
        elapsed = max(0.0, self._clock() - self._started)
        timeout = timeout_seconds is not None and elapsed >= timeout_seconds
        resource = self._resource
        if resource is None or resource._closed:
            return WindowsRuntimeObservationV1(
                OpaqueReference("attempt:unavailable"), OpaqueReference("process:unavailable"),
                WindowsRuntimeState.ORPHANED, None, None, None, (), False, elapsed, timeout,
                ("reconciliation_required",),
            )
        try:
            root_active, exit_code = self._api.process_state(resource.process_handle)
            active_count, process_ids = self._api.active_processes(resource.job_handle)
        except OSError:
            return WindowsRuntimeObservationV1(
                resource.driver_attempt_reference, resource.process_reference,
                WindowsRuntimeState.UNKNOWN, None, None, None, (), False, elapsed, timeout,
                ("observation_unavailable",),
            )
        descendants = tuple(sorted(pid for pid in process_ids if pid != resource.process_id))
        state = WindowsRuntimeState.RUNNING if root_active or active_count else WindowsRuntimeState.EXITED
        return WindowsRuntimeObservationV1(
            resource.driver_attempt_reference, resource.process_reference, state, root_active,
            exit_code, active_count, descendants, True, elapsed, timeout,
            ("timeout_observed",) if timeout else (),
        )

    def observe_descendants(self) -> WindowsRuntimeObservationV1:
        return self.observe()

    def request_cancellation(self, intent: OpaqueReference) -> WindowsCancellationResult:
        if intent in self._cancellations:
            return WindowsCancellationResult(True, True, self._termination_requested)
        self._cancellations.add(intent)
        return WindowsCancellationResult(True, False, False)

    def request_termination(self) -> WindowsCancellationResult:
        resource = self._resource
        if resource is None or resource._closed:
            return WindowsCancellationResult(False, False, False, ("orphaned",))
        class _GrantValidator:
            def __init__(self, authorization, command) -> None:
                self.authorization = authorization
                self.command = command

            def validate(self, grant: WindowsExecutionGrantV1) -> bool:
                return self.authorization.validate(self.command, grant.grant_reference)

        check = WindowsExecutionAuthorityGuard(
            _GrantValidator(self._authorization, self._command), self._fencing
        ).authorize(self._authority_context, self._workspace, "process_termination")
        if not check.allowed:
            return WindowsCancellationResult(
                False, False, False, (check.decision.value,)
            )
        observation = self.observe()
        if observation.observation_available and observation.active_process_count == 0:
            return WindowsCancellationResult(True, False, False, ("natural_exit_observed",))
        try:
            requested = self._api.terminate_job(resource.job_handle, 1)
        except OSError:
            requested = False
        if not requested:
            return WindowsCancellationResult(False, False, False, ("termination_request_failed",))
        self._termination_requested = True
        return WindowsCancellationResult(True, False, True)

    def confirm_termination(self) -> WindowsTerminationConfirmation:
        observation = self.observe()
        if (
            not observation.observation_available
            or observation.root_active is not False
            or observation.active_process_count != 0
        ):
            return WindowsTerminationConfirmation(False, None, ("termination_unverified",))
        semantic = (
            observation.attempt_reference, observation.process_reference,
            observation.root_exit_code, observation.active_process_count,
        )
        proof = WindowsTerminationProofV1(
            observation.attempt_reference, observation.process_reference,
            observation.root_exit_code, True,
            SandboxArtifactFingerprint.from_content(semantic),
        )
        return WindowsTerminationConfirmation(True, proof, ())
