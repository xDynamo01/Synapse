from __future__ import annotations

from dataclasses import dataclass

from tests.factories.windows_authority import process_context
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _resolved

from synapse.sandbox import OpaqueReference
from synapse.sandbox_drivers import (
    ManagedWindowsProcess,
    SandboxFencingDecision,
    WindowsProcessSupervisor,
    WindowsRuntimeState,
)


@dataclass
class SupervisionApi:
    root_active: bool = True
    exit_code: int | None = None
    process_ids: tuple[int, ...] = (1234,)
    fail_observe: bool = False
    terminate_ok: bool = True
    terminate_calls: int = 0

    def process_state(self, process):
        if self.fail_observe:
            raise OSError("injected")
        return self.root_active, self.exit_code

    def active_processes(self, job):
        if self.fail_observe:
            raise OSError("injected")
        return len(self.process_ids), self.process_ids

    def terminate_job(self, job, exit_code):
        self.terminate_calls += 1
        return self.terminate_ok


def _supervisor(tmp_path, api=None, fencing=None, authorization=None, clock=None):
    workspace, _, command = _resolved(tmp_path)
    resource = ManagedWindowsProcess(
        20, 10, 1234, OpaqueReference("process:attempt"),
        OpaqueReference("driver-attempt:one"), FakeApi()
    )
    return WindowsProcessSupervisor(
        resource, api or SupervisionApi(), authorization or Authorization(),
        fencing or Fencing(), workspace, OpaqueReference("grant:one"), command,
        process_context(command, workspace, OpaqueReference("grant:one")),
        started_monotonic=0.0, monotonic=clock or (lambda: 1.0),
    )


def test_running_exited_and_descendant_facts_are_distinct(tmp_path) -> None:
    api = SupervisionApi()
    supervisor = _supervisor(tmp_path, api)
    running = supervisor.observe()
    assert running.state is WindowsRuntimeState.RUNNING and running.root_active
    api.root_active = False
    api.exit_code = 0
    api.process_ids = (2222,)
    child = supervisor.observe_descendants()
    assert child.state is WindowsRuntimeState.RUNNING
    assert child.root_exit_code == 0 and child.descendant_process_ids == (2222,)
    assert not supervisor.confirm_termination().proven
    api.process_ids = ()
    exited = supervisor.observe()
    assert exited.state is WindowsRuntimeState.EXITED
    assert supervisor.confirm_termination().proven


def test_timeout_uses_monotonic_and_never_implies_termination(tmp_path) -> None:
    supervisor = _supervisor(tmp_path, clock=lambda: 11.0)
    observation = supervisor.observe(timeout_seconds=10.0)
    assert observation.timeout_observed
    assert observation.state is WindowsRuntimeState.RUNNING
    assert not supervisor.confirm_termination().proven


def test_cancellation_is_idempotent_and_not_termination(tmp_path) -> None:
    supervisor = _supervisor(tmp_path)
    intent = OpaqueReference("cancellation:one")
    first = supervisor.request_cancellation(intent)
    second = supervisor.request_cancellation(intent)
    assert first.accepted and not first.termination_requested
    assert second.already_requested and not second.termination_requested


def test_stale_or_unauthorized_writer_cannot_terminate(tmp_path) -> None:
    for index, (authorization, fencing, code) in enumerate((
        (Authorization(False), Fencing(), "grant_invalid"),
        (Authorization(), Fencing([SandboxFencingDecision.STALE]), "fencing_stale"),
    )):
        api = SupervisionApi()
        result = _supervisor(
            tmp_path / str(index), api, fencing, authorization
        ).request_termination()
        assert result.diagnostics == (code,)
        assert api.terminate_calls == 0


def test_termination_request_failure_and_observation_failure_are_unverified(tmp_path) -> None:
    api = SupervisionApi(terminate_ok=False)
    supervisor = _supervisor(tmp_path, api)
    assert supervisor.request_termination().diagnostics == ("termination_request_failed",)
    api.fail_observe = True
    observation = supervisor.observe()
    assert observation.state is WindowsRuntimeState.UNKNOWN
    assert not supervisor.confirm_termination().proven


def test_natural_exit_race_does_not_claim_termination_effect(tmp_path) -> None:
    api = SupervisionApi(root_active=False, exit_code=0, process_ids=())
    result = _supervisor(tmp_path, api).request_termination()
    assert result.diagnostics == ("natural_exit_observed",)
    assert not result.termination_requested and api.terminate_calls == 0


def test_lost_handle_is_orphaned_and_requires_reconciliation(tmp_path) -> None:
    workspace, _, command = _resolved(tmp_path)
    supervisor = WindowsProcessSupervisor(
        None, SupervisionApi(), Authorization(), Fencing(), workspace,
        OpaqueReference("grant:one"), command, started_monotonic=0.0,
        authority_context=process_context(command, workspace, OpaqueReference("grant:one")),
        monotonic=lambda: 2.0,
    )
    observation = supervisor.observe()
    assert observation.state is WindowsRuntimeState.ORPHANED
    assert observation.diagnostics == ("reconciliation_required",)
    assert not supervisor.health().full_restart_recovery
