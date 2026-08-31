from dataclasses import FrozenInstanceError, replace
from datetime import timedelta

import pytest

from synapse.sandbox import (
    FactCompleteness,
    InvalidFilesystemBoundary,
    SandboxCapabilityGrantSetId,
    SandboxCapabilityScope,
    SandboxCapabilityScopeKind,
    SandboxFilesystemCapabilityRequirement,
    SandboxFilesystemDenialReason,
    SandboxFilesystemEnforcement,
    SandboxFilesystemGrantService,
    SandboxFilesystemLimits,
    SandboxFilesystemLinkKind,
    SandboxFilesystemOperation,
    SandboxFilesystemPolicy,
    SandboxFilesystemRequest,
    SandboxFilesystemResource,
    SandboxFilesystemResourceFact,
    SandboxFilesystemResourceRule,
    SandboxFilesystemResourceSnapshot,
    SandboxIsolationProfileId,
    SandboxLogicalPath,
    SandboxPolicyVersion,
    derive_identity,
)
from test_sandbox_admission_facts import NOW, ref
from test_sandbox_admission_policy import policy as admission_policy
from test_sandbox_capability_grants import evaluate as capability_evaluate
from test_sandbox_capability_grants import pipeline

LIMITS = SandboxFilesystemLimits(8, 100, 1_000_000)
ENFORCEMENTS = tuple(SandboxFilesystemEnforcement)


def capability_requirement(operation, capability="python"):
    return SandboxFilesystemCapabilityRequirement(operation, capability)


def rule(
    resource=SandboxFilesystemResource.WORKSPACE,
    *,
    operations=(SandboxFilesystemOperation.READ,),
    read_only=False,
    create_only=False,
    allow_overwrite=False,
    require_atomic=False,
    executable=False,
    links=(SandboxFilesystemLinkKind.NONE,),
    limits=LIMITS,
    enforcements=ENFORCEMENTS,
):
    return SandboxFilesystemResourceRule(
        resource=resource,
        allowed_operations=operations,
        capability_requirements=tuple(capability_requirement(item) for item in operations),
        case_sensitive=True,
        read_only=read_only,
        create_only=create_only,
        allow_overwrite=allow_overwrite,
        require_atomic_replace=require_atomic,
        allow_executable_content=executable,
        allowed_links=links,
        limits=limits,
        required_enforcements=enforcements,
    )


def resource_fact(
    plan,
    resource=SandboxFilesystemResource.WORKSPACE,
    *,
    scope="scope:workspace",
    operations=tuple(SandboxFilesystemOperation),
    read_only=False,
    writable=True,
    create_only=False,
    limits=LIMITS,
    enforcements=ENFORCEMENTS,
    isolation_profiles=None,
    valid_from=NOW - timedelta(hours=1),
    valid_until=NOW + timedelta(hours=1),
):
    return SandboxFilesystemResourceFact(
        plan_id=plan.plan_id,
        plan_fingerprint=plan.plan_fingerprint,
        resource=resource,
        scope_ref=ref(scope),
        allowed_operations=operations,
        read_only=read_only,
        writable=writable,
        create_only=create_only,
        limits=limits,
        supported_enforcements=enforcements,
        isolation_profiles=isolation_profiles or (plan.isolation_profile_id,),
        valid_from=valid_from,
        valid_until=valid_until,
    )


def setup(
    *,
    rules=None,
    facts=None,
    selected_admission_policy=None,
    capability_inputs=None,
):
    inputs = capability_inputs or pipeline(admission_policy=selected_admission_policy)
    plan = inputs[4]
    capability_grants = capability_evaluate(inputs)
    selected_rules = rules or (rule(),)
    selected_facts = facts or (resource_fact(plan),)
    filesystem_policy = SandboxFilesystemPolicy.create(
        version=SandboxPolicyVersion("filesystem-policy:v1"),
        plan=plan,
        rules=selected_rules,
    )
    snapshot = SandboxFilesystemResourceSnapshot.create(
        observed_at=NOW,
        completeness=FactCompleteness.COMPLETE,
        facts=selected_facts,
    )
    return plan, capability_grants, snapshot, filesystem_policy


def request(
    *,
    resource=SandboxFilesystemResource.WORKSPACE,
    path="src/main.py",
    operation=SandboxFilesystemOperation.READ,
    limits=SandboxFilesystemLimits(4, 10, 1000),
    link=SandboxFilesystemLinkKind.NONE,
    overwrite=False,
    atomic=False,
    executable=False,
):
    return SandboxFilesystemRequest(
        resource,
        path,
        operation,
        limits,
        link,
        overwrite,
        atomic,
        executable,
    )


