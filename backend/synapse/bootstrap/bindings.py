"""Factual Global Composition Root binding inventory.

The inventory describes current construction authority without importing or
activating any bounded-context Composition Root.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class GlobalBindingId(StrEnum):
    PRIVATE_EVALS = "private-evals"
    CODING_SESSIONS = "coding-sessions"
    SKILLS_RUNTIME_PHASE_2 = "skills-runtime-phase-2"
    SANDBOX_EXECUTION_BOUNDARY = "sandbox-execution-boundary"
    CONCRETE_SANDBOX_DRIVER = "concrete-sandbox-driver"
    REPOSITORY_RUNTIME = "repository-runtime"
    VOICE_AUDIO_PERCEPTION = "voice-audio-perception"
    SEARCH_RUNTIME = "search-runtime"
    DEPLOYMENT_RUNTIME = "deployment-runtime"


class GlobalBindingRequirement(StrEnum):
    REQUIRED = "required"
    INTENTIONALLY_OPTIONAL = "intentionally-optional"


class GlobalBindingAvailability(StrEnum):
    AVAILABLE = "available"
    CAPABILITY_LIMITED = "capability-limited"
    UNAVAILABLE = "unavailable"


class GlobalBindingMode(StrEnum):
    GLOBAL = "global"
    LOCAL_OPT_IN = "local-opt-in"
    LEGACY_GLOBAL_ONLY = "legacy-global-only"
    ABSENT = "absent"


class GlobalBindingActivationAuthority(StrEnum):
    NOT_AUTHORIZED = "not-authorized"
    AUTHORIZED = "authorized"


class GlobalBindingActivationState(StrEnum):
    INERT = "inert"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class GlobalBindingDeclaration:
    binding_id: GlobalBindingId
    requirement: GlobalBindingRequirement
    availability: GlobalBindingAvailability
    mode: GlobalBindingMode
    composition_reference: str | None
    activation_authority: GlobalBindingActivationAuthority = (
        GlobalBindingActivationAuthority.NOT_AUTHORIZED
    )
    activation_state: GlobalBindingActivationState = GlobalBindingActivationState.INERT

    @property
    def blocks_backend_readiness(self) -> bool:
        return self.requirement is GlobalBindingRequirement.REQUIRED and (
            self.mode is not GlobalBindingMode.GLOBAL
            or self.activation_state is not GlobalBindingActivationState.ACTIVE
        )


_CANONICAL_GLOBAL_BINDING_INVENTORY = (
    GlobalBindingDeclaration(
        GlobalBindingId.PRIVATE_EVALS,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "private_evals.composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.CODING_SESSIONS,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "coding_sessions_composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.SKILLS_RUNTIME_PHASE_2,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "skills.composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.SANDBOX_EXECUTION_BOUNDARY,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "sandbox_composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.CONCRETE_SANDBOX_DRIVER,
        GlobalBindingRequirement.INTENTIONALLY_OPTIONAL,
        GlobalBindingAvailability.CAPABILITY_LIMITED,
        GlobalBindingMode.LOCAL_OPT_IN,
        "sandbox_driver_composition",
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.REPOSITORY_RUNTIME,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "repository_runtime_composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.VOICE_AUDIO_PERCEPTION,
        GlobalBindingRequirement.INTENTIONALLY_OPTIONAL,
        GlobalBindingAvailability.CAPABILITY_LIMITED,
        GlobalBindingMode.LEGACY_GLOBAL_ONLY,
        "voice-composition-root",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.SEARCH_RUNTIME,
        GlobalBindingRequirement.INTENTIONALLY_OPTIONAL,
        GlobalBindingAvailability.CAPABILITY_LIMITED,
        GlobalBindingMode.LOCAL_OPT_IN,
        "search_composition",
    ),
    GlobalBindingDeclaration(
        GlobalBindingId.DEPLOYMENT_RUNTIME,
        GlobalBindingRequirement.REQUIRED,
        GlobalBindingAvailability.AVAILABLE,
        GlobalBindingMode.GLOBAL,
        "deployment_composition",
        GlobalBindingActivationAuthority.AUTHORIZED,
        GlobalBindingActivationState.ACTIVE,
    ),
)


def canonical_global_binding_inventory() -> tuple[GlobalBindingDeclaration, ...]:
    """Return the immutable factual inventory without constructing dependencies."""

    return _CANONICAL_GLOBAL_BINDING_INVENTORY
