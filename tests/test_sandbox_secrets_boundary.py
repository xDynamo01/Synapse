from dataclasses import FrozenInstanceError, fields, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    FactCompleteness,
    InvalidSecretsBoundary,
    SandboxAttemptId,
    SandboxIsolationProfileId,
    SandboxPolicyVersion,
    SandboxResourceDimension,
    SandboxResourceLimitService,
    SandboxSecretCapabilityFact,
    SandboxSecretCapabilitySnapshot,
    SandboxSecretDeclaration,
    SandboxSecretDenialReason,
    SandboxSecretFormat,
    SandboxSecretGrantService,
    SandboxSecretLeaseRequest,
    SandboxSecretOperation,
    SandboxSecretPolicy,
    SandboxSecretPolicyRule,
    SandboxSecretRenewalPolicy,
    SandboxSecretRequest,
)
from test_sandbox_admission_facts import NOW, ref
from test_sandbox_capability_grants import pipeline
from test_sandbox_filesystem_boundary import capability_grant_set_with
from test_sandbox_resource_limits import evaluate as resource_evaluate
from test_sandbox_resource_limits import fact as resource_fact
from test_sandbox_resource_limits import limit as resource_limit
from test_sandbox_resource_limits import requested as resource_requested
from test_sandbox_resource_limits import requirement as resource_requirement
from test_sandbox_resource_limits import setup as resource_setup

ATTEMPT = SandboxAttemptId("attempt:1")
OPERATIONS = tuple(
    sorted(
        (
            SandboxSecretOperation.RESOLVE_REFERENCE,
            SandboxSecretOperation.ACQUIRE_LEASE,
            SandboxSecretOperation.REVOKE_LEASE,
        ),
        key=lambda item: item.value,
    )
)


def declaration(
    name="secret-ref:database",
    *,
    provider="logical-vault",
    purpose="workload-api",
    scope="scope:workspace",
):
    return SandboxSecretDeclaration(
        ref(name),
        provider,
        purpose,
        ref(scope),
        SandboxSecretFormat.OPAQUE,
    )


def lease(
    *,
    not_before=NOW,
    expires_at=NOW + timedelta(seconds=60),
    duration=60,
    usage_count=3,
    renewal=SandboxSecretRenewalPolicy.DENY,
    termination=True,
    timeout=True,
    cancellation=True,
):
    return SandboxSecretLeaseRequest(
        not_before,
        expires_at,
        duration,
        usage_count,
        renewal,
        termination,
        timeout,
        cancellation,
    )


def policy_rule(
    selected_declaration=None,
    *,
    operations=OPERATIONS,
    duration=50,
    usage_count=2,
    renewal=SandboxSecretRenewalPolicy.DENY,
):
    return SandboxSecretPolicyRule(
        selected_declaration or declaration(),
        "python",
        tuple(sorted(operations, key=lambda item: item.value)),
        duration,
        usage_count,
        renewal,
        True,
        True,
        True,
    )


def secret_fact(
    plan,
    selected_declaration=None,
    *,
    attempt=ATTEMPT,
    available=True,
    authorization=True,
    operations=OPERATIONS,
    duration=40,
    usage_count=2,
    renewal=False,
    termination=True,
    timeout=True,
    cancellation=True,
    isolation_profiles=None,
    valid_from=NOW - timedelta(hours=1),
    valid_until=NOW + timedelta(hours=1),
):
    return SandboxSecretCapabilityFact(
        plan.plan_id,
        plan.plan_fingerprint,
        plan.workload_id,
        plan.subject,
        attempt,
        selected_declaration or declaration(),
        available,
        ref("authorization:1") if authorization else None,
        tuple(sorted(operations, key=lambda item: item.value)),
        duration,
        usage_count,
        renewal,
        termination,
        timeout,
        cancellation,
        isolation_profiles or (plan.isolation_profile_id,),
        valid_from,
        valid_until,
    )


