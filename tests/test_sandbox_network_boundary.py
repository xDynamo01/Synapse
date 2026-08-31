from dataclasses import FrozenInstanceError
from datetime import timedelta

import pytest

from synapse.sandbox import (
    FactCompleteness,
    InvalidNetworkBoundary,
    SandboxIsolationProfileId,
    SandboxNetworkDenialReason,
    SandboxNetworkDestination,
    SandboxNetworkDestinationKind,
    SandboxNetworkDirection,
    SandboxNetworkEnforcement,
    SandboxNetworkGrantService,
    SandboxNetworkLimits,
    SandboxNetworkOperation,
    SandboxNetworkPolicy,
    SandboxNetworkPolicyRule,
    SandboxNetworkPortRange,
    SandboxNetworkProtocol,
    SandboxNetworkRequest,
    SandboxNetworkResourceFact,
    SandboxNetworkResourceSnapshot,
    SandboxPolicyVersion,
)
from test_sandbox_admission_facts import NOW, ref
from test_sandbox_admission_policy import policy as admission_policy
from test_sandbox_capability_grants import evaluate as capability_evaluate
from test_sandbox_capability_grants import pipeline

LIMITS = SandboxNetworkLimits(4, 100_000, 200_000, 20, 20, 60, 10)
REQUEST_LIMITS = SandboxNetworkLimits(2, 10_000, 20_000, 5, 5, 30, 5)
ENFORCEMENTS = tuple(SandboxNetworkEnforcement)
HOST = SandboxNetworkDestination.hostname("api.example.com")
PORTS = SandboxNetworkPortRange(443, 443)


def policy_rule(
    *,
    destination=HOST,
    protocol=SandboxNetworkProtocol.HTTPS,
    operation=SandboxNetworkOperation.REQUEST,
    direction=SandboxNetworkDirection.OUTBOUND,
    ports=PORTS,
    purpose="workload-api",
    capability="python",
    limits=LIMITS,
    redirects=False,
    proxy=False,
    tls=True,
    local_classes=(),
    enforcements=ENFORCEMENTS,
):
    return SandboxNetworkPolicyRule(
        destination,
        (protocol,),
        (operation,),
        (direction,),
        ports,
        purpose,
        capability,
        limits,
        redirects,
        proxy,
        tls,
        local_classes,
        enforcements,
    )


def resource_fact(
    plan,
    *,
    destination=HOST,
    protocol=SandboxNetworkProtocol.HTTPS,
    operation=SandboxNetworkOperation.REQUEST,
    direction=SandboxNetworkDirection.OUTBOUND,
    ports=PORTS,
    purpose="workload-api",
    scope="scope:workspace",
    limits=LIMITS,
    redirects=False,
    proxy=False,
    tls=True,
    local_classes=(),
    enforcements=ENFORCEMENTS,
    isolation_profiles=None,
    valid_from=NOW - timedelta(hours=1),
    valid_until=NOW + timedelta(hours=1),
):
    return SandboxNetworkResourceFact(
        plan.plan_id,
        plan.plan_fingerprint,
        destination,
        (protocol,),
        (operation,),
        (direction,),
        ports,
        purpose,
        ref(scope),
        limits,
        redirects,
        proxy,
        tls,
        local_classes,
        enforcements,
        isolation_profiles or (plan.isolation_profile_id,),
        valid_from,
        valid_until,
    )


def setup(
    *,
    rules=None,
    facts=None,
    completeness=FactCompleteness.COMPLETE,
    selected_admission_policy=None,
    capability_inputs=None,
):
    inputs = capability_inputs or pipeline(admission_policy=selected_admission_policy)
    plan = inputs[4]
    capabilities = capability_evaluate(inputs)
    selected_rules = (policy_rule(),) if rules is None else rules
    selected_facts = (resource_fact(plan),) if facts is None else facts
    policy = SandboxNetworkPolicy.create(
        version=SandboxPolicyVersion("network-policy:v1"),
        plan=plan,
        rules=selected_rules,
    )
    resources = SandboxNetworkResourceSnapshot.create(
        observed_at=NOW,
        completeness=completeness,
        facts=selected_facts,
    )
    return plan, capabilities, resources, policy


def request(
    *,
    destination=HOST,
    protocol=SandboxNetworkProtocol.HTTPS,
    operation=SandboxNetworkOperation.REQUEST,
    direction=SandboxNetworkDirection.OUTBOUND,
    ports=PORTS,
    purpose="workload-api",
    limits=REQUEST_LIMITS,
    redirects=False,
    proxy=False,
    tls=True,
):
    return SandboxNetworkRequest(
        destination,
        protocol,
        operation,
        direction,
        ports,
        purpose,
        limits,
        redirects,
        proxy,
        tls,
    )


