from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from synapse.sandbox import (
    FactCompleteness,
    InvalidResourceLimitBoundary,
    SandboxIsolationProfileId,
    SandboxNetworkGrantService,
    SandboxPolicyVersion,
    SandboxProcessGrantService,
    SandboxResourceCapabilityFact,
    SandboxResourceCapabilitySnapshot,
    SandboxResourceDenialReason,
    SandboxResourceDimension,
    SandboxResourceEnforcement,
    SandboxResourceLimit,
    SandboxResourceLimitPolicy,
    SandboxResourceLimitRequest,
    SandboxResourceLimitRequirement,
    SandboxResourceLimitService,
    SandboxResourceScope,
    SandboxResourceUnit,
)
from test_sandbox_admission_facts import NOW
from test_sandbox_capability_grants import pipeline
from test_sandbox_network_boundary import evaluate as network_evaluate
from test_sandbox_network_boundary import request as network_request
from test_sandbox_network_boundary import setup as network_setup
from test_sandbox_process_boundary import evaluate as process_evaluate
from test_sandbox_process_boundary import process_request
from test_sandbox_process_boundary import setup as process_setup

SHAPES = {
    SandboxResourceDimension.CPU_QUOTA: (
        SandboxResourceUnit.MICROSECONDS_PER_SECOND,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.CPU_TIME: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.MEMORY_WORKING_SET: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.PER_PROCESS,
    ),
    SandboxResourceDimension.MEMORY_COMMIT: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.DISK_SPACE: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.FILE_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.FILE_SIZE: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.STDOUT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.STDERR_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.RESULT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.PROCESS_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.PROCESS_TREE_DEPTH: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.HANDLE_COUNT: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.PROCESS_TREE,
    ),
    SandboxResourceDimension.FILESYSTEM_OPERATIONS: (
        SandboxResourceUnit.OPERATIONS,
        SandboxResourceScope.FILESYSTEM_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_CONNECTIONS: (
        SandboxResourceUnit.COUNT,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_BYTES_SENT: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.NETWORK_BYTES_RECEIVED: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.NETWORK_TOTAL,
    ),
    SandboxResourceDimension.STARTUP_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.IDLE_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.WALL_CLOCK_DURATION: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.TERMINATION_GRACE: (
        SandboxResourceUnit.MILLISECONDS,
        SandboxResourceScope.SANDBOX_TOTAL,
    ),
    SandboxResourceDimension.EVIDENCE_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
    SandboxResourceDimension.ARTIFACT_OUTPUT_BYTES: (
        SandboxResourceUnit.BYTES,
        SandboxResourceScope.OUTPUT_TOTAL,
    ),
}
ALL_ENFORCEMENTS = tuple(
    sorted(SandboxResourceEnforcement, key=lambda item: item.value)
)


def limit(
    dimension=SandboxResourceDimension.CPU_TIME,
    hard=100,
    *,
    soft=None,
    burst=None,
    grace=None,
    unlimited=False,
    unit=None,
    scope=None,
):
    expected_unit, expected_scope = SHAPES[dimension]
    return SandboxResourceLimit(
        dimension,
        unit or expected_unit,
        scope or expected_scope,
        None if unlimited else hard,
        soft,
        burst,
        grace,
        unlimited,
    )


def requirement(
    dimension=SandboxResourceDimension.CPU_TIME,
    hard=80,
    *,
    required=True,
    allow_unlimited=False,
    soft=None,
    burst=None,
    grace=None,
    enforcements=ALL_ENFORCEMENTS,
):
    return SandboxResourceLimitRequirement(
        limit(
            dimension,
            hard,
            soft=soft,
            burst=burst,
            grace=grace,
            unlimited=allow_unlimited and hard is None,
        ),
        required,
        allow_unlimited,
        enforcements,
    )