def evaluate(fs_inputs, requests, *, evaluated_at=NOW, occurred_at=NOW):
    plan, capabilities, resources, filesystem_policy = fs_inputs
    return SandboxFilesystemGrantService().evaluate(
        plan,
        capabilities,
        resources,
        filesystem_policy,
        tuple(requests),
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def capability_grant_set_with(grant_set, *, grants):
    values = (
        grant_set.request_fingerprint,
        grant_set.admission_snapshot_fingerprint,
        grant_set.permission_snapshot_fingerprint,
        grant_set.policy_id,
        grant_set.policy_fingerprint,
        grant_set.decision_id,
        grant_set.decision_fingerprint,
        grant_set.plan_id,
        grant_set.plan_fingerprint,
        grant_set.evaluated_at,
        grants,
        (),
        grant_set.rationale_codes,
    )
    fingerprint = type(grant_set.grant_set_fingerprint).from_content(values)
    return type(grant_set)(
        derive_identity(SandboxCapabilityGrantSetId, fingerprint),
        fingerprint,
        *values[:10],
        grants,
        (),
        grant_set.rationale_codes,
        grant_set.occurred_at,
    )


def test_filesystem_is_deny_by_default() -> None:
    plan, capabilities, resources, _ = setup()
    empty_policy = SandboxFilesystemPolicy.create(
        version=SandboxPolicyVersion("filesystem-policy:empty"),
        plan=plan,
        rules=(),
    )
    result = evaluate(
        (plan, capabilities, resources, empty_policy),
        (request(),),
    )
    assert not result.grants
    assert result.denials[0].reason is SandboxFilesystemDenialReason.OPERATION_DENIED


@pytest.mark.parametrize(
    "expression",
    [
        "/home/user/file",
        r"C:\Users\user\file",
        r"folder\file",
        "folder//file",
        "./file",
        "folder/",
        "~user/file",
        "CON/file",
    ],
)
def test_invalid_or_host_paths_never_become_logical_paths(expression: str) -> None:
    with pytest.raises(InvalidFilesystemBoundary):
        SandboxLogicalPath.parse(expression, case_sensitive=True)
    result = evaluate(setup(), (request(path=expression),))
    assert not result.grants
    assert result.denials[0].reason is SandboxFilesystemDenialReason.PATH_INVALID


@pytest.mark.parametrize("expression", ["../escape", "folder/../escape"])
def test_traversal_fails_closed_without_normalization(expression: str) -> None:
    result = evaluate(setup(), (request(path=expression),))
    assert result.denials[0].reason is SandboxFilesystemDenialReason.TRAVERSAL
    assert not result.grants


def test_case_sensitivity_is_declared_and_canonical() -> None:
    insensitive = replace(rule(), case_sensitive=False)
    result = evaluate(setup(rules=(insensitive,)), (request(path="Src/Main.PY"),))
    assert result.grants[0].path.value == "src/main.py"
    assert not result.grants[0].path.case_sensitive


@pytest.mark.parametrize(
    "operation",
    [
        SandboxFilesystemOperation.WRITE,
        SandboxFilesystemOperation.APPEND,
        SandboxFilesystemOperation.DELETE,
        SandboxFilesystemOperation.EXECUTE,
    ],
)
def test_read_policy_never_expands_to_mutation_or_execute(operation) -> None:
    result = evaluate(setup(), (request(operation=operation),))
    assert not result.grants
    assert result.denials[0].reason is SandboxFilesystemDenialReason.OPERATION_DENIED


def test_execute_requires_an_explicit_capability_mapping_and_content_rule() -> None:
    execute_rule = rule(
        operations=(SandboxFilesystemOperation.EXECUTE,),
        executable=True,
    )
    result = evaluate(
        setup(rules=(execute_rule,)),
        (
            request(
                operation=SandboxFilesystemOperation.EXECUTE,
                executable=True,
            ),
        ),
    )
    assert result.grants[0].operation is SandboxFilesystemOperation.EXECUTE
    assert result.grants[0].executable_content


def test_create_does_not_imply_overwrite_and_atomic_replace_is_explicit() -> None:
    write_rule = rule(
        operations=(SandboxFilesystemOperation.CREATE, SandboxFilesystemOperation.WRITE),
        create_only=True,
        require_atomic=True,
        enforcements=ENFORCEMENTS,
    )
    fs_inputs = setup(rules=(write_rule,))
    overwrite = evaluate(
        fs_inputs,
        (
            request(
                operation=SandboxFilesystemOperation.CREATE,
                overwrite=True,
                atomic=True,
            ),
        ),
    )
    assert overwrite.denials[0].reason is SandboxFilesystemDenialReason.OPERATION_DENIED
    nonatomic = evaluate(
        fs_inputs,
        (request(operation=SandboxFilesystemOperation.WRITE, atomic=False),),
    )
    assert (
        nonatomic.denials[0].reason
        is SandboxFilesystemDenialReason.UNSUPPORTED_ENFORCEMENT
    )


def test_artifact_read_only_cannot_receive_mutation() -> None:
    base = pipeline()
    plan = base[4]
    artifact_rule = rule(
        SandboxFilesystemResource.ARTIFACT,
        operations=(SandboxFilesystemOperation.READ, SandboxFilesystemOperation.WRITE),
    )
    artifact_fact = resource_fact(
        plan,
        SandboxFilesystemResource.ARTIFACT,
        scope="scope:workspace",
        read_only=False,
        writable=True,
    )
    fs_inputs = setup(
        rules=(artifact_rule,),
        facts=(artifact_fact,),
        capability_inputs=base,
    )
    result = evaluate(
        fs_inputs,
        (
            request(
                resource=SandboxFilesystemResource.ARTIFACT,
                operation=SandboxFilesystemOperation.WRITE,
            ),
        ),
    )
    assert result.denials[0].reason is SandboxFilesystemDenialReason.OPERATION_DENIED


def test_capability_and_resource_scope_are_both_required() -> None:
    fs_inputs = setup()
    plan, capability_grants, resources, filesystem_policy = fs_inputs
    missing_capability = capability_grant_set_with(capability_grants, grants=())
    no_capability = evaluate(
        (plan, missing_capability, resources, filesystem_policy),
        (request(),),
    )
    assert (
        no_capability.denials[0].reason
        is SandboxFilesystemDenialReason.CAPABILITY_ABSENT
    )

    wrong_scope_grants = tuple(
        replace(
            item,
            scopes=(
                SandboxCapabilityScope(
                    SandboxCapabilityScopeKind.EXACT, ref("scope:other")
                ),
            ),
        )
        for item in capability_grants.grants
    )
    changed = capability_grant_set_with(
        capability_grants,
        grants=wrong_scope_grants,
    )
    no_scope = evaluate(
        (plan, changed, resources, filesystem_policy),
        (request(),),
    )
    assert (
        no_scope.denials[0].reason
        is SandboxFilesystemDenialReason.RESOURCE_SCOPE_ABSENT
    )

    denied_inputs = setup(
        selected_admission_policy=admission_policy(allowed_capabilities=())
    )
    no_capability = evaluate(denied_inputs, (request(),))
    assert (
        no_capability.denials[0].reason
        is SandboxFilesystemDenialReason.CAPABILITY_ABSENT
    )


@pytest.mark.parametrize(
    "link",
    [
        SandboxFilesystemLinkKind.SYMLINK,
        SandboxFilesystemLinkKind.JUNCTION,
        SandboxFilesystemLinkKind.REPARSE_POINT,
        SandboxFilesystemLinkKind.HARDLINK,
    ],
)
def test_links_are_not_followed_implicitly(link) -> None:
    result = evaluate(setup(), (request(link=link),))
    assert result.denials[0].reason is SandboxFilesystemDenialReason.LINK_POLICY


def test_limits_never_expand_beyond_request_policy_or_resource() -> None:
    result = evaluate(
        setup(),
        (request(limits=SandboxFilesystemLimits(9, 101, 1_000_001)),),
    )
    assert result.denials[0].reason is SandboxFilesystemDenialReason.LIMIT_EXCEEDED
    granted = evaluate(setup(), (request(),)).grants[0]
    assert granted.limits.within(LIMITS)


def test_unsupported_enforcement_and_isolation_prevent_grant() -> None:
    base = pipeline()
    plan = base[4]
    unsupported_fact = resource_fact(
        plan,
        enforcements=(SandboxFilesystemEnforcement.LIMITS,),
    )
    unsupported = evaluate(
        setup(facts=(unsupported_fact,), capability_inputs=base),
        (request(),),
    )
    assert (
        unsupported.denials[0].reason
        is SandboxFilesystemDenialReason.UNSUPPORTED_ENFORCEMENT
    )
    wrong_isolation = resource_fact(
        plan,
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    mismatch = evaluate(
        setup(facts=(wrong_isolation,), capability_inputs=base),
        (request(),),
    )
    assert mismatch.denials[0].reason is SandboxFilesystemDenialReason.MISMATCH


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.INCOMPLETE, SandboxFilesystemDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxFilesystemDenialReason.UNAVAILABLE),
    ],
)
def test_resource_completeness_is_explicit(completeness, reason) -> None:
    plan, capabilities, resources, filesystem_policy = setup()
    changed = SandboxFilesystemResourceSnapshot.create(
        observed_at=resources.observed_at,
        completeness=completeness,
        facts=resources.facts,
    )
    result = evaluate(
        (plan, capabilities, changed, filesystem_policy),
        (request(),),
    )
    assert result.denials[0].reason is reason


