"""Durable ownership fencing contracts; no authorization or host effects."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from .identities import (
    CodingSessionFingerprint,
    CodingSessionIdentity,
    CodingSessionLeaseFactIdentity,
)
from .references import (
    CodingSessionCheckoutReference,
    CodingSessionCorrelationReference,
    CodingSessionRepositoryReference,
    CodingSessionWorktreeReference,
)

FENCING_AUTHORITY_VERSION = "coding-session-fencing-authority-v1"
FENCING_TOKEN_VERSION = "coding-session-fencing-token-v1"
MAX_FENCING_GENERATION = 2**64 - 1
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{0,191}$")


class FencingContractError(ValueError):
    pass


class FencingStoreError(RuntimeError):
    pass


class FencingConflictError(FencingStoreError):
    pass


class FencingIntegrityError(FencingStoreError):
    pass


class FencingOperationClass(StrEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    WORKSPACE_DELETE_REPLACE = "workspace-delete-replace"
    REPOSITORY_MUTATION_APPLICATION = "repository-mutation-application"
    ARTIFACT_CUSTODY_MUTATION = "artifact-custody-mutation"
    ARTIFACT_PUBLICATION = "artifact-publication"
    DEPLOYMENT_AFFECTING_WRITE = "deployment-affecting-write"
    WORKER_WRITEBACK = "worker-writeback"
    MUTABLE_RESULT_STATE_PUBLICATION = "mutable-result-state-publication"
    DESTRUCTIVE_CLEANUP = "destructive-cleanup"

    @property
    def fencing_required(self) -> bool:
        return self is not FencingOperationClass.READ_ONLY


class FencingValidationState(StrEnum):
    VALID = "valid"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
    MISMATCHED = "mismatched"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class FencingGeneration:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not 1 <= self.value <= MAX_FENCING_GENERATION:
            raise FencingContractError("generation-invalid")


@dataclass(frozen=True, slots=True)
class FencingScope:
    session: CodingSessionIdentity
    repository: CodingSessionRepositoryReference | None = None
    checkout: CodingSessionCheckoutReference | None = None
    worktree: CodingSessionWorktreeReference | None = None
    workspace_reference: str | None = None

    def __post_init__(self) -> None:
        if self.checkout is not None and self.repository is None:
            raise FencingContractError("scope-invalid")
        if self.worktree is not None and self.checkout is None:
            raise FencingContractError("scope-invalid")
        if self.workspace_reference is not None and not _REFERENCE.fullmatch(self.workspace_reference):
            raise FencingContractError("scope-invalid")
        if all(x is None for x in (self.repository, self.workspace_reference)):
            raise FencingContractError("scope-invalid")

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class FencingTransitionRequest:
    scope: FencingScope
    ownership_identity: CodingSessionLeaseFactIdentity
    authority_identity: str
    authority_version: str
    occurrence_reference: str
    correlation: CodingSessionCorrelationReference | None = None
    causation_fingerprint: CodingSessionFingerprint | None = None
    binding_fingerprint: CodingSessionFingerprint | None = None
    idempotency_key: str = ""
    expected_generation: int = 0

    def __post_init__(self) -> None:
        for value in (self.authority_identity, self.occurrence_reference, self.idempotency_key):
            if not _REFERENCE.fullmatch(value):
                raise FencingContractError("transition-reference-invalid")
        if self.authority_version != FENCING_AUTHORITY_VERSION:
            raise FencingContractError("authority-version-invalid")
        if isinstance(self.expected_generation, bool) or not (
            0 <= self.expected_generation < MAX_FENCING_GENERATION
        ):
            raise FencingContractError("generation-invalid")

    @property
    def fingerprint(self) -> CodingSessionFingerprint:
        return CodingSessionFingerprint.from_content(self)


@dataclass(frozen=True, slots=True)
class FencingGenerationFact:
    scope: FencingScope
    generation: FencingGeneration
    ownership_identity: CodingSessionLeaseFactIdentity
    authority_identity: str
    authority_version: str
    occurrence_reference: str
    correlation: CodingSessionCorrelationReference | None
    causation_fingerprint: CodingSessionFingerprint | None
    binding_fingerprint: CodingSessionFingerprint | None
    transition_fingerprint: CodingSessionFingerprint
    idempotency_key: str
    previous_fact_fingerprint: CodingSessionFingerprint | None
    fact_fingerprint: CodingSessionFingerprint

    @classmethod
    def create(
        cls, request: FencingTransitionRequest, generation: int,
        previous: CodingSessionFingerprint | None,
    ) -> FencingGenerationFact:
        value = FencingGeneration(generation)
        semantic = (
            request.scope, value, request.ownership_identity, request.authority_identity,
            request.authority_version, request.occurrence_reference, request.correlation,
            request.causation_fingerprint, request.binding_fingerprint, request.fingerprint,
            request.idempotency_key, previous,
        )
        return cls(
            request.scope, value, request.ownership_identity, request.authority_identity,
            request.authority_version, request.occurrence_reference, request.correlation,
            request.causation_fingerprint, request.binding_fingerprint, request.fingerprint,
            request.idempotency_key, previous, CodingSessionFingerprint.from_content(semantic),
        )


@dataclass(frozen=True, slots=True)
class FencingTokenV1:
    scope: FencingScope
    generation: FencingGeneration
    ownership_identity: CodingSessionLeaseFactIdentity
    authority_identity: str
    authority_version: str
    occurrence_reference: str
    correlation: CodingSessionCorrelationReference | None
    causation_fingerprint: CodingSessionFingerprint | None
    binding_fingerprint: CodingSessionFingerprint | None
    token_fingerprint: CodingSessionFingerprint
    version: str = FENCING_TOKEN_VERSION

    @classmethod
    def from_fact(cls, fact: FencingGenerationFact) -> FencingTokenV1:
        semantic = (
            FENCING_TOKEN_VERSION, fact.scope, fact.generation, fact.ownership_identity,
            fact.authority_identity, fact.authority_version, fact.occurrence_reference,
            fact.correlation, fact.causation_fingerprint, fact.binding_fingerprint,
        )
        return cls(
            fact.scope, fact.generation, fact.ownership_identity, fact.authority_identity,
            fact.authority_version, fact.occurrence_reference, fact.correlation,
            fact.causation_fingerprint, fact.binding_fingerprint,
            CodingSessionFingerprint.from_content(semantic),
        )


@dataclass(frozen=True, slots=True)
class FencingValidationResult:
    state: FencingValidationState
    presented_generation: FencingGeneration | None
    latest_generation: FencingGeneration | None
    fencing_required: bool
    diagnostics: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.fencing_required or self.state is FencingValidationState.VALID


@dataclass(frozen=True, slots=True)
class FencingAuthorityHealth:
    store_available: bool
    schema_compatible: bool
    monotonicity_integrity: bool
    latest_generation_readable: bool
    token_validation_available: bool
    end_to_end_enforced: bool = False


class FencingGenerationStore(Protocol):
    def transition(self, request: FencingTransitionRequest) -> FencingGenerationFact: ...
    def latest(self, scope: FencingScope) -> FencingGenerationFact | None: ...
    def replay(self, scope: FencingScope) -> tuple[FencingGenerationFact, ...]: ...
    def health(self, scope: FencingScope | None = None) -> FencingAuthorityHealth: ...


class FencingAuthority:
    def __init__(self, store: FencingGenerationStore) -> None:
        self._store = store

    def transition(self, request: FencingTransitionRequest) -> FencingTokenV1:
        return FencingTokenV1.from_fact(self._store.transition(request))

    def validate(
        self, token: FencingTokenV1 | None, *, scope: FencingScope,
        ownership_identity: CodingSessionLeaseFactIdentity | None,
        authority_identity: str, operation: FencingOperationClass,
        binding_fingerprint: CodingSessionFingerprint | None = None,
    ) -> FencingValidationResult:
        required = operation.fencing_required
        if not required and token is None:
            return FencingValidationResult(FencingValidationState.VALID, None, None, False, ())
        if token is None:
            return FencingValidationResult(FencingValidationState.UNAVAILABLE, None, None, required, ("fencing-unavailable",))
        if token.scope != scope or token.ownership_identity != ownership_identity or token.authority_identity != authority_identity or token.authority_version != FENCING_AUTHORITY_VERSION or token.binding_fingerprint != binding_fingerprint:
            return FencingValidationResult(FencingValidationState.MISMATCHED, token.generation, None, required, ("fencing-mismatched",))
        try:
            latest = self._store.latest(scope)
        except FencingStoreError:
            return FencingValidationResult(FencingValidationState.UNAVAILABLE, token.generation, None, required, ("fencing-unavailable",))
        if latest is None:
            return FencingValidationResult(FencingValidationState.UNAVAILABLE, token.generation, None, required, ("fencing-unavailable",))
        expected = FencingTokenV1.from_fact(latest)
        if token.token_fingerprint != CodingSessionFingerprint.from_content((token.version, token.scope, token.generation, token.ownership_identity, token.authority_identity, token.authority_version, token.occurrence_reference, token.correlation, token.causation_fingerprint, token.binding_fingerprint)):
            return FencingValidationResult(FencingValidationState.INVALID, token.generation, latest.generation, required, ("fencing-invalid",))
        if token.generation.value < latest.generation.value:
            return FencingValidationResult(FencingValidationState.STALE, token.generation, latest.generation, required, ("fencing-stale",))
        if token.generation.value > latest.generation.value or token.token_fingerprint != expected.token_fingerprint:
            return FencingValidationResult(FencingValidationState.INVALID, token.generation, latest.generation, required, ("fencing-invalid",))
        return FencingValidationResult(FencingValidationState.VALID, token.generation, latest.generation, required, ())