def evaluate(inputs, requests, *, evaluated_at=NOW, occurred_at=NOW):
    plan, capabilities, resources, policy = inputs
    return SandboxNetworkGrantService().evaluate(
        plan,
        capabilities,
        resources,
        policy,
        tuple(requests),
        evaluated_at=evaluated_at,
        occurred_at=occurred_at,
    )


def test_network_is_deny_by_default() -> None:
    plan, capabilities, resources, _ = setup()
    empty = SandboxNetworkPolicy.create(
        version=SandboxPolicyVersion("network-policy:empty"),
        plan=plan,
        rules=(),
    )
    result = evaluate((plan, capabilities, resources, empty), (request(),))
    assert not result.grants
    assert result.denials[0].reason is SandboxNetworkDenialReason.DESTINATION_DENIED


def test_hostname_is_not_an_ip_or_implicitly_resolved() -> None:
    hostname = SandboxNetworkDestination.hostname("Example.COM")
    address = SandboxNetworkDestination.ip("93.184.216.34")
    assert hostname.kind is SandboxNetworkDestinationKind.HOSTNAME
    assert hostname.value == "example.com"
    assert hostname.ip_version is None
    assert hostname != address


def test_exact_hostname_does_not_authorize_subdomain() -> None:
    subdomain = SandboxNetworkDestination.hostname("v2.api.example.com")
    result = evaluate(setup(), (request(destination=subdomain),))
    assert result.denials[0].reason is SandboxNetworkDenialReason.DESTINATION_DENIED


def test_redirect_requires_explicit_revalidation_support() -> None:
    result = evaluate(setup(), (request(redirects=True),))
    assert result.denials[0].reason is SandboxNetworkDenialReason.DESTINATION_DENIED
    assert "redirect.revalidation_required" in result.diagnostics


@pytest.mark.parametrize(
    ("protocol", "operation", "tls"),
    [
        (SandboxNetworkProtocol.DNS, SandboxNetworkOperation.DNS_QUERY, False),
        (SandboxNetworkProtocol.TCP, SandboxNetworkOperation.CONNECT, False),
        (SandboxNetworkProtocol.UDP, SandboxNetworkOperation.SEND, False),
        (SandboxNetworkProtocol.HTTP, SandboxNetworkOperation.REQUEST, False),
    ],
)
def test_https_grant_does_not_expand_to_other_protocols(protocol, operation, tls) -> None:
    result = evaluate(
        setup(),
        (request(protocol=protocol, operation=operation, tls=tls),),
    )
    assert result.denials[0].reason is SandboxNetworkDenialReason.PROTOCOL_DENIED


def test_connect_does_not_grant_bind_or_listen() -> None:
    destination = SandboxNetworkDestination.ip("8.8.8.8")
    tcp_rule = policy_rule(
        destination=destination,
        protocol=SandboxNetworkProtocol.TCP,
        operation=SandboxNetworkOperation.CONNECT,
        ports=SandboxNetworkPortRange(53, 53),
        tls=False,
    )
    base = pipeline()
    fact = resource_fact(
        base[4],
        destination=destination,
        protocol=SandboxNetworkProtocol.TCP,
        operation=SandboxNetworkOperation.CONNECT,
        ports=SandboxNetworkPortRange(53, 53),
        tls=False,
    )
    inputs = setup(rules=(tcp_rule,), facts=(fact,), capability_inputs=base)
    for operation in (SandboxNetworkOperation.BIND, SandboxNetworkOperation.LISTEN):
        result = evaluate(
            inputs,
            (
                request(
                    destination=destination,
                    protocol=SandboxNetworkProtocol.TCP,
                    operation=operation,
                    ports=SandboxNetworkPortRange(53, 53),
                    tls=False,
                ),
            ),
        )
        assert result.denials[0].reason is SandboxNetworkDenialReason.PROTOCOL_DENIED