def fact(
    plan,
    dimension=SandboxResourceDimension.CPU_TIME,
    hard=60,
    *,
    soft=None,
    burst=None,
    grace=None,
    unlimited=False,
    unit=None,
    scope=None,
    enforcements=ALL_ENFORCEMENTS,
    isolation_profiles=None,
    valid_from=NOW - timedelta(hours=1),
    valid_until=NOW + timedelta(hours=1),
):
    return SandboxResourceCapabilityFact(
        plan.plan_id,
        plan.plan_fingerprint,
        limit(
            dimension,
            hard,
            soft=soft,
            burst=burst,
            grace=grace,
            unlimited=unlimited,
            unit=unit,
            scope=scope,
        ),
        enforcements,
        isolation_profiles or (plan.isolation_profile_id,),
        valid_from,
        valid_until,
    )


def setup(
    *,
    requirements=None,
    facts=None,
    completeness=FactCompleteness.COMPLETE,
    base=None,
):
    capability_inputs = base or pipeline()
    process_inputs = process_setup(base=capability_inputs)
    plan, capabilities, filesystem = process_inputs[:3]
    network_grants = network_evaluate(
        network_setup(capability_inputs=capability_inputs),
        (network_request(),),
    )
    network = SandboxNetworkGrantService.build_specification(network_grants)
    process_inputs = (
        process_inputs[0],
        process_inputs[1],
        process_inputs[2],
        network,
        process_inputs[4],
        process_inputs[5],
    )
    process_grants = process_evaluate(
        process_inputs,
        (process_request(plan),),
    )
    process = SandboxProcessGrantService.build_specification(process_grants)
    selected_requirements = (
        (requirement(),) if requirements is None else requirements
    )
    selected_facts = (fact(plan),) if facts is None else facts
    policy = SandboxResourceLimitPolicy.create(
        version=SandboxPolicyVersion("resource-policy:v1"),
        plan=plan,
        filesystem=filesystem,
        network=network,
        process=process,
        requirements=selected_requirements,
    )
    snapshot = SandboxResourceCapabilitySnapshot.create(
        observed_at=NOW,
        completeness=completeness,
        facts=selected_facts,
    )
    return plan, capabilities, filesystem, network, process, snapshot, policy


