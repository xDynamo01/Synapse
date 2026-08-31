"""Factual Windows Job Object resource-limit enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from synapse.sandbox import SandboxResourceDimension, SandboxResourceGrant

MAX_SIGNED_64 = (1 << 63) - 1


class WindowsJobResourceDimension(StrEnum):
    PROCESS_COUNT = "process_count"
    PROCESS_MEMORY = "process_memory"
    JOB_MEMORY = "job_memory"
    PROCESS_CPU_TIME = "process_cpu_time"
    JOB_CPU_TIME = "job_cpu_time"
    CPU_RATE = "cpu_rate"


class WindowsResourceCapabilityState(StrEnum):
    SUPPORTED = "supported"
    CONFIGURABLE = "configurable"
    ENFORCED = "enforced"
    OBSERVABLE_ONLY = "observable_only"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class WindowsResourceCapability:
    dimension: WindowsJobResourceDimension
    state: WindowsResourceCapabilityState
    observable: bool


@dataclass(frozen=True, slots=True)
class WindowsJobResourceRequirement:
    dimension: WindowsJobResourceDimension
    requested: int
    granted: int
    required: bool

    def __post_init__(self) -> None:
        for value in (self.requested, self.granted):
            if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_SIGNED_64:
                raise ValueError("resource_policy_invalid")
        if self.dimension is WindowsJobResourceDimension.CPU_RATE:
            if self.requested > 10_000 or self.granted > 10_000:
                raise ValueError("resource_policy_invalid")


@dataclass(frozen=True, slots=True)
class WindowsJobResourcePolicyV1:
    requirements: tuple[WindowsJobResourceRequirement, ...]

    def __post_init__(self) -> None:
        canonical = tuple(sorted(self.requirements, key=lambda item: item.dimension.value))
        if self.requirements != canonical or len({item.dimension for item in canonical}) != len(canonical):
            raise ValueError("resource_policy_invalid")

    @classmethod
    def from_sandbox_grants(
        cls,
        grants: tuple[SandboxResourceGrant, ...],
        *,
        optional_dimensions: frozenset[WindowsJobResourceDimension] = frozenset(),
    ) -> WindowsJobResourcePolicyV1:
        mapping = {
            SandboxResourceDimension.PROCESS_COUNT: WindowsJobResourceDimension.PROCESS_COUNT,
            SandboxResourceDimension.MEMORY_WORKING_SET: WindowsJobResourceDimension.PROCESS_MEMORY,
            SandboxResourceDimension.MEMORY_COMMIT: WindowsJobResourceDimension.JOB_MEMORY,
            SandboxResourceDimension.CPU_TIME: WindowsJobResourceDimension.JOB_CPU_TIME,
            SandboxResourceDimension.CPU_QUOTA: WindowsJobResourceDimension.CPU_RATE,
        }
        requirements: list[WindowsJobResourceRequirement] = []
        for grant in grants:
            dimension = mapping.get(grant.effective.dimension)
            if dimension is None or grant.effective.unlimited:
                continue
            requested = grant.requested.hard
            effective = grant.effective.hard
            if requested is None or effective is None:
                raise ValueError("resource_policy_invalid")
            if dimension is WindowsJobResourceDimension.CPU_RATE:
                if requested % 100 or effective % 100:
                    raise ValueError("resource_policy_invalid")
                requested //= 100
                effective //= 100
            requirements.append(
                WindowsJobResourceRequirement(
                    dimension,
                    requested,
                    effective,
                    dimension not in optional_dimensions,
                )
            )
        return cls(tuple(sorted(requirements, key=lambda item: item.dimension.value)))


@dataclass(frozen=True, slots=True)
class WindowsNativeJobLimits:
    active_process_limit: int | None = None
    process_memory_bytes: int | None = None
    job_memory_bytes: int | None = None
    process_cpu_time_100ns: int | None = None
    job_cpu_time_100ns: int | None = None
    cpu_rate: int | None = None


@dataclass(frozen=True, slots=True)
class WindowsResourceEnforcementFact:
    dimension: WindowsJobResourceDimension
    requested: int
    granted: int
    required: bool
    configured: bool
    active: bool
    capability_state: WindowsResourceCapabilityState
    diagnostics: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WindowsJobResourceApplication:
    accepted: bool
    facts: tuple[WindowsResourceEnforcementFact, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WindowsJobRuntimeMetricsV1:
    available: bool
    active_process_count: int | None
    total_user_time_100ns: int | None
    total_kernel_time_100ns: int | None
    peak_process_memory_bytes: int | None
    peak_job_memory_bytes: int | None
    diagnostics: tuple[str, ...] = ()


class WindowsJobResourceApi(Protocol):
    def resource_capabilities(self) -> tuple[WindowsResourceCapability, ...]: ...
    def configure_job_limits(self, job: int, limits: WindowsNativeJobLimits) -> bool: ...
    def query_job_limits(self, job: int) -> WindowsNativeJobLimits: ...
    def collect_job_metrics(self, job: int) -> WindowsJobRuntimeMetricsV1: ...


class WindowsJobResourceEnforcer:
    def __init__(self, api: WindowsJobResourceApi) -> None:
        self._api = api

    def apply(
        self, job: int, policy: WindowsJobResourcePolicyV1 | None
    ) -> WindowsJobResourceApplication:
        if policy is None or not policy.requirements:
            return WindowsJobResourceApplication(True, (), ())
        capabilities = {item.dimension: item for item in self._api.resource_capabilities()}
        facts: list[WindowsResourceEnforcementFact] = []
        supported: list[WindowsJobResourceRequirement] = []
        for requirement in policy.requirements:
            if requirement.requested > requirement.granted:
                return WindowsJobResourceApplication(
                    False,
                    tuple(facts),
                    ("requested_limit_exceeds_grant",),
                )
            capability = capabilities.get(requirement.dimension)
            configurable = capability is not None and capability.state in {
                WindowsResourceCapabilityState.CONFIGURABLE,
                WindowsResourceCapabilityState.ENFORCED,
            }
            if not configurable:
                state = capability.state if capability is not None else WindowsResourceCapabilityState.UNAVAILABLE
                facts.append(
                    WindowsResourceEnforcementFact(
                        requirement.dimension,
                        requirement.requested,
                        requirement.granted,
                        requirement.required,
                        False,
                        False,
                        state,
                        ("limit_unsupported",),
                    )
                )
                if requirement.required:
                    return WindowsJobResourceApplication(
                        False,
                        tuple(facts),
                        ("required_resource_enforcement_unavailable",),
                    )
                continue
            supported.append(requirement)
        if not supported:
            return WindowsJobResourceApplication(True, tuple(facts), ())
        configured = self._native_limits(tuple(supported))
        if not self._api.configure_job_limits(job, configured):
            return self._configuration_failure(facts, supported, "job_configuration_failed")
        try:
            observed = self._api.query_job_limits(job)
        except OSError:
            return self._configuration_failure(facts, supported, "job_verification_failed")
        for requirement in supported:
            active = self._value(observed, requirement.dimension) == self._value(
                configured, requirement.dimension
            )
            facts.append(
                WindowsResourceEnforcementFact(
                    requirement.dimension,
                    requirement.requested,
                    requirement.granted,
                    requirement.required,
                    True,
                    active,
                    WindowsResourceCapabilityState.ENFORCED if active else WindowsResourceCapabilityState.FAILED,
                    () if active else ("job_verification_failed",),
                )
            )
            if requirement.required and not active:
                return WindowsJobResourceApplication(
                    False, tuple(sorted(facts, key=lambda item: item.dimension.value)), ("job_verification_failed",)
                )
        return WindowsJobResourceApplication(
            True, tuple(sorted(facts, key=lambda item: item.dimension.value)), ()
        )

    def metrics(self, job: int) -> WindowsJobRuntimeMetricsV1:
        try:
            return self._api.collect_job_metrics(job)
        except OSError:
            return WindowsJobRuntimeMetricsV1(False, None, None, None, None, None, ("metrics_unavailable",))

    @staticmethod
    def _native_limits(
        requirements: tuple[WindowsJobResourceRequirement, ...]
    ) -> WindowsNativeJobLimits:
        values: dict[WindowsJobResourceDimension, int] = {
            item.dimension: item.requested for item in requirements
        }
        return WindowsNativeJobLimits(
            values.get(WindowsJobResourceDimension.PROCESS_COUNT),
            values.get(WindowsJobResourceDimension.PROCESS_MEMORY),
            values.get(WindowsJobResourceDimension.JOB_MEMORY),
            WindowsJobResourceEnforcer._milliseconds_to_100ns(
                values.get(WindowsJobResourceDimension.PROCESS_CPU_TIME)
            ),
            WindowsJobResourceEnforcer._milliseconds_to_100ns(
                values.get(WindowsJobResourceDimension.JOB_CPU_TIME)
            ),
            values.get(WindowsJobResourceDimension.CPU_RATE),
        )

    @staticmethod
    def _milliseconds_to_100ns(value: int | None) -> int | None:
        if value is None:
            return None
        if value > MAX_SIGNED_64 // 10_000:
            raise ValueError("resource_policy_invalid")
        return value * 10_000

    @staticmethod
    def _value(limits: WindowsNativeJobLimits, dimension: WindowsJobResourceDimension) -> int | None:
        return {
            WindowsJobResourceDimension.PROCESS_COUNT: limits.active_process_limit,
            WindowsJobResourceDimension.PROCESS_MEMORY: limits.process_memory_bytes,
            WindowsJobResourceDimension.JOB_MEMORY: limits.job_memory_bytes,
            WindowsJobResourceDimension.PROCESS_CPU_TIME: limits.process_cpu_time_100ns,
            WindowsJobResourceDimension.JOB_CPU_TIME: limits.job_cpu_time_100ns,
            WindowsJobResourceDimension.CPU_RATE: limits.cpu_rate,
        }[dimension]

    @staticmethod
    def _configuration_failure(
        facts: list[WindowsResourceEnforcementFact],
        requirements: list[WindowsJobResourceRequirement],
        code: str,
    ) -> WindowsJobResourceApplication:
        for requirement in requirements:
            facts.append(
                WindowsResourceEnforcementFact(
                    requirement.dimension,
                    requirement.requested,
                    requirement.granted,
                    requirement.required,
                    False,
                    False,
                    WindowsResourceCapabilityState.FAILED,
                    (code,),
                )
            )
        required = any(item.required for item in requirements)
        return WindowsJobResourceApplication(
            not required,
            tuple(sorted(facts, key=lambda item: item.dimension.value)),
            (code,) if required else (),
        )