def test_listen_requires_an_explicit_inbound_policy_and_fact() -> None:
    destination = SandboxNetworkDestination.ip("8.8.8.8")
    ports = SandboxNetworkPortRange(9000, 9000)
    base = pipeline()
    inputs = setup(
        rules=(
            policy_rule(
                destination=destination,
                protocol=SandboxNetworkProtocol.TCP,
                operation=SandboxNetworkOperation.LISTEN,
                direction=SandboxNetworkDirection.INBOUND,
                ports=ports,
                tls=False,
            ),
        ),
        facts=(
            resource_fact(
                base[4],
                destination=destination,
                protocol=SandboxNetworkProtocol.TCP,
                operation=SandboxNetworkOperation.LISTEN,
                direction=SandboxNetworkDirection.INBOUND,
                ports=ports,
                tls=False,
            ),
        ),
        capability_inputs=base,
    )
    result = evaluate(
        inputs,
        (
            request(
                destination=destination,
                protocol=SandboxNetworkProtocol.TCP,
                operation=SandboxNetworkOperation.LISTEN,
                direction=SandboxNetworkDirection.INBOUND,
                ports=ports,
                tls=False,
            ),
        ),
    )
    assert result.grants[0].operation is SandboxNetworkOperation.LISTEN
    assert result.grants[0].direction is SandboxNetworkDirection.INBOUND


def test_dns_grant_remains_only_a_dns_query_grant() -> None:
    destination = SandboxNetworkDestination.hostname("resolver.example.com")
    ports = SandboxNetworkPortRange(53, 53)
    base = pipeline()
    inputs = setup(
        rules=(
            policy_rule(
                destination=destination,
                protocol=SandboxNetworkProtocol.DNS,
                operation=SandboxNetworkOperation.DNS_QUERY,
                ports=ports,
                tls=False,
            ),
        ),
        facts=(
            resource_fact(
                base[4],
                destination=destination,
                protocol=SandboxNetworkProtocol.DNS,
                operation=SandboxNetworkOperation.DNS_QUERY,
                ports=ports,
                tls=False,
            ),
        ),
        capability_inputs=base,
    )
    grant = evaluate(
        inputs,
        (
            request(
                destination=destination,
                protocol=SandboxNetworkProtocol.DNS,
                operation=SandboxNetworkOperation.DNS_QUERY,
                ports=ports,
                tls=False,
            ),
        ),
    ).grants[0]
    assert grant.protocol is SandboxNetworkProtocol.DNS
    assert grant.operation is SandboxNetworkOperation.DNS_QUERY


@pytest.mark.parametrize(
    "destination",
    [
        SandboxNetworkDestination.ip("127.0.0.1"),
        SandboxNetworkDestination.ip("169.254.1.1"),
        SandboxNetworkDestination.ip("10.0.0.1"),
        SandboxNetworkDestination.ip("224.0.0.1"),
        SandboxNetworkDestination.ip("255.255.255.255"),
    ],
)
def test_local_network_classes_are_denied_without_explicit_grant(destination) -> None:
    local_rule = policy_rule(destination=destination)
    base = pipeline()
    fact = resource_fact(base[4], destination=destination)
    result = evaluate(
        setup(rules=(local_rule,), facts=(fact,), capability_inputs=base),
        (request(destination=destination),),
    )
    assert result.denials[0].reason is SandboxNetworkDenialReason.LOCAL_NETWORK_DENIED


def test_local_network_access_requires_explicit_policy_and_fact_classes() -> None:
    destination = SandboxNetworkDestination.ip("127.0.0.1")
    classes = destination.local_classes()
    base = pipeline()
    result = evaluate(
        setup(
            rules=(policy_rule(destination=destination, local_classes=classes),),
            facts=(
                resource_fact(
                    base[4],
                    destination=destination,
                    local_classes=classes,
                ),
            ),
            capability_inputs=base,
        ),
        (request(destination=destination),),
    )
    assert result.grants


def test_ipv4_does_not_authorize_ipv6() -> None:
    ipv6 = SandboxNetworkDestination.ip("2001:4860:4860::8888")
    result = evaluate(setup(), (request(destination=ipv6),))
    assert result.denials[0].reason is SandboxNetworkDenialReason.DESTINATION_DENIED


def test_wildcard_is_explicit_and_not_inferred_from_suffix() -> None:
    wildcard = SandboxNetworkDestination.wildcard("example.com")
    result = evaluate(setup(), (request(destination=wildcard),))
    assert result.denials[0].reason is SandboxNetworkDenialReason.WILDCARD_DENIED
    assert wildcard != SandboxNetworkDestination.hostname("api.example.com")


def test_capability_and_resource_fact_are_both_required() -> None:
    denied_inputs = setup(
        selected_admission_policy=admission_policy(allowed_capabilities=())
    )
    absent_capability = evaluate(denied_inputs, (request(),))
    assert (
        absent_capability.denials[0].reason
        is SandboxNetworkDenialReason.CAPABILITY_ABSENT
    )
    plan, capabilities, _, policy = setup()
    empty_resources = SandboxNetworkResourceSnapshot.create(
        observed_at=NOW,
        completeness=FactCompleteness.COMPLETE,
        facts=(),
    )
    absent_fact = evaluate(
        (plan, capabilities, empty_resources, policy),
        (request(),),
    )
    assert (
        absent_fact.denials[0].reason
        is SandboxNetworkDenialReason.RESOURCE_SCOPE_ABSENT
    )