def evaluate(inputs, requests, *, evaluated_at=NOW, occurred_at=NOW):
    plan, capabilities, filesystem, network, process, facts, policy = inputs
    return SandboxResourceLimitService().evaluate(
        plan,
        capabilities,
        filesystem,
        network,
        process,
        facts,
        policy,
        tuple(requests),
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def requested(value):
    return SandboxResourceLimitRequest(value)


def test_all_required_resource_dimensions_are_closed_and_typed() -> None:
    assert set(SandboxResourceDimension) == set(SHAPES)
    assert len(SandboxResourceDimension) == 23


def test_effective_limit_is_the_most_restrictive_intersection() -> None:
    base = pipeline()
    inputs = setup(
        base=base,
        requirements=(requirement(hard=80, soft=60, burst=50, grace=40),),
        facts=(fact(base[4], hard=70, soft=55, burst=45, grace=35),),
    )
    result = evaluate(
        inputs,
        (requested(limit(hard=90, soft=65, burst=50, grace=45)),),
    )
    effective = result.grants[0].effective
    assert effective.hard == 70
    assert effective.soft == 55
    assert effective.burst == 45
    assert effective.grace == 35
    assert effective.hard <= result.grants[0].requested.hard
    assert effective.hard <= result.grants[0].policy_maximum.hard
    assert effective.hard <= result.grants[0].supported_maximum.hard


def test_required_limit_absence_fails_closed() -> None:
    result = evaluate(setup(), ())
    assert result.denials[0].reason is SandboxResourceDenialReason.LIMIT_ABSENT


def test_unlimited_is_never_inferred_and_requires_three_explicit_inputs() -> None:
    with pytest.raises(InvalidResourceLimitBoundary):
        SandboxResourceLimit(
            SandboxResourceDimension.CPU_TIME,
            SandboxResourceUnit.MILLISECONDS,
            SandboxResourceScope.PROCESS_TREE,
            None,
        )
    base = pipeline()
    inputs = setup(
        base=base,
        requirements=(requirement(hard=None, allow_unlimited=True),),
        facts=(fact(base[4], unlimited=True),),
    )
    granted = evaluate(inputs, (requested(limit(unlimited=True)),))
    assert granted.grants[0].effective.unlimited
    denied = evaluate(inputs, (requested(limit(hard=100)),))
    assert not denied.grants[0].effective.unlimited


def test_soft_burst_and_grace_never_replace_or_expand_hard() -> None:
    with pytest.raises(InvalidResourceLimitBoundary):
        limit(hard=100, soft=101)
    with pytest.raises(InvalidResourceLimitBoundary):
        limit(hard=100, burst=101)
    with pytest.raises(InvalidResourceLimitBoundary):
        limit(hard=100, grace=101)
    base = pipeline()
    granted = evaluate(
        setup(
            base=base,
            requirements=(requirement(hard=100, soft=90, burst=80, grace=70),),
            facts=(fact(base[4], hard=100, soft=85, burst=75, grace=65),),
        ),
        (requested(limit(hard=100, soft=95, burst=90, grace=80)),),
    ).grants[0].effective
    assert granted.soft == 85
    assert granted.burst == 75
    assert granted.grace == 65
    assert granted.hard == 100


def test_cpu_time_and_wall_clock_are_distinct_dimensions() -> None:
    assert SHAPES[SandboxResourceDimension.CPU_TIME][0] is SHAPES[
        SandboxResourceDimension.WALL_CLOCK_DURATION
    ][0]
    assert (
        SandboxResourceDimension.CPU_TIME
        is not SandboxResourceDimension.WALL_CLOCK_DURATION
    )


def test_per_process_memory_does_not_substitute_process_tree_memory() -> None:
    request_limit = limit(
        SandboxResourceDimension.MEMORY_COMMIT,
        unit=SandboxResourceUnit.BYTES,
        scope=SandboxResourceScope.PER_PROCESS,
    )
    base = pipeline()
    inputs = setup(
        base=base,
        requirements=(
            requirement(SandboxResourceDimension.MEMORY_COMMIT),
        ),
        facts=(fact(base[4], SandboxResourceDimension.MEMORY_COMMIT),),
    )
    result = evaluate(inputs, (requested(request_limit),))
    assert result.denials[0].reason is SandboxResourceDenialReason.SCOPE_MISMATCH


def test_bytes_are_not_compared_with_counts() -> None:
    base = pipeline()
    inputs = setup(
        base=base,
        requirements=(requirement(SandboxResourceDimension.FILE_COUNT),),
        facts=(fact(base[4], SandboxResourceDimension.FILE_COUNT),),
    )
    wrong = limit(
        SandboxResourceDimension.FILE_COUNT,
        unit=SandboxResourceUnit.BYTES,
    )
    result = evaluate(inputs, (requested(wrong),))
    assert result.denials[0].reason is SandboxResourceDenialReason.UNIT_MISMATCH


@pytest.mark.parametrize(
    ("dimension", "requested_hard"),
    [
        (SandboxResourceDimension.FILE_COUNT, 11),
        (SandboxResourceDimension.NETWORK_CONNECTIONS, 3),
        (SandboxResourceDimension.PROCESS_COUNT, 3),
    ],
)
def test_existing_specifications_bound_related_effective_limits(
    dimension,
    requested_hard,
) -> None:
    base = pipeline()
    inputs = setup(
        base=base,
        requirements=(
            requirement(dimension, hard=20),
        ),
        facts=(
            fact(base[4], dimension, hard=20),
        ),
    )
    result = evaluate(
        inputs,
        (requested(limit(dimension, hard=requested_hard)),),
    )
    assert result.denials[0].reason is SandboxResourceDenialReason.POLICY_EXCEEDED
    assert "specification.maximum_exceeded" in result.diagnostics


def test_unsupported_enforcement_and_isolation_fail_closed() -> None:
    base = pipeline()
    unsupported = fact(
        base[4],
        enforcements=(SandboxResourceEnforcement.CPU_TIME,),
    )
    denial = evaluate(
        setup(base=base, facts=(unsupported,)),
        (requested(limit()),),
    )
    assert (
        denial.denials[0].reason
        is SandboxResourceDenialReason.UNSUPPORTED_ENFORCEMENT
    )
    wrong_isolation = fact(
        base[4],
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    mismatch = evaluate(
        setup(base=base, facts=(wrong_isolation,)),
        (requested(limit()),),
    )
    assert mismatch.denials[0].reason is SandboxResourceDenialReason.SCOPE_MISMATCH


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.INCOMPLETE, SandboxResourceDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxResourceDenialReason.UNAVAILABLE),
    ],
)
def test_completeness_is_explicit(completeness, reason) -> None:
    result = evaluate(
        setup(completeness=completeness),
        (requested(limit()),),
    )
    assert result.denials[0].reason is reason


