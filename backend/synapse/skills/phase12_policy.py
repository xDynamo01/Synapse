from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase12_errors import InvalidSkillExecutionHandoffPolicy


@dataclass(frozen=True)
class SkillExecutionHandoffLimits:
    max_dependencies: int
    max_capabilities: int
    max_security_declarations: int
    max_resources: int
    max_external_bindings: int
    max_diagnostics: int

    def __post_init__(self) -> None:
        values = (
            self.max_dependencies,
            self.max_capabilities,
            self.max_security_declarations,
            self.max_resources,
            self.max_external_bindings,
            self.max_diagnostics,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 1 <= value <= 5_000
            for value in values
        ):
            raise InvalidSkillExecutionHandoffPolicy()


@dataclass(frozen=True)
class SkillExecutionBindingCompletenessPolicy:
    require_governance: bool
    require_intelligence: bool
    require_private_evals: bool
    require_complete_histories: bool

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, bool)
            for value in (
                self.require_governance,
                self.require_intelligence,
                self.require_private_evals,
                self.require_complete_histories,
            )
        ):
            raise InvalidSkillExecutionHandoffPolicy()


@dataclass(frozen=True)
class SkillExecutionHandoffBuildPolicy:
    require_active_subject: bool
    require_complete_dependency_resolution: bool
    require_resolved_dependency_registrations: bool
    allow_optional_dependency_omissions: bool
    require_declared_execution_profile: bool
    bindings: SkillExecutionBindingCompletenessPolicy
    limits: SkillExecutionHandoffLimits

    def __post_init__(self) -> None:
        if (
            not all(
                isinstance(value, bool)
                for value in (
                    self.require_active_subject,
                    self.require_complete_dependency_resolution,
                    self.require_resolved_dependency_registrations,
                    self.allow_optional_dependency_omissions,
                    self.require_declared_execution_profile,
                )
            )
            or not isinstance(self.bindings, SkillExecutionBindingCompletenessPolicy)
            or not isinstance(self.limits, SkillExecutionHandoffLimits)
        ):
            raise InvalidSkillExecutionHandoffPolicy()
