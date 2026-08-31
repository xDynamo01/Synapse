from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    FactCompleteness,
    InvalidProcessBoundary,
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxChildProcessPolicy,
    SandboxFilesystemGrantService,
    SandboxFilesystemOperation,
    SandboxFilesystemResource,
    SandboxHandleInheritancePolicy,
    SandboxIsolationProfileId,
    SandboxLogicalEntrypoint,
    SandboxNetworkGrantService,
    SandboxPolicyVersion,
    SandboxProcessArgument,
    SandboxProcessArgumentKind,
    SandboxProcessCapabilityFact,
    SandboxProcessCapabilitySnapshot,
    SandboxProcessCleanupRequirements,
    SandboxProcessDenialReason,
    SandboxProcessEnforcement,
    SandboxProcessEnvironmentEntry,
    SandboxProcessGrantService,
    SandboxProcessLimits,
    SandboxProcessOperation,
    SandboxProcessOperationCapability,
    SandboxProcessPolicy,
    SandboxProcessRequest,
    SandboxProcessStartupRequirements,
    SandboxProcessStdioPolicy,
    SandboxProcessTerminationRequirements,
    SandboxRuntimeDescriptor,
    SandboxRuntimeKind,
)
from test_sandbox_admission_facts import NOW, ref
from test_sandbox_capability_grants import evaluate as capability_evaluate
from test_sandbox_capability_grants import pipeline
from test_sandbox_filesystem_boundary import capability_grant_set_with
from test_sandbox_filesystem_boundary import evaluate as filesystem_evaluate
from test_sandbox_filesystem_boundary import request as filesystem_request
from test_sandbox_filesystem_boundary import resource_fact as filesystem_fact
from test_sandbox_filesystem_boundary import rule as filesystem_rule
from test_sandbox_filesystem_boundary import setup as filesystem_setup
from test_sandbox_network_boundary import evaluate as network_evaluate
from test_sandbox_network_boundary import setup as network_setup

LIMITS = SandboxProcessLimits(4, 3, 2, 8, 512, 4, 512, 30, 10)
REQUEST_LIMITS = SandboxProcessLimits(2, 2, 0, 4, 128, 2, 128, 15, 5)
ENFORCEMENTS = tuple(SandboxProcessEnforcement)
STARTUP = SandboxProcessStartupRequirements(True, True)
TERMINATION = SandboxProcessTerminationRequirements(True, True)
CLEANUP = SandboxProcessCleanupRequirements(True, True)


def specifications(base):
    plan = base[4]
    artifact_rule = filesystem_rule(
        SandboxFilesystemResource.ARTIFACT,
        operations=(SandboxFilesystemOperation.EXECUTE,),
        executable=True,
    )
    artifact_fact = filesystem_fact(
        plan,
        SandboxFilesystemResource.ARTIFACT,
        scope="scope:workspace",
    )
    workspace_rule = filesystem_rule()
    workspace_fact = filesystem_fact(plan)
    filesystem_inputs = filesystem_setup(
        rules=(artifact_rule, workspace_rule),
        facts=(artifact_fact, workspace_fact),
        capability_inputs=base,
    )
    filesystem_grants = filesystem_evaluate(
        filesystem_inputs,
        (
            filesystem_request(
                resource=SandboxFilesystemResource.ARTIFACT,
                operation=SandboxFilesystemOperation.EXECUTE,
                executable=True,
            ),
            filesystem_request(),
        ),
    )
    filesystem = SandboxFilesystemGrantService.build_specification(
        filesystem_grants
    )
    network_inputs = network_setup(
        rules=(),
        facts=(),
        capability_inputs=base,
    )
    network_grants = network_evaluate(network_inputs, ())
    network = SandboxNetworkGrantService.build_specification(network_grants)
    return filesystem, network


def process_policy(plan, *, operations=(SandboxProcessOperation.START,)):
    return SandboxProcessPolicy.create(
        version=SandboxPolicyVersion("process-policy:v1"),
        plan=plan,
        allowed_operations=operations,
        capability_requirements=tuple(
            SandboxProcessOperationCapability(operation, "python")
            for operation in operations
        ),
        allowed_argument_kinds=tuple(SandboxProcessArgumentKind),
        allowed_working_roots=(SandboxFilesystemResource.WORKSPACE,),
        allowed_environment_names=("LANG", "MODE"),
        allowed_stdio=(
            SandboxProcessStdioPolicy.CLOSED,
            SandboxProcessStdioPolicy.CAPTURED,
        ),
        child_policy=(
            SandboxChildProcessPolicy.SAME_SUPERVISED_TREE
            if SandboxProcessOperation.SPAWN_CHILD in operations
            else SandboxChildProcessPolicy.DENY
        ),
        handle_policy=SandboxHandleInheritancePolicy.NONE,
        allowed_handle_refs=(),
        startup_requirements=STARTUP,
        termination_requirements=TERMINATION,
        cleanup_requirements=CLEANUP,
        limits=LIMITS,
        required_enforcements=ENFORCEMENTS,
    )