def test_stale_and_conflicting_facts_are_distinct() -> None:
    base = pipeline()
    stale = fact(
        base[4],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    stale_result = evaluate(
        setup(base=base, facts=(stale,)),
        (requested(limit()),),
    )
    assert stale_result.denials[0].reason is SandboxResourceDenialReason.STALE
    conflict = evaluate(
        setup(base=base, facts=(fact(base[4]), fact(base[4], hard=50))),
        (requested(limit()),),
    )
    assert (
        conflict.denials[0].reason
        is SandboxResourceDenialReason.CONTRADICTORY_LIMITS
    )
    contradictory_requests = evaluate(
        setup(base=base),
        (requested(limit(hard=100)), requested(limit(hard=90))),
    )
    assert (
        contradictory_requests.denials[0].reason
        is SandboxResourceDenialReason.CONTRADICTORY_LIMITS
    )


def test_input_order_and_occurrence_do_not_change_identity() -> None:
    dimensions = (
        SandboxResourceDimension.CPU_TIME,
        SandboxResourceDimension.MEMORY_WORKING_SET,
    )
    base = pipeline()
    requirements = tuple(requirement(item) for item in dimensions)
    facts = tuple(fact(base[4], item) for item in dimensions)
    left = setup(base=base, requirements=requirements, facts=facts)
    right = setup(
        base=base,
        requirements=tuple(reversed(requirements)),
        facts=tuple(reversed(facts)),
    )
    requests = tuple(requested(limit(item)) for item in dimensions)
    first = evaluate(left, requests)
    replay = evaluate(
        right,
        tuple(reversed(requests)),
        occurred_at=NOW + timedelta(minutes=1),
    )
    assert first.grant_set_id == replay.grant_set_id
    assert first.grant_set_fingerprint == replay.grant_set_fingerprint
    assert first.occurred_at != replay.occurred_at


def test_semantic_change_changes_fingerprint() -> None:
    inputs = setup()
    first = evaluate(inputs, (requested(limit(hard=100)),))
    changed = evaluate(inputs, (requested(limit(hard=90)),))
    assert first.grant_set_fingerprint != changed.grant_set_fingerprint


def test_specification_is_immutable_and_non_operational() -> None:
    grant_set = evaluate(setup(), (requested(limit()),))
    specification = SandboxResourceLimitService.build_specification(grant_set)
    assert specification.effective_limits == tuple(
        grant.effective for grant in grant_set.grants
    )
    assert not hasattr(specification, "measure")
    assert not hasattr(specification, "apply")
    assert not hasattr(specification, "enforce")
    with pytest.raises(FrozenInstanceError):
        specification.effective_limits = ()  # type: ignore[misc]