def test_stale_resource_fact_is_distinct() -> None:
    base = pipeline()
    plan = base[4]
    stale = resource_fact(
        plan,
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    result = evaluate(
        setup(facts=(stale,), capability_inputs=base),
        (request(),),
    )
    assert result.denials[0].reason is SandboxFilesystemDenialReason.STALE


def test_stale_capability_grant_cannot_support_filesystem_access() -> None:
    plan, grants, resources, filesystem_policy = setup()
    stale_grants = tuple(
        replace(
            item,
            valid_from=NOW - timedelta(hours=2),
            valid_until=NOW - timedelta(hours=1),
        )
        for item in grants.grants
    )
    stale_set = capability_grant_set_with(grants, grants=stale_grants)
    result = evaluate(
        (plan, stale_set, resources, filesystem_policy),
        (request(),),
    )
    assert result.denials[0].reason is SandboxFilesystemDenialReason.STALE


def test_output_policy_does_not_open_an_unlisted_workspace_root() -> None:
    base = pipeline()
    plan = base[4]
    output_fact = resource_fact(
        plan,
        SandboxFilesystemResource.OUTPUT,
        scope="scope:workspace",
    )
    fs_inputs = setup(
        rules=(rule(SandboxFilesystemResource.OUTPUT),),
        facts=(output_fact,),
        capability_inputs=base,
    )
    result = evaluate(fs_inputs, (request(),))
    assert result.denials[0].reason is SandboxFilesystemDenialReason.OPERATION_DENIED


def test_request_and_fact_order_do_not_change_result_or_fingerprint() -> None:
    base = pipeline()
    plan = base[4]
    workspace = resource_fact(plan)
    output = resource_fact(
        plan, SandboxFilesystemResource.OUTPUT, scope="scope:workspace"
    )
    rules = (
        rule(),
        rule(SandboxFilesystemResource.OUTPUT),
    )
    left_inputs = setup(
        rules=rules,
        facts=(workspace, output),
        capability_inputs=base,
    )
    right_inputs = setup(
        rules=tuple(reversed(rules)),
        facts=(output, workspace),
        capability_inputs=base,
    )
    requests = (
        request(),
        request(resource=SandboxFilesystemResource.OUTPUT, path="result.txt"),
    )
    left = evaluate(left_inputs, requests)
    right = evaluate(right_inputs, tuple(reversed(requests)))
    assert left == right


def test_specification_is_immutable_and_not_operational() -> None:
    grant_set = evaluate(setup(), (request(),))
    specification = SandboxFilesystemGrantService.build_specification(grant_set)
    assert specification.grants == grant_set.grants
    assert not hasattr(specification, "materialized")
    assert not hasattr(specification, "executable")
    assert not hasattr(specification, "apply")
    assert not hasattr(specification, "execute")
    with pytest.raises(FrozenInstanceError):
        specification.grants = ()  # type: ignore[misc]


def test_semantic_change_and_occurrence_replay_are_deterministic() -> None:
    fs_inputs = setup()
    first = evaluate(fs_inputs, (request(),))
    changed = evaluate(
        fs_inputs,
        (request(path="src/other.py"),),
    )
    replay = evaluate(fs_inputs, (request(),), occurred_at=NOW + timedelta(minutes=1))
    assert first.grant_set_fingerprint != changed.grant_set_fingerprint
    assert first.grant_set_id == replay.grant_set_id
    assert first.grant_set_fingerprint == replay.grant_set_fingerprint
    assert first.occurred_at != replay.occurred_at