def process_fact(
    plan,
    *,
    operations=(SandboxProcessOperation.START,),
    environment=("LANG", "MODE"),
    child_policy=SandboxChildProcessPolicy.DENY,
    handle_policy=SandboxHandleInheritancePolicy.NONE,
    handles=(),
    enforcements=ENFORCEMENTS,
    isolation_profiles=None,
    valid_from=NOW - timedelta(hours=1),
    valid_until=NOW + timedelta(hours=1),
):
    return SandboxProcessCapabilityFact(
        plan.plan_id,
        plan.plan_fingerprint,
        plan.runtime,
        plan.entrypoint,
        plan.artifact_fingerprint,
        operations,
        ref("scope:workspace"),
        environment,
        handles,
        child_policy,
        handle_policy,
        STARTUP,
        TERMINATION,
        CLEANUP,
        LIMITS,
        enforcements,
        isolation_profiles or (plan.isolation_profile_id,),
        valid_from,
        valid_until,
    )


def process_request(
    plan,
    *,
    operations=(SandboxProcessOperation.START,),
    arguments=(),
    environment=(),
    child_policy=SandboxChildProcessPolicy.DENY,
    handle_policy=SandboxHandleInheritancePolicy.NONE,
    handles=(),
    detached=False,
    limits=REQUEST_LIMITS,
):
    return SandboxProcessRequest(
        plan.runtime,
        plan.entrypoint,
        plan.artifact_fingerprint,
        operations,
        arguments,
        SandboxFilesystemResource.WORKSPACE,
        environment,
        SandboxProcessStdioPolicy.CLOSED,
        SandboxProcessStdioPolicy.CAPTURED,
        SandboxProcessStdioPolicy.CAPTURED,
        child_policy,
        handle_policy,
        handles,
        detached,
        STARTUP,
        TERMINATION,
        CLEANUP,
        limits,
    )


def setup(
    *,
    operations=(SandboxProcessOperation.START,),
    facts=None,
    completeness=FactCompleteness.COMPLETE,
    selected_admission_policy=None,
    base=None,
):
    inputs = base or pipeline(admission_policy=selected_admission_policy)
    plan = inputs[4]
    capabilities = capability_evaluate(inputs)
    filesystem, network = specifications(inputs)
    selected_facts = (
        (
            process_fact(
                plan,
                operations=operations,
                child_policy=(
                    SandboxChildProcessPolicy.SAME_SUPERVISED_TREE
                    if SandboxProcessOperation.SPAWN_CHILD in operations
                    else SandboxChildProcessPolicy.DENY
                ),
            ),
        )
        if facts is None
        else facts
    )
    snapshot = SandboxProcessCapabilitySnapshot.create(
        observed_at=NOW,
        completeness=completeness,
        facts=selected_facts,
    )
    return (
        plan,
        capabilities,
        filesystem,
        network,
        snapshot,
        process_policy(plan, operations=operations),
    )