def secret_request(
    plan,
    selected_declaration=None,
    *,
    attempt=ATTEMPT,
    operations=OPERATIONS,
    selected_lease=None,
):
    return SandboxSecretRequest(
        selected_declaration or declaration(),
        plan.subject,
        plan.workload_id,
        plan.plan_id,
        plan.plan_fingerprint,
        attempt,
        operations,
        selected_lease or lease(),
    )


def setup(
    *,
    rules=None,
    facts=None,
    completeness=FactCompleteness.COMPLETE,
    base=None,
):
    capability_inputs = base or pipeline()
    plan = capability_inputs[4]
    resource_inputs = resource_setup(
        base=capability_inputs,
        requirements=(
            resource_requirement(
                SandboxResourceDimension.WALL_CLOCK_DURATION,
                hard=30_000,
            ),
        ),
        facts=(
            resource_fact(
                plan,
                SandboxResourceDimension.WALL_CLOCK_DURATION,
                hard=30_000,
            ),
        ),
    )
    resource_grants = resource_evaluate(
        resource_inputs,
        (
            resource_requested(
                resource_limit(
                    SandboxResourceDimension.WALL_CLOCK_DURATION,
                    hard=30_000,
                )
            ),
        ),
    )
    resources = SandboxResourceLimitService.build_specification(resource_grants)
    capabilities = resource_inputs[1]
    selected_rules = (policy_rule(),) if rules is None else rules
    selected_facts = (secret_fact(plan),) if facts is None else facts
    policy = SandboxSecretPolicy.create(
        version=SandboxPolicyVersion("secret-policy:v1"),
        plan=plan,
        resources=resources,
        rules=selected_rules,
    )
    snapshot = SandboxSecretCapabilitySnapshot.create(
        observed_at=NOW,
        completeness=completeness,
        facts=selected_facts,
    )
    return plan, capabilities, resources, snapshot, policy


def evaluate(inputs, requests, *, evaluated_at=NOW, occurred_at=NOW):
    plan, capabilities, resources, facts, policy = inputs
    return SandboxSecretGrantService().evaluate(
        plan,
        capabilities,
        resources,
        facts,
        policy,
        tuple(requests),
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def test_no_secret_value_or_provider_payload_is_representable() -> None:
    public_fields = {
        item.name
        for contract in (
            SandboxSecretDeclaration,
            SandboxSecretRequest,
            SandboxSecretCapabilityFact,
        )
        for item in fields(contract)
    }
    forbidden = {
        "value",
        "secret_value",
        "credential",
        "token",
        "private_key",
        "payload",
        "environment",
        "file_path",
    }
    assert not public_fields & forbidden
    declared = declaration()
    assert declared.secret_ref.value == "secret-ref:database"
    assert declared.provider == "logical-vault"
    assert not hasattr(declared.secret_ref, "provider_payload")


def test_request_or_availability_alone_does_not_create_grant() -> None:
    inputs = setup(facts=())
    absent = evaluate(inputs, (secret_request(inputs[0]),))
    assert not absent.grants
    assert absent.denials[0].reason is SandboxSecretDenialReason.SECRET_UNAVAILABLE
    base = pipeline()
    available = secret_fact(base[4], authorization=False)
    missing_authorization = evaluate(
        setup(base=base, facts=(available,)),
        (secret_request(base[4]),),
    )
    assert (
        missing_authorization.denials[0].reason
        is SandboxSecretDenialReason.AUTHORIZATION_MISSING
    )
    complete = setup()
    no_capability = (
        complete[0],
        capability_grant_set_with(complete[1], grants=()),
        complete[2],
        complete[3],
        complete[4],
    )
    capability_absent = evaluate(
        no_capability,
        (secret_request(complete[0]),),
    )
    assert (
        capability_absent.denials[0].reason
        is SandboxSecretDenialReason.CAPABILITY_ABSENT
    )


def test_external_authorization_is_not_an_active_lease() -> None:
    inputs = setup()
    grant_set = evaluate(inputs, (secret_request(inputs[0]),))
    specification = SandboxSecretGrantService.build_specification(grant_set)
    assert specification.leases == grant_set.grants
    assert not hasattr(specification, "active")
    assert not hasattr(specification, "materialized")
    assert not hasattr(specification, "inject")


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("subject", SandboxSecretDenialReason.SUBJECT_MISMATCH),
        ("purpose", SandboxSecretDenialReason.PURPOSE_MISMATCH),
        ("scope", SandboxSecretDenialReason.SCOPE_MISMATCH),
        ("provider", SandboxSecretDenialReason.PROVIDER_UNSUPPORTED),
        ("attempt", SandboxSecretDenialReason.SCOPE_MISMATCH),
    ],
)
def test_subject_purpose_scope_provider_and_attempt_mismatch_fail_closed(
    change,
    reason,
) -> None:
    base = pipeline()
    plan = base[4]
    request = secret_request(plan)
    rules = (policy_rule(),)
    facts = (secret_fact(plan),)
    if change == "subject":
        request = replace(request, subject=ref("subject:other"))
    elif change == "purpose":
        request = replace(
            request,
            declaration=declaration(purpose="other-purpose"),
        )
    elif change == "scope":
        request = replace(
            request,
            declaration=declaration(scope="scope:other"),
        )
    elif change == "provider":
        request = replace(
            request,
            declaration=declaration(provider="other-provider"),
        )
    else:
        request = replace(request, attempt_id=SandboxAttemptId("attempt:other"))
    result = evaluate(
        setup(base=base, rules=rules, facts=facts),
        (request,),
    )
    assert result.denials[0].reason is reason


