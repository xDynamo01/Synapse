"""Immutable Coding Session contracts and their pure factual assessment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, TypeAlias

from .causal import CodingSessionCausalMetadata
from .identities import CodingSessionFingerprint, CodingSessionIdentity
from .references import (
    CodingSessionActorReference,
    CodingSessionCheckoutReference,
    CodingSessionCorrelationReference,
    CodingSessionPlatformContextReference,
    CodingSessionProjectReference,
    CodingSessionPurposeReference,
    CodingSessionRepositoryReference,
    CodingSessionTaskReference,
    CodingSessionWorktreeReference,
)

CODING_SESSION_CONTRACT_VERSION = "coding-session-contract-v1"
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class CodingSessionBindingScope(str, Enum):
    NONE = "none"
    REPOSITORY = "repository"
    CHECKOUT = "checkout"
    WORKTREE = "worktree"


class CodingSessionRequestedCapability(str, Enum):
    REPOSITORY_ACCESS = "repository-access"
    REPOSITORY_MUTATION = "repository-mutation"
    SANDBOX_EXECUTION = "sandbox-execution"
    WORKER_ASSISTANCE = "worker-assistance"
    PRIVATE_EVAL = "private-eval"
    APPROVAL = "approval"
    ARTIFACT_PRODUCTION = "artifact-production"
    DEPLOYMENT_CANDIDATE_HANDOFF = "deployment-candidate-handoff"


class CodingSessionCompletionRequirement(str, Enum):
    REPOSITORY_VERIFICATION = "repository-verification"
    DURABLE_CHECKPOINT = "durable-checkpoint"
    CORRESPONDING_EVAL_RESULT = "corresponding-eval-result"
    NO_PENDING_RECOVERY = "no-pending-recovery"
    VALID_ARTIFACT_REFERENCE = "valid-artifact-reference"


CodingSessionRequirementCode: TypeAlias = (
    CodingSessionRequestedCapability | CodingSessionCompletionRequirement
)


class CodingSessionContractDiagnosticCode(str, Enum):
    MISSING_REQUIRED_BINDING = "missing-required-binding"
    INCOMPATIBLE_BINDING_COMBINATION = "incompatible-binding-combination"
    INVALID_EXTERNAL_REFERENCE = "invalid-external-reference"
    DUPLICATE_SEMANTIC_REQUIREMENT = "duplicate-semantic-requirement"
    CONFLICTING_REQUIREMENT = "conflicting-requirement"
    MISMATCHED_SESSION_IDENTITY = "mismatched-session-identity"
    MISMATCHED_PROJECT_REPOSITORY_RELATIONSHIP = (
        "mismatched-project-repository-relationship"
    )
    UNSUPPORTED_CONTRACT_VERSION = "unsupported-contract-version"


class CodingSessionContractDiagnosticSeverity(str, Enum):
    ERROR = "error"


class CodingSessionRuntimeConclusion(str, Enum):
    NOT_EVALUATED = "not-evaluated"


@dataclass(frozen=True, slots=True)
class CodingSessionPurpose:
    task: CodingSessionTaskReference
    purpose: CodingSessionPurposeReference


@dataclass(frozen=True, slots=True)
class CodingSessionBinding:
    session_identity: CodingSessionIdentity
    project: CodingSessionProjectReference
    scope: CodingSessionBindingScope
    repository: CodingSessionRepositoryReference | None = None
    checkout: CodingSessionCheckoutReference | None = None
    worktree: CodingSessionWorktreeReference | None = None
    platform_context: CodingSessionPlatformContextReference | None = None


@dataclass(frozen=True, slots=True)
class CodingSessionRequirement:
    code: CodingSessionRequirementCode
    target: CodingSessionFingerprint | None = None

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True, order=True)
class CodingSessionContractDiagnostic:
    code: CodingSessionContractDiagnosticCode
    subject: str
    severity: CodingSessionContractDiagnosticSeverity = (
        CodingSessionContractDiagnosticSeverity.ERROR
    )


@dataclass(frozen=True, slots=True)
class CodingSessionContract:
    session_identity: CodingSessionIdentity
    actor: CodingSessionActorReference
    project: CodingSessionProjectReference
    purpose: CodingSessionPurpose
    correlation: CodingSessionCorrelationReference
    binding: CodingSessionBinding
    requested_capabilities: tuple[CodingSessionRequirement, ...]
    completion_requirements: tuple[CodingSessionRequirement, ...]
    policy_version: str
    causal_metadata: CodingSessionCausalMetadata
    contract_version: str = CODING_SESSION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requested_capabilities",
            tuple(sorted(self.requested_capabilities, key=lambda item: item.fingerprint.value)),
        )
        object.__setattr__(
            self,
            "completion_requirements",
            tuple(sorted(self.completion_requirements, key=lambda item: item.fingerprint.value)),
        )

    def semantic_content(self) -> object:
        return (
            self.contract_version,
            self.session_identity,
            self.actor,
            self.project,
            self.purpose,
            self.correlation,
            self.binding,
            self.requested_capabilities,
            self.completion_requirements,
            self.policy_version,
            self.causal_metadata,
        )

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self.semantic_content())


@dataclass(frozen=True, slots=True)
class CodingSessionContractAssessment:
    contract_fingerprint: CodingSessionFingerprint
    complete: bool
    valid: bool
    prepared: CodingSessionRuntimeConclusion
    active: CodingSessionRuntimeConclusion
    diagnostics: tuple[CodingSessionContractDiagnostic, ...]

    @classmethod
    def assess(cls, contract: CodingSessionContract) -> CodingSessionContractAssessment:
        diagnostics = _diagnostics_for(contract)
        completeness_codes = {
            CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING,
            CodingSessionContractDiagnosticCode.INCOMPATIBLE_BINDING_COMBINATION,
        }
        return cls(
            contract_fingerprint=contract.fingerprint,
            complete=not any(item.code in completeness_codes for item in diagnostics),
            valid=not diagnostics,
            prepared=CodingSessionRuntimeConclusion.NOT_EVALUATED,
            active=CodingSessionRuntimeConclusion.NOT_EVALUATED,
            diagnostics=diagnostics,
        )


def _diagnostics_for(
    contract: CodingSessionContract,
) -> tuple[CodingSessionContractDiagnostic, ...]:
    findings: set[CodingSessionContractDiagnostic] = set()
    add = findings.add

    if contract.contract_version != CODING_SESSION_CONTRACT_VERSION or not _VERSION.fullmatch(
        contract.policy_version
    ):
        add(_diagnostic(CodingSessionContractDiagnosticCode.UNSUPPORTED_CONTRACT_VERSION, "version"))
    if contract.binding.session_identity != contract.session_identity:
        add(_diagnostic(CodingSessionContractDiagnosticCode.MISMATCHED_SESSION_IDENTITY, "binding"))
    if contract.causal_metadata.semantic_identity != contract.session_identity:
        add(_diagnostic(CodingSessionContractDiagnosticCode.MISMATCHED_SESSION_IDENTITY, "causal"))
    if contract.binding.project != contract.project:
        add(
            _diagnostic(
                CodingSessionContractDiagnosticCode.MISMATCHED_PROJECT_REPOSITORY_RELATIONSHIP,
                "binding.project",
            )
        )

    _assess_binding(contract.binding, add)
    _assess_requirements(contract, add)
    return tuple(sorted(findings, key=lambda item: (item.code.value, item.subject)))


def _assess_binding(
    binding: CodingSessionBinding,
    add: Callable[[CodingSessionContractDiagnostic], None],
) -> None:
    emit = add  # retained as a narrow local callback without exposing an assessment port
    expected = {
        CodingSessionBindingScope.NONE: (False, False, False),
        CodingSessionBindingScope.REPOSITORY: (True, False, False),
        CodingSessionBindingScope.CHECKOUT: (True, True, False),
        CodingSessionBindingScope.WORKTREE: (True, True, True),
    }[binding.scope]
    actual = tuple(
        item is not None for item in (binding.repository, binding.checkout, binding.worktree)
    )
    for subject, required, present in zip(
        ("binding.repository", "binding.checkout", "binding.worktree"), expected, actual
    ):
        if required and not present:
            emit(_diagnostic(CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING, subject))
        elif not required and present:
            emit(
                _diagnostic(
                    CodingSessionContractDiagnosticCode.INCOMPATIBLE_BINDING_COMBINATION,
                    subject,
                )
            )
    external = tuple(
        item
        for item in (
            binding.repository,
            binding.checkout,
            binding.worktree,
            binding.platform_context,
        )
        if item is not None
    )
    repository_chain = tuple(
        item for item in (binding.repository, binding.checkout, binding.worktree) if item is not None
    )
    if repository_chain and len({(item.producer, item.version) for item in repository_chain}) != 1:
        emit(
            _diagnostic(
                CodingSessionContractDiagnosticCode.INVALID_EXTERNAL_REFERENCE,
                "binding.repository-chain",
            )
        )
    if any(item.identity == "" for item in external):
        emit(
            _diagnostic(
                CodingSessionContractDiagnosticCode.INVALID_EXTERNAL_REFERENCE,
                "binding.external-reference",
            )
        )


def _assess_requirements(
    contract: CodingSessionContract,
    add: Callable[[CodingSessionContractDiagnostic], None],
) -> None:
    emit = add
    requested = contract.requested_capabilities
    completion = contract.completion_requirements
    for subject, requirements, expected_type in (
        ("requested-capabilities", requested, CodingSessionRequestedCapability),
        ("completion-requirements", completion, CodingSessionCompletionRequirement),
    ):
        seen: set[CodingSessionRequirement] = set()
        targets: dict[CodingSessionRequirementCode, CodingSessionFingerprint | None] = {}
        for requirement in requirements:
            if not isinstance(requirement.code, expected_type):
                emit(
                    _diagnostic(
                        CodingSessionContractDiagnosticCode.CONFLICTING_REQUIREMENT, subject
                    )
                )
            if requirement in seen:
                emit(
                    _diagnostic(
                        CodingSessionContractDiagnosticCode.DUPLICATE_SEMANTIC_REQUIREMENT,
                        subject,
                    )
                )
            seen.add(requirement)
            previous = targets.get(requirement.code)
            if requirement.code in targets and previous != requirement.target:
                emit(
                    _diagnostic(
                        CodingSessionContractDiagnosticCode.CONFLICTING_REQUIREMENT, subject
                    )
                )
            targets[requirement.code] = requirement.target

    capabilities = {requirement.code for requirement in requested}
    completions = {requirement.code for requirement in completion}
    repository_required = bool(
        capabilities
        & {
            CodingSessionRequestedCapability.REPOSITORY_ACCESS,
            CodingSessionRequestedCapability.REPOSITORY_MUTATION,
        }
        or completions
        & {
            CodingSessionCompletionRequirement.REPOSITORY_VERIFICATION,
            CodingSessionCompletionRequirement.NO_PENDING_RECOVERY,
        }
    )
    if repository_required and contract.binding.repository is None:
        emit(
            _diagnostic(
                CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING,
                "binding.repository",
            )
        )
    if (
        CodingSessionRequestedCapability.REPOSITORY_MUTATION in capabilities
        and contract.binding.worktree is None
    ):
        emit(
            _diagnostic(
                CodingSessionContractDiagnosticCode.MISSING_REQUIRED_BINDING,
                "binding.worktree",
            )
        )


def _diagnostic(
    code: CodingSessionContractDiagnosticCode, subject: str
) -> CodingSessionContractDiagnostic:
    return CodingSessionContractDiagnostic(code=code, subject=subject)