def evaluate(inputs, requests, *, evaluated_at=NOW, occurred_at=NOW):
    plan, capabilities, filesystem, network, facts, policy = inputs
    return SandboxProcessGrantService().evaluate(
        plan,
        capabilities,
        filesystem,
        network,
        facts,
        policy,
        tuple(requests),
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def test_shell_or_command_string_is_not_representable() -> None:
    for token in ("python -m app", "app;whoami", "$(command)", "a|b", "a>b"):
        with pytest.raises(InvalidProcessBoundary):
            SandboxProcessArgument(SandboxProcessArgumentKind.TOKEN, token=token)
    assert not hasattr(SandboxProcessRequest, "command")
    assert not hasattr(SandboxProcessRequest, "shell")


def test_runtime_and_entrypoint_must_match_plan() -> None:
    inputs = setup()
    plan = inputs[0]
    wrong_runtime = replace(
        process_request(plan),
        runtime=SandboxRuntimeDescriptor(SandboxRuntimeKind.WASM, "1"),
    )
    runtime_denial = evaluate(inputs, (wrong_runtime,))
    assert runtime_denial.denials[0].reason is SandboxProcessDenialReason.RUNTIME_DENIED
    wrong_entrypoint = replace(
        process_request(plan),
        entrypoint=SandboxLogicalEntrypoint("other.module:main"),
    )
    entrypoint_denial = evaluate(inputs, (wrong_entrypoint,))
    assert (
        entrypoint_denial.denials[0].reason
        is SandboxProcessDenialReason.ENTRYPOINT_MISMATCH
    )


def test_environment_is_explicit_and_opaque() -> None:
    inputs = setup()
    plan = inputs[0]
    entry = SandboxProcessEnvironmentEntry("LANG", ref("environment:lang"))
    result = evaluate(inputs, (process_request(plan, environment=(entry,)),))
    assert result.grants[0].environment == (entry,)
    assert isinstance(entry.value_ref, OpaqueReference)
    assert not hasattr(process_request(plan), "inherit_environment")
    assert not hasattr(entry, "value")
    denied_entry = SandboxProcessEnvironmentEntry(
        "HOST_PATH",
        ref("environment:host-path"),
    )
    denied = evaluate(
        inputs,
        (process_request(plan, environment=(denied_entry,)),),
    )
    assert denied.denials[0].reason is SandboxProcessDenialReason.ENVIRONMENT_DENIED


def test_fact_with_unsupported_runtime_is_distinct_from_policy_denial() -> None:
    base = pipeline()
    unsupported = replace(
        process_fact(base[4]),
        runtime=SandboxRuntimeDescriptor(SandboxRuntimeKind.WASM, "1"),
    )
    inputs = setup(base=base, facts=(unsupported,))
    result = evaluate(inputs, (process_request(inputs[0]),))
    assert (
        result.denials[0].reason
        is SandboxProcessDenialReason.RUNTIME_UNSUPPORTED
    )


def test_start_does_not_grant_spawn_child() -> None:
    inputs = setup()
    plan = inputs[0]
    child_request = process_request(
        plan,
        operations=(SandboxProcessOperation.SPAWN_CHILD,),
        child_policy=SandboxChildProcessPolicy.SAME_SUPERVISED_TREE,
    )
    result = evaluate(inputs, (child_request,))
    assert result.denials[0].reason is SandboxProcessDenialReason.CHILD_PROCESS_DENIED


def test_spawn_child_is_bound_to_same_tree_and_cannot_detach() -> None:
    operations = (
        SandboxProcessOperation.START,
        SandboxProcessOperation.SPAWN_CHILD,
    )
    inputs = setup(operations=operations)
    plan = inputs[0]
    granted = evaluate(
        inputs,
        (
            process_request(
                plan,
                operations=operations,
                child_policy=SandboxChildProcessPolicy.SAME_SUPERVISED_TREE,
            ),
        ),
    )
    assert granted.grants[0].child_policy is SandboxChildProcessPolicy.SAME_SUPERVISED_TREE
    detached = evaluate(
        inputs,
        (
            process_request(
                plan,
                operations=operations,
                child_policy=SandboxChildProcessPolicy.SAME_SUPERVISED_TREE,
                detached=True,
            ),
        ),
    )
    assert (
        detached.denials[0].reason
        is SandboxProcessDenialReason.DETACHED_PROCESS_DENIED
    )


def test_handles_are_not_inherited_without_explicit_authority() -> None:
    inputs = setup()
    plan = inputs[0]
    with pytest.raises(InvalidProcessBoundary):
        process_request(plan, handles=(ref("handle:1"),))
    explicit = process_request(
        plan,
        handle_policy=SandboxHandleInheritancePolicy.EXPLICIT_ALLOWLIST,
        handles=(ref("handle:1"),),
    )
    result = evaluate(inputs, (explicit,))
    assert (
        result.denials[0].reason
        is SandboxProcessDenialReason.HANDLE_INHERITANCE_DENIED
    )


def test_executable_artifact_is_fingerprint_and_filesystem_bound() -> None:
    inputs = setup()
    plan = inputs[0]
    mismatched = replace(
        process_request(plan),
        artifact_fingerprint=SandboxArtifactFingerprint.from_content("other"),
    )
    result = evaluate(inputs, (mismatched,))
    assert result.denials[0].reason is SandboxProcessDenialReason.MISMATCH
    filesystem = inputs[2]
    empty_content = (
        filesystem.plan_id,
        filesystem.plan_fingerprint,
        filesystem.grant_set_id,
        filesystem.grant_set_fingerprint,
        (),
    )
    empty_filesystem = type(filesystem)(
        filesystem.plan_id,
        filesystem.plan_fingerprint,
        filesystem.grant_set_id,
        filesystem.grant_set_fingerprint,
        (),
        SandboxArtifactFingerprint.from_content(empty_content),
    )
    absent = evaluate(
        (
            inputs[0],
            inputs[1],
            empty_filesystem,
            inputs[3],
            inputs[4],
            inputs[5],
        ),
        (process_request(plan),),
    )
    assert absent.denials[0].reason is SandboxProcessDenialReason.MISMATCH


def test_capability_and_process_fact_are_both_required() -> None:
    inputs = setup()
    no_capability_grants = capability_grant_set_with(
        inputs[1],
        grants=(),
    )
    no_capability = (
        inputs[0],
        no_capability_grants,
        inputs[2],
        inputs[3],
        inputs[4],
        inputs[5],
    )
    denied = evaluate(no_capability, (process_request(inputs[0]),))
    assert denied.denials[0].reason is SandboxProcessDenialReason.CAPABILITY_ABSENT
    no_fact = setup(facts=())
    denied_fact = evaluate(no_fact, (process_request(no_fact[0]),))
    assert denied_fact.denials[0].reason is SandboxProcessDenialReason.MISMATCH


@pytest.mark.parametrize(
    "missing",
    [
        SandboxProcessEnforcement.DESCENDANT_TRACKING,
        SandboxProcessEnforcement.VERIFIED_TERMINATION,
    ],
)
def test_required_tree_and_termination_enforcement_fail_closed(missing) -> None:
    base = pipeline()
    fact = process_fact(
        base[4],
        enforcements=tuple(item for item in ENFORCEMENTS if item is not missing),
    )
    inputs = setup(base=base, facts=(fact,))
    result = evaluate(inputs, (process_request(inputs[0]),))
    assert (
        result.denials[0].reason
        is SandboxProcessDenialReason.ENFORCEMENT_UNSUPPORTED
    )


def test_grant_never_expands_operations_environment_or_limits() -> None:
    inputs = setup()
    plan = inputs[0]
    environment = (SandboxProcessEnvironmentEntry("MODE", ref("environment:mode")),)
    arguments = (
        SandboxProcessArgument(SandboxProcessArgumentKind.TOKEN, token="worker"),
        SandboxProcessArgument(SandboxProcessArgumentKind.INTEGER, integer=2),
    )
    requested = process_request(
        plan,
        arguments=arguments,
        environment=environment,
    )
    grant = evaluate(inputs, (requested,)).grants[0]
    assert grant.operations == requested.operations
    assert grant.environment == environment
    assert grant.arguments == arguments
    assert grant.limits == REQUEST_LIMITS
    assert grant.startup_requirements == STARTUP
    assert grant.termination_requirements == TERMINATION
    assert grant.cleanup_requirements == CLEANUP


def test_structural_limits_are_enforced() -> None:
    inputs = setup()
    plan = inputs[0]
    arguments = tuple(
        SandboxProcessArgument(SandboxProcessArgumentKind.TOKEN, token=f"arg-{index}")
        for index in range(5)
    )
    result = evaluate(inputs, (process_request(plan, arguments=arguments),))
    assert result.denials[0].reason is SandboxProcessDenialReason.LIMIT_EXCEEDED


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.INCOMPLETE, SandboxProcessDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxProcessDenialReason.UNAVAILABLE),
    ],
)
def test_completeness_is_explicit(completeness, reason) -> None:
    inputs = setup(completeness=completeness)
    result = evaluate(inputs, (process_request(inputs[0]),))
    assert result.denials[0].reason is reason


