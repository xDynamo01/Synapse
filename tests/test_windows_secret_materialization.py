from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier, Thread

from tests.factories.windows_authority import process_context
from tests.test_windows_process_driver import Authorization, FakeApi, Fencing, _request, _resolved

from synapse.sandbox import (
    OpaqueReference,
    SandboxAttemptId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxSecretDeclaration,
    SandboxSecretFormat,
    SandboxSecretGrant,
    SandboxSecretOperation,
    SandboxSecretRenewalPolicy,
    SandboxWorkloadId,
)
from synapse.sandbox_drivers import (
    InMemoryWindowsSecretProvider,
    SandboxFencingDecision,
    WindowsExecutionGrantStatus,
    WindowsProcessDriver,
    WindowsProcessStartOutcome,
    WindowsSecretDeliveryRequest,
    WindowsSecretLifecycleState,
    WindowsSecretMaterializationError,
    WindowsSecretMaterializer,
)

SECRET = b"synthetic-super-secret"


def _grant(command, workspace, *, usage=1, expires=None):
    now = datetime.now(timezone.utc)
    return SandboxSecretGrant(
        SandboxSecretDeclaration(
            OpaqueReference("secret:fixture"),
            "controlled-fixture",
            "process-environment",
            OpaqueReference(workspace.value),
            SandboxSecretFormat.UTF8_TEXT,
        ),
        OpaqueReference("subject:test"),
        SandboxWorkloadId(command.workload_reference.value),
        SandboxPlanId(command.plan_reference.value),
        SandboxPlanFingerprint.from_content("plan"),
        SandboxAttemptId(command.attempt_reference.value),
        tuple(
            sorted(
                (SandboxSecretOperation.ACQUIRE_LEASE, SandboxSecretOperation.RESOLVE_REFERENCE),
                key=lambda x: x.value,
            )
        ),
        OpaqueReference("grant:one"),
        now - timedelta(minutes=1),
        expires or now + timedelta(minutes=5),
        int(
            ((expires or now + timedelta(minutes=5)) - (now - timedelta(minutes=1))).total_seconds()
        ),
        usage,
        SandboxSecretRenewalPolicy.DENY,
        True,
        True,
        True,
        (),
    )


class CapturingApi(FakeApi):
    secret_environment = ()

    def create_process_suspended(self, command, stdio=None, secret_environment=()):
        self.secret_environment = secret_environment
        return super().create_process_suspended(command, stdio)


class FailingRevokeProvider(InMemoryWindowsSecretProvider):
    def revoke(self, materialization_reference):
        return False


def _setup(tmp_path, provider_type=InMemoryWindowsSecretProvider, **grant_options):
    workspace, _, command = _resolved(tmp_path)
    provider = provider_type({OpaqueReference("secret:fixture"): SECRET})
    materializer = WindowsSecretMaterializer(provider)
    context = process_context(command, workspace, OpaqueReference("grant:one"))
    delivery = WindowsSecretDeliveryRequest(
        "SYNAPSE_FIXTURE_SECRET", _grant(command, workspace, **grant_options)
    )
    return workspace, command, context, materializer, delivery


def test_explicit_provider_materializes_without_plaintext_projection(tmp_path) -> None:
    workspace, command, context, materializer, delivery = _setup(tmp_path)
    material = materializer.materialize(delivery, context, workspace)
    assert material.environment_value().encode() == SECRET
    assert SECRET.decode() not in repr(material)
    assert SECRET.decode() not in repr(material.fact)
    assert SECRET.decode() not in repr(materializer.health())
    assert material.revoke()
    assert material.fact.state is WindowsSecretLifecycleState.REVOKED