def test_port_and_limits_never_expand() -> None:
    wide_port = evaluate(
        setup(),
        (request(ports=SandboxNetworkPortRange(443, 444)),),
    )
    assert wide_port.denials[0].reason is SandboxNetworkDenialReason.PORT_DENIED
    excessive = evaluate(
        setup(),
        (
            request(
                limits=SandboxNetworkLimits(
                    5, 100_001, 200_001, 21, 21, 61, 11
                )
            ),
        ),
    )
    assert excessive.denials[0].reason is SandboxNetworkDenialReason.LIMIT_EXCEEDED
    grant = evaluate(setup(), (request(),)).grants[0]
    assert grant.ports == PORTS
    assert grant.limits == REQUEST_LIMITS


def test_isolation_and_required_enforcement_fail_closed() -> None:
    base = pipeline()
    wrong_isolation = resource_fact(
        base[4],
        isolation_profiles=(SandboxIsolationProfileId("isolation:other"),),
    )
    mismatch = evaluate(
        setup(facts=(wrong_isolation,), capability_inputs=base),
        (request(),),
    )
    assert mismatch.denials[0].reason is SandboxNetworkDenialReason.MISMATCH
    unsupported = resource_fact(
        base[4],
        enforcements=(SandboxNetworkEnforcement.EXACT_DESTINATION,),
    )
    denial = evaluate(
        setup(facts=(unsupported,), capability_inputs=base),
        (request(),),
    )
    assert (
        denial.denials[0].reason
        is SandboxNetworkDenialReason.UNSUPPORTED_ENFORCEMENT
    )


@pytest.mark.parametrize(
    ("completeness", "reason"),
    [
        (FactCompleteness.INCOMPLETE, SandboxNetworkDenialReason.INCOMPLETE),
        (FactCompleteness.UNKNOWN, SandboxNetworkDenialReason.UNAVAILABLE),
    ],
)
def test_completeness_is_explicit(completeness, reason) -> None:
    result = evaluate(setup(completeness=completeness), (request(),))
    assert result.denials[0].reason is reason


def test_stale_fact_is_not_unavailable() -> None:
    base = pipeline()
    stale = resource_fact(
        base[4],
        valid_from=NOW - timedelta(hours=2),
        valid_until=NOW - timedelta(hours=1),
    )
    result = evaluate(
        setup(facts=(stale,), capability_inputs=base),
        (request(),),
    )
    assert result.denials[0].reason is SandboxNetworkDenialReason.STALE


def test_input_order_and_occurrence_do_not_change_semantic_identity() -> None:
    second = SandboxNetworkDestination.hostname("events.example.com")
    base = pipeline()
    rules = (policy_rule(), policy_rule(destination=second))
    facts = (
        resource_fact(base[4]),
        resource_fact(base[4], destination=second),
    )
    left = setup(rules=rules, facts=facts, capability_inputs=base)
    right = setup(
        rules=tuple(reversed(rules)),
        facts=tuple(reversed(facts)),
        capability_inputs=base,
    )
    requests = (request(), request(destination=second))
    first = evaluate(left, requests)
    replay = evaluate(
        right,
        tuple(reversed(requests)),
        occurred_at=NOW + timedelta(minutes=1),
    )
    assert first.grant_set_id == replay.grant_set_id
    assert first.grant_set_fingerprint == replay.grant_set_fingerprint
    assert first.occurred_at != replay.occurred_at


def test_specification_is_immutable_and_not_executable() -> None:
    grant_set = evaluate(setup(), (request(),))
    specification = SandboxNetworkGrantService.build_specification(grant_set)
    assert specification.grants == grant_set.grants
    assert not hasattr(specification, "executable")
    assert not hasattr(specification, "connect")
    assert not hasattr(specification, "send")
    with pytest.raises(FrozenInstanceError):
        specification.grants = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "factory_value",
    ["localhost", "*.example.com", "93.184.216.34", "bad..example.com"],
)
def test_hostname_validation_never_reinterprets_other_destination_kinds(
    factory_value,
) -> None:
    with pytest.raises(InvalidNetworkBoundary):
        SandboxNetworkDestination.hostname(factory_value)