def test_stale_fact_is_distinct() -> None:
    base = pipeline()
    stale = process_fact(
        base[4],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    inputs = setup(base=base, facts=(stale,))
    result = evaluate(inputs, (process_request(inputs[0]),))
    assert result.denials[0].reason is SandboxProcessDenialReason.STALE


def test_request_order_and_occurrence_do_not_change_identity() -> None:
    operations = (
        SandboxProcessOperation.START,
        SandboxProcessOperation.INSPECT_STATUS,
    )
    inputs = setup(operations=operations)
    plan = inputs[0]
    requests = (
        process_request(plan, operations=(SandboxProcessOperation.START,)),
        process_request(plan, operations=(SandboxProcessOperation.INSPECT_STATUS,)),
    )
    first = evaluate(inputs, requests)
    replay = evaluate(
        inputs,
        tuple(reversed(requests)),
        occurred_at=NOW + timedelta(minutes=1),
    )
    assert first.grant_set_id == replay.grant_set_id
    assert first.grant_set_fingerprint == replay.grant_set_fingerprint
    assert first.occurred_at != replay.occurred_at


def test_specification_is_immutable_and_non_operational() -> None:
    inputs = setup()
    grant_set = evaluate(inputs, (process_request(inputs[0]),))
    specification = SandboxProcessGrantService.build_specification(grant_set)
    assert specification.grants == grant_set.grants
    assert not hasattr(specification, "start")
    assert not hasattr(specification, "signal")
    assert not hasattr(specification, "terminate")
    assert not hasattr(specification, "executable")
    with pytest.raises(FrozenInstanceError):
        specification.grants = ()  # type: ignore[misc]


def test_isolation_profile_mismatch_fails_closed() -> None:
    base = pipeline()
    fact = process_fact(
        base[4],
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    inputs = setup(base=base, facts=(fact,))
    result = evaluate(inputs, (process_request(inputs[0]),))
    assert result.denials[0].reason is SandboxProcessDenialReason.MISMATCH