def test_unknown_scope_expiry_revocation_and_cross_attempt_fail_closed(tmp_path) -> None:
    workspace, command, context, materializer, delivery = _setup(tmp_path)
    cases = [
        (
            WindowsSecretMaterializer(InMemoryWindowsSecretProvider({})),
            delivery,
            context,
            "secret_reference_unknown",
        ),
        (
            materializer,
            replace(
                delivery, grant=replace(delivery.grant, subject=OpaqueReference("subject:wrong"))
            ),
            context,
            "secret_subject_mismatch",
        ),
        (
            materializer,
            replace(
                delivery,
                grant=replace(delivery.grant, workload_id=SandboxWorkloadId("workload:wrong")),
            ),
            context,
            "secret_workload_mismatch",
        ),
        (
            materializer,
            replace(
                delivery,
                grant=replace(delivery.grant, attempt_id=SandboxAttemptId("attempt:wrong")),
            ),
            context,
            "secret_attempt_mismatch",
        ),
        (
            materializer,
            delivery,
            replace(context, workspace_id=type(workspace)("workspace:wrong")),
            "secret_scope_mismatch",
        ),
        (
            materializer,
            replace(
                delivery,
                grant=replace(
                    delivery.grant,
                    authorization_ref=OpaqueReference("grant:wrong"),
                ),
            ),
            context,
            "secret_grant_mismatch",
        ),
        (
            materializer,
            delivery,
            replace(
                context,
                grant=replace(context.grant, status=WindowsExecutionGrantStatus.REVOKED),
            ),
            "secret_revoked",
        ),
    ]
    for selected, request, selected_context, expected in cases:
        try:
            selected.materialize(request, selected_context, workspace)
        except WindowsSecretMaterializationError as error:
            assert str(error) == expected and SECRET.decode() not in str(error)
        else:
            raise AssertionError(expected)


def test_usage_is_atomic_and_exhaustion_is_closed(tmp_path) -> None:
    workspace, _, context, materializer, delivery = _setup(tmp_path, usage=1)
    barrier = Barrier(3)
    outcomes = []

    def run():
        barrier.wait()
        try:
            outcomes.append(materializer.materialize(delivery, context, workspace))
        except WindowsSecretMaterializationError as error:
            outcomes.append(str(error))

    threads = [Thread(target=run), Thread(target=run)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()
    assert sum(not isinstance(item, str) for item in outcomes) == 1
    assert "secret_usage_exhausted" in outcomes
    for item in outcomes:
        if not isinstance(item, str):
            item.revoke()


def test_controlled_environment_delivery_and_revocation_before_resume(tmp_path) -> None:
    workspace, command, _, materializer, delivery = _setup(tmp_path)
    api = CapturingApi()
    request = replace(_request(workspace, command), secret_deliveries=(delivery,))
    result = WindowsProcessDriver(
        api, Authorization(), Fencing(), secret_materializer=materializer, platform_available=True
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.STARTED
    assert api.secret_environment == (("SYNAPSE_FIXTURE_SECRET", SECRET.decode()),)
    assert api.marker == ["user-code"]
    assert SECRET.decode() not in repr(result)
    assert SECRET.decode() not in repr(command.command_fingerprint)


def test_stale_fencing_and_failed_revocation_never_resume(tmp_path) -> None:
    workspace, command, _, materializer, delivery = _setup(tmp_path)
    request = replace(_request(workspace, command), secret_deliveries=(delivery,))
    stale = Fencing([SandboxFencingDecision.VALID] * 8 + [SandboxFencingDecision.STALE])
    api = CapturingApi()
    result = WindowsProcessDriver(
        api, Authorization(), stale, secret_materializer=materializer, platform_available=True
    ).start(request)
    assert result.outcome is WindowsProcessStartOutcome.FAILED
    assert not api.marker

    _, command2, _, failing, second_delivery = _setup(
        tmp_path / "revocation", FailingRevokeProvider
    )
    api2 = CapturingApi()
    request2 = replace(_request(workspace, command2), secret_deliveries=(second_delivery,))
    result2 = WindowsProcessDriver(
        api2, Authorization(), Fencing(), secret_materializer=failing, platform_available=True
    ).start(request2)
    assert result2.diagnostic_codes == ("secret_revocation_unproven",)
    assert not api2.marker


def test_replay_never_calls_provider_and_marks_unproven(tmp_path) -> None:
    workspace, _, context, materializer, delivery = _setup(tmp_path)
    fact = materializer.materialize(delivery, context, workspace).fact
    replayed = WindowsSecretMaterializer.replay(fact)
    assert replayed.state is WindowsSecretLifecycleState.REVOCATION_UNPROVEN
    assert replayed.reconciliation_required