def test_plan_mismatch_fails_closed() -> None:
    inputs = setup()
    request = replace(
        secret_request(inputs[0]),
        plan_id=type(inputs[0].plan_id)("sandboxplanid:other"),
    )
    result = evaluate(inputs, (request,))
    assert result.denials[0].reason is SandboxSecretDenialReason.SCOPE_MISMATCH


def test_use_once_is_incompatible_with_renewal() -> None:
    inputs = setup()
    with pytest.raises(InvalidSecretsBoundary):
        secret_request(
            inputs[0],
            operations=(SandboxSecretOperation.USE_ONCE,),
            selected_lease=lease(
                usage_count=1,
                renewal=SandboxSecretRenewalPolicy.EXPLICIT,
            ),
        )
    base = pipeline()
    use_once = (SandboxSecretOperation.USE_ONCE,)
    granted = evaluate(
        setup(
            base=base,
            rules=(policy_rule(operations=use_once, usage_count=1),),
            facts=(
                secret_fact(
                    base[4],
                    operations=use_once,
                    usage_count=1,
                ),
            ),
        ),
        (
            secret_request(
                base[4],
                operations=use_once,
                selected_lease=lease(usage_count=1),
            ),
        ),
    )
    assert granted.grants[0].maximum_usage_count == 1
    assert (
        granted.grants[0].renewal_policy
        is SandboxSecretRenewalPolicy.DENY
    )


def test_renewal_requires_explicit_policy_and_fact_authority() -> None:
    inputs = setup()
    renewal_request = secret_request(
        inputs[0],
        operations=tuple(
            sorted(
                (
                    SandboxSecretOperation.ACQUIRE_LEASE,
                    SandboxSecretOperation.RENEW_LEASE,
                ),
                key=lambda item: item.value,
            )
        ),
        selected_lease=lease(renewal=SandboxSecretRenewalPolicy.EXPLICIT),
    )
    denied = evaluate(inputs, (renewal_request,))
    assert denied.denials[0].reason is SandboxSecretDenialReason.RENEWAL_DENIED
    base = pipeline()
    operations = renewal_request.operations
    allowed = evaluate(
        setup(
            base=base,
            rules=(
                policy_rule(
                    operations=operations,
                    renewal=SandboxSecretRenewalPolicy.EXPLICIT,
                ),
            ),
            facts=(
                secret_fact(
                    base[4],
                    operations=operations,
                    renewal=True,
                ),
            ),
        ),
        (replace(renewal_request, plan_id=base[4].plan_id, plan_fingerprint=base[4].plan_fingerprint, subject=base[4].subject, workload_id=base[4].workload_id),),
    )
    assert allowed.grants[0].renewal_policy is SandboxSecretRenewalPolicy.EXPLICIT


