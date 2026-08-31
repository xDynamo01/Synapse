"""Deny-by-default network grant evaluation without network I/O."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .capability_grants import SandboxCapabilityGrantSet
from .errors import InvalidNetworkBoundary
from .execution_plan import SandboxExecutionPlan
from .facts import FactCompleteness, SandboxCapabilityScopeKind
from .identities import (
    OpaqueReference,
    SandboxArtifactFingerprint,
    SandboxIsolationProfileId,
    SandboxNetworkGrantSetId,
    SandboxNetworkPolicyId,
    SandboxPlanFingerprint,
    SandboxPlanId,
    SandboxPolicyVersion,
    derive_identity,
)

NETWORK_DESTINATION_FORMAT = "sandbox-network-destination-v1"
NETWORK_POLICY_FORMAT = "sandbox-network-policy-v1"
NETWORK_RESOURCE_FORMAT = "sandbox-network-resources-v1"
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PURPOSE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")


class SandboxNetworkProtocol(StrEnum):
    DNS = "dns"
    TCP = "tcp"
    UDP = "udp"
    HTTP = "http"
    HTTPS = "https"


class SandboxNetworkOperation(StrEnum):
    DNS_QUERY = "dns_query"
    CONNECT = "connect"
    SEND = "send"
    RECEIVE = "receive"
    REQUEST = "request"
    BIND = "bind"
    LISTEN = "listen"


class SandboxNetworkDirection(StrEnum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"


class SandboxNetworkDestinationKind(StrEnum):
    HOSTNAME = "hostname"
    IP = "ip"
    CIDR = "cidr"
    WILDCARD = "wildcard"


class SandboxNetworkLocalClass(StrEnum):
    LOOPBACK = "loopback"
    LINK_LOCAL = "link_local"
    PRIVATE = "private"
    MULTICAST = "multicast"
    BROADCAST = "broadcast"


class SandboxNetworkEnforcement(StrEnum):
    EXACT_DESTINATION = "exact_destination"
    DNS_REBINDING_PROTECTION = "dns_rebinding_protection"
    REDIRECT_REVALIDATION = "redirect_revalidation"
    PROXY_ISOLATION = "proxy_isolation"
    LOCAL_NETWORK_CLASSIFICATION = "local_network_classification"
    TLS_VALIDATION = "tls_validation"
    CONNECTION_LIMITS = "connection_limits"
    BYTE_LIMITS = "byte_limits"
    MESSAGE_LIMITS = "message_limits"
    TIME_LIMITS = "time_limits"


class SandboxNetworkDenialReason(StrEnum):
    CAPABILITY_ABSENT = "capability_absent"
    RESOURCE_SCOPE_ABSENT = "resource_scope_absent"
    DESTINATION_DENIED = "destination_denied"
    PROTOCOL_DENIED = "protocol_denied"
    DIRECTION_DENIED = "direction_denied"
    PORT_DENIED = "port_denied"
    WILDCARD_DENIED = "wildcard_denied"
    LOCAL_NETWORK_DENIED = "local_network_denied"
    UNSUPPORTED_ENFORCEMENT = "unsupported_enforcement"
    MISMATCH = "mismatch"
    STALE = "stale"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    LIMIT_EXCEEDED = "limit_exceeded"


@dataclass(frozen=True, slots=True)
class SandboxNetworkDestination:
    format_version: str
    kind: SandboxNetworkDestinationKind
    value: str
    ip_version: int | None

    @classmethod
    def hostname(cls, value: str) -> SandboxNetworkDestination:
        normalized = _normalize_hostname(value)
        return cls(
            NETWORK_DESTINATION_FORMAT,
            SandboxNetworkDestinationKind.HOSTNAME,
            normalized,
            None,
        )

    @classmethod
    def ip(cls, value: str) -> SandboxNetworkDestination:
        try:
            parsed = ipaddress.ip_address(value)
        except ValueError as exc:
            raise InvalidNetworkBoundary("destination.ip_invalid") from exc
        return cls(
            NETWORK_DESTINATION_FORMAT,
            SandboxNetworkDestinationKind.IP,
            parsed.compressed,
            parsed.version,
        )

    @classmethod
    def cidr(cls, value: str) -> SandboxNetworkDestination:
        try:
            parsed = ipaddress.ip_network(value, strict=True)
        except ValueError as exc:
            raise InvalidNetworkBoundary("destination.cidr_invalid") from exc
        return cls(
            NETWORK_DESTINATION_FORMAT,
            SandboxNetworkDestinationKind.CIDR,
            parsed.with_prefixlen,
            parsed.version,
        )

    @classmethod
    def wildcard(cls, suffix: str) -> SandboxNetworkDestination:
        normalized = _normalize_hostname(suffix)
        return cls(
            NETWORK_DESTINATION_FORMAT,
            SandboxNetworkDestinationKind.WILDCARD,
            f"*.{normalized}",
            None,
        )

    def __post_init__(self) -> None:
        if self.format_version != NETWORK_DESTINATION_FORMAT:
            raise InvalidNetworkBoundary("destination.format_unsupported")
        if self.kind is SandboxNetworkDestinationKind.HOSTNAME:
            if self.value != _normalize_hostname(self.value) or self.ip_version is not None:
                raise InvalidNetworkBoundary("destination.hostname_invalid")
        elif self.kind is SandboxNetworkDestinationKind.WILDCARD:
            if (
                not self.value.startswith("*.")
                or self.value[2:] != _normalize_hostname(self.value[2:])
                or self.ip_version is not None
            ):
                raise InvalidNetworkBoundary("destination.wildcard_invalid")
        elif self.kind is SandboxNetworkDestinationKind.IP:
            try:
                parsed_ip = ipaddress.ip_address(self.value)
            except ValueError as exc:
                raise InvalidNetworkBoundary("destination.ip_invalid") from exc
            if parsed_ip.compressed != self.value or parsed_ip.version != self.ip_version:
                raise InvalidNetworkBoundary("destination.ip_not_canonical")
        else:
            try:
                parsed_network = ipaddress.ip_network(self.value, strict=True)
            except ValueError as exc:
                raise InvalidNetworkBoundary("destination.cidr_invalid") from exc
            if (
                parsed_network.with_prefixlen != self.value
                or parsed_network.version != self.ip_version
            ):
                raise InvalidNetworkBoundary("destination.cidr_not_canonical")

    def local_classes(self) -> tuple[SandboxNetworkLocalClass, ...]:
        if self.kind not in {
            SandboxNetworkDestinationKind.IP,
            SandboxNetworkDestinationKind.CIDR,
        }:
            return ()
        parsed = (
            ipaddress.ip_address(self.value)
            if self.kind is SandboxNetworkDestinationKind.IP
            else ipaddress.ip_network(self.value, strict=True)
        )
        classes: set[SandboxNetworkLocalClass] = set()
        if parsed.is_loopback:
            classes.add(SandboxNetworkLocalClass.LOOPBACK)
        if parsed.is_link_local:
            classes.add(SandboxNetworkLocalClass.LINK_LOCAL)
        if parsed.is_private:
            classes.add(SandboxNetworkLocalClass.PRIVATE)
        if parsed.is_multicast:
            classes.add(SandboxNetworkLocalClass.MULTICAST)
        if (
            self.kind is SandboxNetworkDestinationKind.IP
            and self.ip_version == 4
            and self.value == "255.255.255.255"
        ):
            classes.add(SandboxNetworkLocalClass.BROADCAST)
        return tuple(sorted(classes, key=lambda item: item.value))


def _normalize_hostname(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 253:
        raise InvalidNetworkBoundary("destination.hostname_invalid")
    if value.endswith(".") or value.startswith(".") or "*" in value:
        raise InvalidNetworkBoundary("destination.hostname_invalid")
    normalized = value.casefold()
    labels = normalized.split(".")
    if len(labels) < 2 or any(not _HOST_LABEL.fullmatch(label) for label in labels):
        raise InvalidNetworkBoundary("destination.hostname_invalid")
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        return normalized
    raise InvalidNetworkBoundary("destination.hostname_is_ip")


@dataclass(frozen=True, slots=True)
class SandboxNetworkPortRange:
    first: int
    last: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.first, int)
            or isinstance(self.first, bool)
            or not isinstance(self.last, int)
            or isinstance(self.last, bool)
            or not 1 <= self.first <= self.last <= 65535
        ):
            raise InvalidNetworkBoundary("port_range.invalid")

    def within(self, other: SandboxNetworkPortRange) -> bool:
        return other.first <= self.first and self.last <= other.last


@dataclass(frozen=True, slots=True)
class SandboxNetworkLimits:
    maximum_connections: int
    maximum_bytes_sent: int
    maximum_bytes_received: int
    maximum_requests: int
    maximum_responses: int
    maximum_duration_seconds: int
    idle_timeout_seconds: int

    def __post_init__(self) -> None:
        values = (
            self.maximum_connections,
            self.maximum_bytes_sent,
            self.maximum_bytes_received,
            self.maximum_requests,
            self.maximum_responses,
            self.maximum_duration_seconds,
            self.idle_timeout_seconds,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value <= 0 for value in values
        ):
            raise InvalidNetworkBoundary("limits.must_be_positive")
        if self.idle_timeout_seconds > self.maximum_duration_seconds:
            raise InvalidNetworkBoundary("limits.idle_exceeds_duration")

    def within(self, other: SandboxNetworkLimits) -> bool:
        return all(
            current <= maximum
            for current, maximum in zip(
                (
                    self.maximum_connections,
                    self.maximum_bytes_sent,
                    self.maximum_bytes_received,
                    self.maximum_requests,
                    self.maximum_responses,
                    self.maximum_duration_seconds,
                    self.idle_timeout_seconds,
                ),
                (
                    other.maximum_connections,
                    other.maximum_bytes_sent,
                    other.maximum_bytes_received,
                    other.maximum_requests,
                    other.maximum_responses,
                    other.maximum_duration_seconds,
                    other.idle_timeout_seconds,
                ),
                strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class SandboxNetworkRequest:
    destination: SandboxNetworkDestination
    protocol: SandboxNetworkProtocol
    operation: SandboxNetworkOperation
    direction: SandboxNetworkDirection
    ports: SandboxNetworkPortRange
    purpose: str
    limits: SandboxNetworkLimits
    allow_redirects: bool
    allow_proxy_inheritance: bool
    require_tls: bool

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, str) or not _PURPOSE.fullmatch(self.purpose):
            raise InvalidNetworkBoundary("request.purpose_invalid")
        if not _operation_supported(self.protocol, self.operation):
            raise InvalidNetworkBoundary("request.protocol_operation_invalid")
        if self.protocol is SandboxNetworkProtocol.HTTPS and not self.require_tls:
            raise InvalidNetworkBoundary("request.https_requires_tls")


@dataclass(frozen=True, slots=True)
class SandboxNetworkPolicyRule:
    destination: SandboxNetworkDestination
    protocols: tuple[SandboxNetworkProtocol, ...]
    operations: tuple[SandboxNetworkOperation, ...]
    directions: tuple[SandboxNetworkDirection, ...]
    ports: SandboxNetworkPortRange
    purpose: str
    capability: str
    limits: SandboxNetworkLimits
    allow_redirects: bool
    allow_proxy_inheritance: bool
    require_tls: bool
    allowed_local_classes: tuple[SandboxNetworkLocalClass, ...]
    required_enforcements: tuple[SandboxNetworkEnforcement, ...]

    def __post_init__(self) -> None:
        if not self.protocols or not self.operations or not self.directions:
            raise InvalidNetworkBoundary("policy.rule_incomplete")
        if not _PURPOSE.fullmatch(self.purpose) or not self.capability:
            raise InvalidNetworkBoundary("policy.rule_identity_invalid")
        if any(
            not any(_operation_supported(protocol, operation) for protocol in self.protocols)
            for operation in self.operations
        ):
            raise InvalidNetworkBoundary("policy.protocol_operation_invalid")
        if SandboxNetworkProtocol.HTTPS in self.protocols and not self.require_tls:
            raise InvalidNetworkBoundary("policy.https_requires_tls")
        required = _baseline_enforcements(
            self.destination,
            allow_redirects=self.allow_redirects,
            require_tls=self.require_tls,
        )
        if not required <= set(self.required_enforcements):
            raise InvalidNetworkBoundary("policy.enforcement_requirements_incomplete")
        for name in ("protocols", "operations", "directions"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise InvalidNetworkBoundary(f"policy.{name}_conflict")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda item: item.value)))
        object.__setattr__(
            self,
            "allowed_local_classes",
            tuple(sorted(set(self.allowed_local_classes), key=lambda item: item.value)),
        )
        object.__setattr__(
            self,
            "required_enforcements",
            tuple(sorted(set(self.required_enforcements), key=lambda item: item.value)),
        )


@dataclass(frozen=True, slots=True)
class SandboxNetworkPolicy:
    format_version: str
    policy_id: SandboxNetworkPolicyId
    version: SandboxPolicyVersion
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    rules: tuple[SandboxNetworkPolicyRule, ...]
    policy_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.format_version,
            self.version,
            self.plan_id,
            self.plan_fingerprint,
            self.rules,
        )

    @classmethod
    def create(
        cls,
        *,
        version: SandboxPolicyVersion,
        plan: SandboxExecutionPlan,
        rules: tuple[SandboxNetworkPolicyRule, ...],
    ) -> SandboxNetworkPolicy:
        ordered = tuple(sorted(rules, key=repr))
        content = (
            NETWORK_POLICY_FORMAT,
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            ordered,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxNetworkPolicyId, fingerprint)
        return cls(
            NETWORK_POLICY_FORMAT,
            SandboxNetworkPolicyId(identity.value),
            version,
            plan.plan_id,
            plan.plan_fingerprint,
            ordered,
            fingerprint,
        )

    def __post_init__(self) -> None:
        if self.format_version != NETWORK_POLICY_FORMAT:
            raise InvalidNetworkBoundary("policy.format_unsupported")
        if len(set(self.rules)) != len(self.rules):
            raise InvalidNetworkBoundary("policy.rules_conflict")
        if self.rules != tuple(sorted(self.rules, key=repr)):
            raise InvalidNetworkBoundary("policy.rules_not_canonical")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.policy_fingerprint:
            raise InvalidNetworkBoundary("policy.fingerprint_mismatch")
        if derive_identity(SandboxNetworkPolicyId, expected) != self.policy_id:
            raise InvalidNetworkBoundary("policy.identity_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxNetworkResourceFact:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    destination: SandboxNetworkDestination
    protocols: tuple[SandboxNetworkProtocol, ...]
    operations: tuple[SandboxNetworkOperation, ...]
    directions: tuple[SandboxNetworkDirection, ...]
    ports: SandboxNetworkPortRange
    purpose: str
    scope_ref: OpaqueReference
    limits: SandboxNetworkLimits
    allow_redirects: bool
    allow_proxy_inheritance: bool
    tls_supported: bool
    allowed_local_classes: tuple[SandboxNetworkLocalClass, ...]
    supported_enforcements: tuple[SandboxNetworkEnforcement, ...]
    isolation_profiles: tuple[SandboxIsolationProfileId, ...]
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if (
            self.valid_from.tzinfo is None
            or self.valid_from.utcoffset() is None
            or self.valid_until.tzinfo is None
            or self.valid_until.utcoffset() is None
            or self.valid_until < self.valid_from
        ):
            raise InvalidNetworkBoundary("resource_fact.validity_invalid")
        if not _PURPOSE.fullmatch(self.purpose):
            raise InvalidNetworkBoundary("resource_fact.purpose_invalid")
        if any(
            not any(_operation_supported(protocol, operation) for protocol in self.protocols)
            for operation in self.operations
        ):
            raise InvalidNetworkBoundary("resource_fact.protocol_operation_invalid")
        for name in ("protocols", "operations", "directions"):
            values = getattr(self, name)
            if len(set(values)) != len(values):
                raise InvalidNetworkBoundary(f"resource_fact.{name}_conflict")
            object.__setattr__(self, name, tuple(sorted(values, key=lambda item: item.value)))
        for name in (
            "allowed_local_classes",
            "supported_enforcements",
            "isolation_profiles",
        ):
            values = getattr(self, name)
            object.__setattr__(self, name, tuple(sorted(set(values), key=lambda item: item.value)))


def _operation_supported(
    protocol: SandboxNetworkProtocol,
    operation: SandboxNetworkOperation,
) -> bool:
    supported = {
        SandboxNetworkProtocol.DNS: {SandboxNetworkOperation.DNS_QUERY},
        SandboxNetworkProtocol.TCP: {
            SandboxNetworkOperation.CONNECT,
            SandboxNetworkOperation.BIND,
            SandboxNetworkOperation.LISTEN,
        },
        SandboxNetworkProtocol.UDP: {
            SandboxNetworkOperation.SEND,
            SandboxNetworkOperation.RECEIVE,
            SandboxNetworkOperation.BIND,
            SandboxNetworkOperation.LISTEN,
        },
        SandboxNetworkProtocol.HTTP: {SandboxNetworkOperation.REQUEST},
        SandboxNetworkProtocol.HTTPS: {SandboxNetworkOperation.REQUEST},
    }
    return operation in supported[protocol]


def _baseline_enforcements(
    destination: SandboxNetworkDestination,
    *,
    allow_redirects: bool,
    require_tls: bool,
) -> set[SandboxNetworkEnforcement]:
    required = {
        SandboxNetworkEnforcement.EXACT_DESTINATION,
        SandboxNetworkEnforcement.PROXY_ISOLATION,
        SandboxNetworkEnforcement.CONNECTION_LIMITS,
        SandboxNetworkEnforcement.BYTE_LIMITS,
        SandboxNetworkEnforcement.MESSAGE_LIMITS,
        SandboxNetworkEnforcement.TIME_LIMITS,
    }
    if destination.kind in {
        SandboxNetworkDestinationKind.HOSTNAME,
        SandboxNetworkDestinationKind.WILDCARD,
    }:
        required.add(SandboxNetworkEnforcement.DNS_REBINDING_PROTECTION)
    if destination.kind in {
        SandboxNetworkDestinationKind.IP,
        SandboxNetworkDestinationKind.CIDR,
    }:
        required.add(SandboxNetworkEnforcement.LOCAL_NETWORK_CLASSIFICATION)
    if allow_redirects:
        required.add(SandboxNetworkEnforcement.REDIRECT_REVALIDATION)
    if require_tls:
        required.add(SandboxNetworkEnforcement.TLS_VALIDATION)
    return required


@dataclass(frozen=True, slots=True)
class SandboxNetworkResourceSnapshot:
    format_version: str
    observed_at: datetime
    completeness: FactCompleteness
    facts: tuple[SandboxNetworkResourceFact, ...]
    resource_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (self.format_version, self.observed_at, self.completeness, self.facts)

    @classmethod
    def create(
        cls,
        *,
        observed_at: datetime,
        completeness: FactCompleteness,
        facts: tuple[SandboxNetworkResourceFact, ...],
    ) -> SandboxNetworkResourceSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise InvalidNetworkBoundary("resource_snapshot.observed_at_invalid")
        ordered = tuple(sorted(facts, key=repr))
        content = (NETWORK_RESOURCE_FORMAT, observed_at, completeness, ordered)
        return cls(
            NETWORK_RESOURCE_FORMAT,
            observed_at,
            completeness,
            ordered,
            SandboxArtifactFingerprint.from_content(content),
        )

    def __post_init__(self) -> None:
        if self.format_version != NETWORK_RESOURCE_FORMAT:
            raise InvalidNetworkBoundary("resource_snapshot.format_unsupported")
        if self.facts != tuple(sorted(self.facts, key=repr)):
            raise InvalidNetworkBoundary("resource_snapshot.facts_not_canonical")
        if SandboxArtifactFingerprint.from_content(self.content()) != self.resource_fingerprint:
            raise InvalidNetworkBoundary("resource_snapshot.fingerprint_mismatch")


@dataclass(frozen=True, slots=True)
class SandboxNetworkGrant:
    destination: SandboxNetworkDestination
    protocol: SandboxNetworkProtocol
    operation: SandboxNetworkOperation
    direction: SandboxNetworkDirection
    ports: SandboxNetworkPortRange
    purpose: str
    limits: SandboxNetworkLimits
    scope_ref: OpaqueReference
    allow_redirects: bool
    allow_proxy_inheritance: bool
    require_tls: bool
    required_enforcements: tuple[SandboxNetworkEnforcement, ...]
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.required_enforcements != tuple(
            sorted(set(self.required_enforcements), key=lambda item: item.value)
        ):
            raise InvalidNetworkBoundary("grant.enforcements_not_canonical")
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidNetworkBoundary("grant.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxNetworkDenial:
    destination_kind: SandboxNetworkDestinationKind
    protocol: SandboxNetworkProtocol
    operation: SandboxNetworkOperation
    reason: SandboxNetworkDenialReason
    rationale_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.rationale_codes != tuple(sorted(set(self.rationale_codes))):
            raise InvalidNetworkBoundary("denial.rationale_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxNetworkGrantSet:
    grant_set_id: SandboxNetworkGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    request_fingerprint: SandboxArtifactFingerprint
    capability_grant_set_fingerprint: SandboxArtifactFingerprint
    policy_id: SandboxNetworkPolicyId
    policy_fingerprint: SandboxArtifactFingerprint
    resource_snapshot_fingerprint: SandboxArtifactFingerprint
    evaluated_at: datetime
    grants: tuple[SandboxNetworkGrant, ...]
    denials: tuple[SandboxNetworkDenial, ...]
    diagnostics: tuple[str, ...]
    occurred_at: datetime

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.request_fingerprint,
            self.capability_grant_set_fingerprint,
            self.policy_id,
            self.policy_fingerprint,
            self.resource_snapshot_fingerprint,
            self.evaluated_at,
            self.grants,
            self.denials,
            self.diagnostics,
        )

    def __post_init__(self) -> None:
        if (
            self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() is None
            or self.occurred_at.tzinfo is None
            or self.occurred_at.utcoffset() is None
        ):
            raise InvalidNetworkBoundary("grant_set.timestamp_invalid")
        expected = SandboxArtifactFingerprint.from_content(self.content())
        if expected != self.grant_set_fingerprint:
            raise InvalidNetworkBoundary("grant_set.fingerprint_mismatch")
        if derive_identity(SandboxNetworkGrantSetId, expected) != self.grant_set_id:
            raise InvalidNetworkBoundary("grant_set.identity_mismatch")
        if self.grants != tuple(sorted(self.grants, key=repr)):
            raise InvalidNetworkBoundary("grant_set.grants_not_canonical")
        if self.denials != tuple(sorted(self.denials, key=repr)):
            raise InvalidNetworkBoundary("grant_set.denials_not_canonical")
        if self.diagnostics != tuple(sorted(set(self.diagnostics))):
            raise InvalidNetworkBoundary("grant_set.diagnostics_not_canonical")


@dataclass(frozen=True, slots=True)
class SandboxNetworkSpecification:
    plan_id: SandboxPlanId
    plan_fingerprint: SandboxPlanFingerprint
    grant_set_id: SandboxNetworkGrantSetId
    grant_set_fingerprint: SandboxArtifactFingerprint
    grants: tuple[SandboxNetworkGrant, ...]
    required_enforcements: tuple[SandboxNetworkEnforcement, ...]
    specification_fingerprint: SandboxArtifactFingerprint

    def content(self) -> tuple[object, ...]:
        return (
            self.plan_id,
            self.plan_fingerprint,
            self.grant_set_id,
            self.grant_set_fingerprint,
            self.grants,
            self.required_enforcements,
        )

    def __post_init__(self) -> None:
        if self.required_enforcements != tuple(
            sorted(set(self.required_enforcements), key=lambda item: item.value)
        ):
            raise InvalidNetworkBoundary("specification.enforcements_not_canonical")
        if (
            SandboxArtifactFingerprint.from_content(self.content())
            != self.specification_fingerprint
        ):
            raise InvalidNetworkBoundary("specification.fingerprint_mismatch")


class SandboxNetworkGrantService:
    """Evaluate declared network facts without resolving or contacting destinations."""

    def evaluate(
        self,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxNetworkResourceSnapshot,
        policy: SandboxNetworkPolicy,
        requests: tuple[SandboxNetworkRequest, ...],
        *,
        evaluated_at: datetime,
        occurred_at: datetime,
    ) -> SandboxNetworkGrantSet:
        self._validate_bindings(plan, capabilities, policy)
        if (
            evaluated_at.tzinfo is None
            or evaluated_at.utcoffset() is None
            or occurred_at.tzinfo is None
            or occurred_at.utcoffset() is None
        ):
            raise InvalidNetworkBoundary("grant_set.timestamp_invalid")
        ordered_requests = tuple(sorted(requests, key=repr))
        request_fingerprint = SandboxArtifactFingerprint.from_content(
            (plan.plan_id, plan.plan_fingerprint, ordered_requests)
        )
        grants: list[SandboxNetworkGrant] = []
        denials: list[SandboxNetworkDenial] = []
        for request in ordered_requests:
            grant, denial = self._evaluate_request(
                plan,
                capabilities,
                resources,
                policy,
                request,
                evaluated_at,
            )
            if grant is not None:
                grants.append(grant)
            if denial is not None:
                denials.append(denial)
        ordered_grants = tuple(sorted(grants, key=repr))
        ordered_denials = tuple(sorted(denials, key=repr))
        diagnostics = tuple(
            sorted({code for denial in ordered_denials for code in denial.rationale_codes})
        )
        content = (
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            resources.resource_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
        )
        fingerprint = SandboxArtifactFingerprint.from_content(content)
        identity = derive_identity(SandboxNetworkGrantSetId, fingerprint)
        return SandboxNetworkGrantSet(
            SandboxNetworkGrantSetId(identity.value),
            fingerprint,
            plan.plan_id,
            plan.plan_fingerprint,
            request_fingerprint,
            capabilities.grant_set_fingerprint,
            policy.policy_id,
            policy.policy_fingerprint,
            resources.resource_fingerprint,
            evaluated_at,
            ordered_grants,
            ordered_denials,
            diagnostics,
            occurred_at,
        )

    @staticmethod
    def build_specification(
        grant_set: SandboxNetworkGrantSet,
    ) -> SandboxNetworkSpecification:
        enforcements = tuple(
            sorted(
                {
                    enforcement
                    for grant in grant_set.grants
                    for enforcement in grant.required_enforcements
                },
                key=lambda item: item.value,
            )
        )
        content = (
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.grants,
            enforcements,
        )
        return SandboxNetworkSpecification(
            grant_set.plan_id,
            grant_set.plan_fingerprint,
            grant_set.grant_set_id,
            grant_set.grant_set_fingerprint,
            grant_set.grants,
            enforcements,
            SandboxArtifactFingerprint.from_content(content),
        )

    @staticmethod
    def _validate_bindings(
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        policy: SandboxNetworkPolicy,
    ) -> None:
        diagnostics = []
        if capabilities.plan_id != plan.plan_id:
            diagnostics.append("binding.capability_plan_identity_mismatch")
        if capabilities.plan_fingerprint != plan.plan_fingerprint:
            diagnostics.append("binding.capability_plan_fingerprint_mismatch")
        if policy.plan_id != plan.plan_id:
            diagnostics.append("binding.policy_plan_identity_mismatch")
        if policy.plan_fingerprint != plan.plan_fingerprint:
            diagnostics.append("binding.policy_plan_fingerprint_mismatch")
        if diagnostics:
            raise InvalidNetworkBoundary(",".join(sorted(diagnostics)))

    @classmethod
    def _evaluate_request(
        cls,
        plan: SandboxExecutionPlan,
        capabilities: SandboxCapabilityGrantSet,
        resources: SandboxNetworkResourceSnapshot,
        policy: SandboxNetworkPolicy,
        request: SandboxNetworkRequest,
        evaluated_at: datetime,
    ) -> tuple[SandboxNetworkGrant | None, SandboxNetworkDenial | None]:
        if resources.completeness is FactCompleteness.INCOMPLETE:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.INCOMPLETE, "resources.incomplete"
            )
        if resources.completeness is not FactCompleteness.COMPLETE:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.UNAVAILABLE, "resources.unavailable"
            )
        candidates = [rule for rule in policy.rules if rule.destination == request.destination]
        if not candidates:
            reason = (
                SandboxNetworkDenialReason.WILDCARD_DENIED
                if request.destination.kind is SandboxNetworkDestinationKind.WILDCARD
                else SandboxNetworkDenialReason.DESTINATION_DENIED
            )
            return None, cls._denial(request, reason, "policy.destination_denied")
        if len(candidates) != 1:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.MISMATCH, "policy.rules_conflict"
            )
        rule = candidates[0]
        if request.protocol not in rule.protocols:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PROTOCOL_DENIED, "policy.protocol_denied"
            )
        if request.operation not in rule.operations:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PROTOCOL_DENIED, "policy.operation_denied"
            )
        if request.direction not in rule.directions:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.DIRECTION_DENIED, "policy.direction_denied"
            )
        if not request.ports.within(rule.ports):
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PORT_DENIED, "policy.port_denied"
            )
        if request.purpose != rule.purpose:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.MISMATCH, "policy.purpose_mismatch"
            )
        if request.allow_redirects and not rule.allow_redirects:
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.DESTINATION_DENIED,
                "redirect.revalidation_required",
            )
        if request.allow_proxy_inheritance and not rule.allow_proxy_inheritance:
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.UNSUPPORTED_ENFORCEMENT,
                "proxy.inheritance_denied",
            )
        if request.require_tls and not rule.require_tls:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PROTOCOL_DENIED, "tls.policy_required"
            )
        if not request.limits.within(rule.limits):
            return None, cls._denial(
                request, SandboxNetworkDenialReason.LIMIT_EXCEEDED, "policy.limits_exceeded"
            )
        local_classes = set(request.destination.local_classes())
        if not local_classes <= set(rule.allowed_local_classes):
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.LOCAL_NETWORK_DENIED,
                "policy.local_network_denied",
            )
        facts = [fact for fact in resources.facts if fact.destination == request.destination]
        if len(facts) != 1:
            reason = (
                SandboxNetworkDenialReason.RESOURCE_SCOPE_ABSENT
                if not facts
                else SandboxNetworkDenialReason.MISMATCH
            )
            return None, cls._denial(request, reason, "resource.correspondence")
        fact = facts[0]
        mismatch = (
            fact.plan_id != plan.plan_id
            or fact.plan_fingerprint != plan.plan_fingerprint
            or fact.purpose != request.purpose
            or plan.isolation_profile_id not in fact.isolation_profiles
        )
        if mismatch:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.MISMATCH, "resource.binding_mismatch"
            )
        if not fact.valid_from <= evaluated_at <= fact.valid_until:
            return None, cls._denial(request, SandboxNetworkDenialReason.STALE, "resource.stale")
        if request.protocol not in fact.protocols:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PROTOCOL_DENIED, "resource.protocol_denied"
            )
        if request.operation not in fact.operations:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PROTOCOL_DENIED, "resource.operation_denied"
            )
        if request.direction not in fact.directions:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.DIRECTION_DENIED, "resource.direction_denied"
            )
        if not request.ports.within(fact.ports):
            return None, cls._denial(
                request, SandboxNetworkDenialReason.PORT_DENIED, "resource.port_denied"
            )
        if not request.limits.within(fact.limits):
            return None, cls._denial(
                request, SandboxNetworkDenialReason.LIMIT_EXCEEDED, "resource.limits_exceeded"
            )
        if request.allow_redirects and not fact.allow_redirects:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.DESTINATION_DENIED, "resource.redirect_denied"
            )
        if request.allow_proxy_inheritance and not fact.allow_proxy_inheritance:
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.UNSUPPORTED_ENFORCEMENT,
                "resource.proxy_unsupported",
            )
        if request.require_tls and not fact.tls_supported:
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.UNSUPPORTED_ENFORCEMENT,
                "resource.tls_unsupported",
            )
        if not local_classes <= set(fact.allowed_local_classes):
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.LOCAL_NETWORK_DENIED,
                "resource.local_network_denied",
            )
        if not set(rule.required_enforcements) <= set(fact.supported_enforcements):
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.UNSUPPORTED_ENFORCEMENT,
                "resource.enforcement_unsupported",
            )
        capability = next(
            (grant for grant in capabilities.grants if grant.capability == rule.capability),
            None,
        )
        if capability is None:
            return None, cls._denial(
                request, SandboxNetworkDenialReason.CAPABILITY_ABSENT, "capability.absent"
            )
        if not capability.valid_from <= evaluated_at <= capability.valid_until:
            return None, cls._denial(request, SandboxNetworkDenialReason.STALE, "capability.stale")
        if not any(
            scope.kind is SandboxCapabilityScopeKind.WILDCARD or scope.reference == fact.scope_ref
            for scope in capability.scopes
        ):
            return None, cls._denial(
                request,
                SandboxNetworkDenialReason.RESOURCE_SCOPE_ABSENT,
                "capability.resource_scope_absent",
            )
        return (
            SandboxNetworkGrant(
                request.destination,
                request.protocol,
                request.operation,
                request.direction,
                request.ports,
                request.purpose,
                request.limits,
                fact.scope_ref,
                request.allow_redirects,
                request.allow_proxy_inheritance,
                request.require_tls,
                rule.required_enforcements,
                ("network.intersection_satisfied",),
            ),
            None,
        )

    @staticmethod
    def _denial(
        request: SandboxNetworkRequest,
        reason: SandboxNetworkDenialReason,
        code: str,
    ) -> SandboxNetworkDenial:
        return SandboxNetworkDenial(
            request.destination.kind,
            request.protocol,
            request.operation,
            reason,
            (code,),
        )
