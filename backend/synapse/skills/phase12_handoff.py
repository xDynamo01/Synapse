from __future__ import annotations

from dataclasses import replace

from synapse.skills.phase2_models import (
    PublishedSkillVersionId,
    SkillExecutionDeclaration,
)
from synapse.skills.phase10_identity import (
    _binding_occurrence_ref,
    _governance_binding_ref,
    _intelligence_binding_ref,
)
from synapse.skills.phase10_models import (
    SkillGovernanceBindingProjection,
    SkillIntelligenceBindingProjection,
)
from synapse.skills.phase10_refs import ExternalBindingOccurrenceRef
from synapse.skills.phase11_identity import (
    _private_eval_binding_ref,
    _private_eval_occurrence_ref,
)
from synapse.skills.phase11_models import SkillPrivateEvalBindingProjection
from synapse.skills.phase11_refs import PrivateEvalBindingOccurrenceRef
from synapse.skills.phase12_errors import (
    CorruptSkillExecutionInputProjection,
    InvalidSkillExecutionBindingReference,
    InvalidSkillExecutionHandoffRequest,
    InvalidSkillExecutionInstallationFact,
    InvalidSkillExecutionLifecycleFact,
    InvalidSkillExecutionResolutionFact,
    SkillExecutionHandoffCorrespondenceError,
    SkillExecutionHandoffLimitExceeded,
)
from synapse.skills.phase12_identity import _handoff_id
from synapse.skills.phase12_models import (
    BuildSkillExecutionHandoffRequest,
    SkillDependencyRegistrationStatus,
    SkillExecutionBindingFamily,
    SkillExecutionBindingHistoryFact,
    SkillExecutionDependencyFact,
    SkillExecutionDependencyRegistrationFact,
    SkillExecutionHandoffBuildResult,
    SkillExecutionHandoffDiagnostic,
    SkillExecutionHandoffDiagnosticCode,
    SkillExecutionHandoffDraft,
    SkillExecutionHandoffRequirements,
    SkillExecutionInstallationFact,
    SkillExecutionLifecycleFact,
    SkillExecutionReadiness,
    SkillExecutionReadinessStatus,
    SkillExecutionResolutionFact,
)
from synapse.skills.phase12_refs import SkillExecutionHandoffId

_SATISFIED = SkillExecutionReadinessStatus.SATISFIED
_INCOMPLETE = SkillExecutionReadinessStatus.INCOMPLETE
_UNKNOWN = SkillExecutionReadinessStatus.UNKNOWN
_NOT_REQUIRED = SkillExecutionReadinessStatus.NOT_REQUIRED