def test_lease_is_bounded_by_request_policy_fact_and_resources() -> None:
    inputs = setup()
    grant = evaluate(inputs, (secret_request(inputs[0]),)).grants[0]
    assert grant.maximum_duration_seconds == 30
    assert grant.maximum_duration_seconds <= 60
    assert grant.maximum_duration_seconds <= 50
    assert grant.maximum_duration_seconds <= 40
    assert grant.maximum_usage_count == 2
    assert grant.expires_at <= NOW + timedelta(seconds=30)


@pytest.mark.parametrize(
    "missing",
    ["termination", "timeout", "cancellation"],
)
def test_required_revocation_must_be_supported_and_requested(missing) -> None:
    base = pipeline()
    kwargs = {
        "termination": missing != "termination",
        "timeout": missing != "timeout",
        "cancellation": missing != "cancellation",
    }
    unsupported = secret_fact(base[4], **kwargs)
    result = evaluate(
        setup(base=base, facts=(unsupported,)),
        (secret_request(base[4]),),
    )
    assert result.denials[0].reason is SandboxSecretDenialReason.LEASE_UNSUPPORTED


def test_isolation_inadequacy_fails_closed() -> None:
    base = pipeline()
    unsupported = secret_fact(
        base[4],
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    result = evaluate(
        setup(base=base, facts=(unsupported,)),
        (secret_request(base[4]),),
    )
    assert (
        result.denials[0].reason
        is SandboxSecretDenialReason.ISOLATION_INSUFFICIENT
    )


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.INCOMPLETE, SandboxSecretDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxSecretDenialReason.SECRET_UNAVAILABLE),
    ],
)
def test_completeness_is_explicit(completeness, reason) -> None:
    inputs = setup(completeness=completeness)
    result = evaluate(inputs, (secret_request(inputs[0]),))
    assert result.denials[0].reason is reason


def test_expired_fact_is_distinct() -> None:
    base = pipeline()
    expired = secret_fact(
        base[4],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    result = evaluate(
        setup(base=base, facts=(expired,)),
        (secret_request(base[4]),),
    )
    assert result.denials[0].reason is SandboxSecretDenialReason.EXPIRED


def test_input_order_and_occurrence_do_not_change_identity() -> None:
    base = pipeline()
    plan = base[4]
    second = declaration("secret-ref:events")
    rules = (policy_rule(), policy_rule(second))
    facts = (secret_fact(plan), secret_fact(plan, second))
    left = setup(base=base, rules=rules, facts=facts)
    right = setup(
        base=base,
        rules=tuple(reversed(rules)),
        facts=tuple(reversed(facts)),
    )
    requests = (secret_request(plan), secret_request(plan, second))
    first = evaluate(left, requests)
    replay = evaluate(
        right,
        tuple(reversed(requests)),
        occurred_at=NOW + timedelta(minutes=1),
    )
    assert first.grant_set_id == replay.grant_set_id
    assert first.grant_set_fingerprint == replay.grant_set_fingerprint
    assert first.occurred_at != replay.occurred_at


def test_lease_specification_is_immutable_and_non_operational() -> None:
    inputs = setup()
    grant_set = evaluate(inputs, (secret_request(inputs[0]),))
    specification = SandboxSecretGrantService.build_specification(grant_set)
    assert not hasattr(specification, "resolve")
    assert not hasattr(specification, "acquire")
    assert not hasattr(specification, "execute")
    with pytest.raises(FrozenInstanceError):
        specification.leases = ()  # type: ignore[misc]