class SkillExecutionHandoffService:
    """Pure validation of caller-supplied facts; it authenticates no source authority."""

    def build(
        self, request: BuildSkillExecutionHandoffRequest
    ) -> SkillExecutionHandoffBuildResult:
        self._validate_request(request)
        execution = self._execution(request)
        dependencies = self._dependencies(request)
        registrations = tuple(
            sorted(
                request.dependency_registrations,
                key=lambda item: item.dependency.to_canonical_text(),
            )
        )
        capabilities = tuple(
            sorted(
                {
                    *request.publication.manifest.capabilities,
                    *(execution.required_capabilities if execution else ()),
                }
            )
        )
        tools = tuple(
            sorted(
                {
                    *request.publication.manifest.tools,
                    *(execution.required_tools if execution else ()),
                }
            )
        )
        resources = (execution.resources,) if execution else ()
        governance = tuple(sorted(request.governance_occurrences))
        intelligence = tuple(sorted(request.intelligence_occurrences))
        private_evals = tuple(sorted(request.private_eval_occurrences))
        self._validate_limits(
            request,
            dependencies,
            capabilities,
            resources,
            governance + intelligence + private_evals,
        )
        diagnostics = self._diagnostics(request, registrations, execution)
        if len(diagnostics) > request.policy.limits.max_diagnostics:
            raise SkillExecutionHandoffLimitExceeded()
        readiness = self._readiness(request, diagnostics)
        requirements = SkillExecutionHandoffRequirements(
            request.policy.require_active_subject,
            request.policy.require_complete_dependency_resolution,
            request.policy.require_resolved_dependency_registrations,
            request.policy.allow_optional_dependency_omissions,
            request.policy.require_declared_execution_profile,
            request.policy.bindings,
        )
        resolution = SkillExecutionResolutionFact(
            request.resolution.resolution_profile_ref,
            request.resolution.policy.version,
            request.resolution.status,
            request.resolution.complete,
            request.resolution.required_resolved,
            request.resolution.has_optional_omissions,
            request.resolution.has_degraded_selections,
            tuple(
                sorted(
                    {item.kind for item in request.resolution.conflicts},
                    key=lambda item: item.value,
                )
            ),
            bool(request.resolution.graph_cycles),
        )
        installation = SkillExecutionInstallationFact(
            request.installation_id
            in {item.record_id for item in request.installation.installations},
            request.installation_id
            in {item.record_id for item in request.installation.current_registrations},
            request.installation.complete,
            request.installation_id
            in set(request.installation.terminated_installation_ids),
            request.installation_id
            in set(request.installation.corrupted_installation_ids),
        )
        lifecycle = SkillExecutionLifecycleFact(
            request.lifecycle_history_complete,
            request.lifecycle.active,
            request.lifecycle.revoked,
            request.lifecycle.deprecated,
            request.lifecycle.superseded,
            request.lifecycle.active_installation_id,
        )
        binding_histories = tuple(
            SkillExecutionBindingHistoryFact(
                family,
                projection is not None,
                projection.history.complete if projection is not None else False,
            )
            for family, projection in (
                (SkillExecutionBindingFamily.GOVERNANCE, request.governance),
                (SkillExecutionBindingFamily.INTELLIGENCE, request.intelligence),
                (SkillExecutionBindingFamily.PRIVATE_EVALS, request.private_evals),
            )
        )
        draft = SkillExecutionHandoffDraft(
            request.format_version,
            SkillExecutionHandoffId("0" * 64),
            request.subject,
            request.installation_id,
            request.activation.record_id if request.activation else None,
            requirements,
            installation,
            lifecycle,
            resolution,
            dependencies,
            registrations,
            capabilities,
            request.publication.manifest.security,
            resources,
            tools,
            execution.runtime if execution else None,
            request.execution_profile,
            execution.entrypoint if execution else None,
            governance,
            intelligence,
            private_evals,
            binding_histories,
            readiness,
            diagnostics,
        )
        draft = replace(draft, handoff_id=_handoff_id(draft))
        return SkillExecutionHandoffBuildResult(draft, readiness)

    @staticmethod
    def _dependencies(
        request: BuildSkillExecutionHandoffRequest,
    ) -> tuple[SkillExecutionDependencyFact, ...]:
        return tuple(
            sorted(
                (
                    SkillExecutionDependencyFact(
                        item.selected,
                        tuple(
                            sorted(str(requirement) for requirement in item.requirement_ids)
                        ),
                        item.policy_version,
                        item.lifecycle_status,
                        item.compatibility_status,
                        item.degraded,
                    )
                    for item in request.resolution.resolved
                ),
                key=lambda item: item.selected.to_canonical_text(),
            )
        )

    @staticmethod
    def _validate_request(request: BuildSkillExecutionHandoffRequest) -> None:
        if not isinstance(request, BuildSkillExecutionHandoffRequest):
            raise InvalidSkillExecutionHandoffRequest()
        if request.publication.identity != request.subject:
            raise SkillExecutionHandoffCorrespondenceError()
        try:
            request.subject.assert_manifest(request.publication.manifest)
        except (TypeError, ValueError, RuntimeError) as exc:
            raise SkillExecutionHandoffCorrespondenceError() from exc
        if (
            request.installation.identity != request.subject
            or request.lifecycle.identity != request.subject
            or request.resolution.subject != request.subject
        ):
            raise SkillExecutionHandoffCorrespondenceError()
        SkillExecutionHandoffService._validate_installation(request)
        SkillExecutionHandoffService._validate_lifecycle(request)
        SkillExecutionHandoffService._validate_resolution(request)
        for projection in (
            request.governance,
            request.intelligence,
            request.private_evals,
        ):
            if projection is not None and projection.identity != request.subject:
                raise SkillExecutionHandoffCorrespondenceError()
        SkillExecutionHandoffService._validate_occurrences(request)

    @staticmethod
    def _validate_installation(request: BuildSkillExecutionHandoffRequest) -> None:
        projection = request.installation
        current = {record.record_id: record for record in projection.current_registrations}
        installations = {record.record_id: record for record in projection.installations}
        terminated = set(projection.terminated_installation_ids)
        corrupted = set(projection.corrupted_installation_ids)
        if (
            len(installations) != len(projection.installations)
            or len(current) != len(projection.current_registrations)
            or not set(current).issubset(installations)
            or not terminated.issubset(installations)
            or not corrupted.issubset(terminated)
            or set(current).intersection(terminated)
            or projection.has_current_registration != bool(current)
        ):
            raise CorruptSkillExecutionInputProjection()
        for record in projection.installations:
            if (
                record.identity != request.subject
                or record.content_fingerprint != request.subject.content_fingerprint
            ):
                raise InvalidSkillExecutionInstallationFact()
        selected = installations.get(request.installation_id)
        if selected is not None and selected.identity != request.subject:
            raise InvalidSkillExecutionInstallationFact()

    @staticmethod
    def _validate_lifecycle(request: BuildSkillExecutionHandoffRequest) -> None:
        if request.activation is not None and (
            request.activation.identity != request.subject
            or request.activation.installation_id != request.installation_id
        ):
            raise SkillExecutionHandoffCorrespondenceError()
        if request.lifecycle.active_installation_id is not None and (
            request.lifecycle.active_installation_id != request.installation_id
        ):
            raise InvalidSkillExecutionLifecycleFact()
        if request.lifecycle.revoked and request.lifecycle.active:
            raise InvalidSkillExecutionLifecycleFact()

    @staticmethod
    def _validate_resolution(request: BuildSkillExecutionHandoffRequest) -> None:
        resolution = request.resolution
        if (
            not isinstance(resolution.complete, bool)
            or not isinstance(resolution.required_resolved, bool)
            or any(
                item.policy_version != resolution.policy.version
                for item in resolution.resolved
            )
        ):
            raise InvalidSkillExecutionResolutionFact()
        selected_dependencies = {item.selected for item in resolution.resolved}
        if len(selected_dependencies) != len(resolution.resolved):
            raise InvalidSkillExecutionResolutionFact()
        registration_dependencies = {
            item.dependency for item in request.dependency_registrations
        }
        if (
            len(registration_dependencies) != len(request.dependency_registrations)
            or not registration_dependencies.issubset(selected_dependencies)
        ):
            raise InvalidSkillExecutionResolutionFact()

    @staticmethod
    def _validate_occurrences(request: BuildSkillExecutionHandoffRequest) -> None:
        SkillExecutionHandoffService._validate_governance_occurrences(
            request.governance, request.governance_occurrences, request.subject
        )
        SkillExecutionHandoffService._validate_intelligence_occurrences(
            request.intelligence, request.intelligence_occurrences, request.subject
        )
        SkillExecutionHandoffService._validate_private_eval_occurrences(
            request.private_evals, request.private_eval_occurrences, request.subject
        )

    @staticmethod
    def _validate_governance_occurrences(
        projection: SkillGovernanceBindingProjection | None,
        selected: tuple[ExternalBindingOccurrenceRef, ...],
        subject: PublishedSkillVersionId,
    ) -> None:
        if len(set(selected)) != len(selected):
            raise InvalidSkillExecutionBindingReference()
        if projection is None:
            if selected:
                raise InvalidSkillExecutionBindingReference()
            return
        records = {record.occurrence_ref: record for record in projection.history.records}
        for occurrence in selected:
            record = records.get(occurrence)
            if record is None or record.identity != subject:
                raise InvalidSkillExecutionBindingReference()
            expected_binding = _governance_binding_ref(
                record.identity,
                record.authority_ref,
                record.decision_ref,
                record.decision_kind_ref,
                record.policy_ref,
            )
            expected_occurrence = _binding_occurrence_ref(
                "governance", expected_binding, record.binder_ref, record.bound_at
            )
            if (
                record.binding_ref != expected_binding
                or record.occurrence_ref != expected_occurrence
            ):
                raise InvalidSkillExecutionBindingReference()

    @staticmethod
    def _validate_intelligence_occurrences(
        projection: SkillIntelligenceBindingProjection | None,
        selected: tuple[ExternalBindingOccurrenceRef, ...],
        subject: PublishedSkillVersionId,
    ) -> None:
        if len(set(selected)) != len(selected):
            raise InvalidSkillExecutionBindingReference()
        if projection is None:
            if selected:
                raise InvalidSkillExecutionBindingReference()
            return
        records = {record.occurrence_ref: record for record in projection.history.records}
        for occurrence in selected:
            record = records.get(occurrence)
            if record is None or record.identity != subject:
                raise InvalidSkillExecutionBindingReference()
            expected_binding = _intelligence_binding_ref(
                record.identity,
                record.authority_ref,
                record.fact_ref,
                record.fact_kind_ref,
                record.profile_ref,
                record.analysis_ref,
            )
            expected_occurrence = _binding_occurrence_ref(
                "intelligence", expected_binding, record.binder_ref, record.bound_at
            )
            if (
                record.binding_ref != expected_binding
                or record.occurrence_ref != expected_occurrence
            ):
                raise InvalidSkillExecutionBindingReference()

    @staticmethod
    def _validate_private_eval_occurrences(
        projection: SkillPrivateEvalBindingProjection | None,
        selected: tuple[PrivateEvalBindingOccurrenceRef, ...],
        subject: PublishedSkillVersionId,
    ) -> None:
        if len(set(selected)) != len(selected):
            raise InvalidSkillExecutionBindingReference()
        if projection is None:
            if selected:
                raise InvalidSkillExecutionBindingReference()
            return
        records = {record.occurrence_ref: record for record in projection.history.records}
        for occurrence in selected:
            record = records.get(occurrence)
            if record is None or record.identity != subject:
                raise InvalidSkillExecutionBindingReference()
            expected_binding = _private_eval_binding_ref(record)
            expected_occurrence = _private_eval_occurrence_ref(
                expected_binding, record.binder_ref, record.bound_at
            )
            if (
                record.binding_ref != expected_binding
                or record.occurrence_ref != expected_occurrence
            ):
                raise InvalidSkillExecutionBindingReference()

    @staticmethod
    def _execution(
        request: BuildSkillExecutionHandoffRequest,
    ) -> SkillExecutionDeclaration | None:
        if request.logical_entrypoint is None:
            return None
        matches = tuple(
            item
            for item in request.publication.manifest.execution
            if item.entrypoint.logical_path == request.logical_entrypoint
        )
        if len(matches) != 1:
            raise InvalidSkillExecutionHandoffRequest()
        return matches[0]

    @staticmethod
    def _validate_limits(
        request: BuildSkillExecutionHandoffRequest,
        dependencies: tuple[object, ...],
        capabilities: tuple[object, ...],
        resources: tuple[object, ...],
        external: tuple[object, ...],
    ) -> None:
        limits = request.policy.limits
        counts = (
            (len(dependencies), limits.max_dependencies),
            (len(capabilities), limits.max_capabilities),
            (1, limits.max_security_declarations),
            (len(resources), limits.max_resources),
            (len(external), limits.max_external_bindings),
        )
        if any(actual > maximum for actual, maximum in counts):
            raise SkillExecutionHandoffLimitExceeded()

    @staticmethod
    def _diagnostics(
        request: BuildSkillExecutionHandoffRequest,
        registrations: tuple[SkillExecutionDependencyRegistrationFact, ...],
        execution: SkillExecutionDeclaration | None,
    ) -> tuple[SkillExecutionHandoffDiagnostic, ...]:
        diagnostics: tuple[SkillExecutionHandoffDiagnostic, ...] = ()
        installation_ids = {
            record.record_id for record in request.installation.installations
        }
        current_ids = {
            record.record_id for record in request.installation.current_registrations
        }
        if request.installation_id not in installation_ids:
            diagnostics += (_diagnostic(SkillExecutionHandoffDiagnosticCode.INSTALLATION_MISSING),)
        elif request.installation_id in request.installation.corrupted_installation_ids:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_REGISTRATION_CORRUPTED
                ),
            )
        elif request.installation_id not in current_ids:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.INSTALLATION_TERMINATED),
            )
        if not request.installation.complete:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_HISTORY_INCOMPLETE
                ),
            )
        if request.activation is None:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.ACTIVATION_MISSING),
            )
        if not request.lifecycle_history_complete:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.LIFECYCLE_HISTORY_INCOMPLETE
                ),
            )
        if request.lifecycle.revoked:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.LIFECYCLE_REVOKED),
            )
        elif not request.lifecycle.active:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.LIFECYCLE_INACTIVE),
            )
        if request.lifecycle.deprecated:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.LIFECYCLE_DEPRECATED),
            )
        if request.lifecycle.superseded:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.LIFECYCLE_SUPERSEDED),
            )
        if not request.resolution.complete:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.RESOLUTION_INCOMPLETE),
            )
        if not request.resolution.required_resolved:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.UNRESOLVED_REQUIRED_DEPENDENCY
                ),
            )
        if request.resolution.has_optional_omissions:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.OPTIONAL_DEPENDENCY_OMITTED
                ),
            )
        if request.resolution.has_degraded_selections:
            diagnostics += (
                _diagnostic(
                    SkillExecutionHandoffDiagnosticCode.DEGRADED_DEPENDENCY_SELECTION
                ),
            )
        if request.resolution.conflicts:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.RESOLUTION_CONFLICT),
            )
        if request.resolution.graph_cycles:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.GRAPH_CYCLE_CONFLICT),
            )
        registrations_by_subject = {item.dependency: item for item in registrations}
        for dependency in sorted(
            (item.selected for item in request.resolution.resolved),
            key=lambda item: item.to_canonical_text(),
        ):
            registration = registrations_by_subject.get(dependency)
            if registration is None or not registration.history_complete:
                diagnostics += (
                    _diagnostic(
                        SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_UNKNOWN,
                        dependency,
                    ),
                )
            elif registration.status is not SkillDependencyRegistrationStatus.REGISTERED:
                diagnostics += (
                    _diagnostic(
                        SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_INVALID,
                        dependency,
                    ),
                )
        if request.execution_profile is None or execution is None:
            diagnostics += (
                _diagnostic(SkillExecutionHandoffDiagnosticCode.EXECUTION_PROFILE_MISSING),
            )
        for family, required, projection, selected in (
            (
                SkillExecutionBindingFamily.GOVERNANCE,
                request.policy.bindings.require_governance,
                request.governance,
                request.governance_occurrences,
            ),
            (
                SkillExecutionBindingFamily.INTELLIGENCE,
                request.policy.bindings.require_intelligence,
                request.intelligence,
                request.intelligence_occurrences,
            ),
            (
                SkillExecutionBindingFamily.PRIVATE_EVALS,
                request.policy.bindings.require_private_evals,
                request.private_evals,
                request.private_eval_occurrences,
            ),
        ):
            if required and not selected:
                diagnostics += (
                    _diagnostic(
                        SkillExecutionHandoffDiagnosticCode.EXTERNAL_BINDING_ABSENT,
                        binding_family=family,
                    ),
                )
            if (
                projection is not None
                and request.policy.bindings.require_complete_histories
                and not projection.history.complete
            ):
                diagnostics += (
                    _diagnostic(
                        SkillExecutionHandoffDiagnosticCode.BINDING_HISTORY_INCOMPLETE,
                        binding_family=family,
                    ),
                )
        return tuple(sorted(set(diagnostics)))

    @staticmethod
    def _readiness(
        request: BuildSkillExecutionHandoffRequest,
        diagnostics: tuple[SkillExecutionHandoffDiagnostic, ...],
    ) -> SkillExecutionReadiness:
        codes = {item.code for item in diagnostics}
        installation = (
            _INCOMPLETE
            if codes.intersection(
                {
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_MISSING,
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_TERMINATED,
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_REGISTRATION_CORRUPTED,
                    SkillExecutionHandoffDiagnosticCode.INSTALLATION_HISTORY_INCOMPLETE,
                }
            )
            else _SATISFIED
        )
        lifecycle_blocking = codes.intersection(
            {
                SkillExecutionHandoffDiagnosticCode.ACTIVATION_MISSING,
                SkillExecutionHandoffDiagnosticCode.LIFECYCLE_HISTORY_INCOMPLETE,
                SkillExecutionHandoffDiagnosticCode.LIFECYCLE_INACTIVE,
                SkillExecutionHandoffDiagnosticCode.LIFECYCLE_REVOKED,
            }
        )
        if SkillExecutionHandoffDiagnosticCode.LIFECYCLE_REVOKED in codes:
            lifecycle = _INCOMPLETE
        elif request.policy.require_active_subject:
            lifecycle = _INCOMPLETE if lifecycle_blocking else _SATISFIED
        else:
            lifecycle = _NOT_REQUIRED
        dependencies = (
            _INCOMPLETE
            if codes.intersection(
                {
                    SkillExecutionHandoffDiagnosticCode.RESOLUTION_INCOMPLETE,
                    SkillExecutionHandoffDiagnosticCode.UNRESOLVED_REQUIRED_DEPENDENCY,
                    SkillExecutionHandoffDiagnosticCode.RESOLUTION_CONFLICT,
                    SkillExecutionHandoffDiagnosticCode.GRAPH_CYCLE_CONFLICT,
                }
            )
            else _SATISFIED
        )
        if (
            SkillExecutionHandoffDiagnosticCode.OPTIONAL_DEPENDENCY_OMITTED in codes
            and not request.policy.allow_optional_dependency_omissions
        ):
            dependencies = _INCOMPLETE
        registration = (
            _UNKNOWN
            if codes.intersection(
                {
                    SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_UNKNOWN,
                    SkillExecutionHandoffDiagnosticCode.DEPENDENCY_REGISTRATION_INVALID,
                }
            )
            else (_NOT_REQUIRED if not request.resolution.resolved else _SATISFIED)
        )
        external = (
            _INCOMPLETE
            if codes.intersection(
                {
                    SkillExecutionHandoffDiagnosticCode.EXTERNAL_BINDING_ABSENT,
                    SkillExecutionHandoffDiagnosticCode.BINDING_HISTORY_INCOMPLETE,
                }
            )
            else _SATISFIED
        )
        profile = (
            _INCOMPLETE
            if SkillExecutionHandoffDiagnosticCode.EXECUTION_PROFILE_MISSING in codes
            else _SATISFIED
        )
        required_dimensions = (
            installation,
            lifecycle,
            (
                dependencies
                if request.policy.require_complete_dependency_resolution
                else _NOT_REQUIRED
            ),
            (
                registration
                if request.policy.require_resolved_dependency_registrations
                else _NOT_REQUIRED
            ),
            external,
            (
                profile
                if request.policy.require_declared_execution_profile
                else _NOT_REQUIRED
            ),
        )
        complete = (
            _SATISFIED
            if all(
                item in {_SATISFIED, _NOT_REQUIRED}
                for item in required_dimensions
            )
            else _INCOMPLETE
        )
        return SkillExecutionReadiness(
            _SATISFIED,
            installation,
            lifecycle,
            dependencies,
            registration,
            _SATISFIED,
            _SATISFIED,
            profile,
            external,
            complete,
        )


def _diagnostic(
    code: SkillExecutionHandoffDiagnosticCode,
    subject: PublishedSkillVersionId | None = None,
    *,
    binding_family: SkillExecutionBindingFamily | None = None,
) -> SkillExecutionHandoffDiagnostic:
    return SkillExecutionHandoffDiagnostic(
        code,
        subject,
        binding_family,
    )
