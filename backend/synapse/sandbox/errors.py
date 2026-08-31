"""Safe errors for the pure Sandbox domain foundation."""


class SandboxDomainError(ValueError):
    """Base error whose representation never includes rejected input."""

    code = "sandbox_domain_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class InvalidSandboxModel(SandboxDomainError):
    code = "invalid_sandbox_model"


class InvalidSandboxIdentity(SandboxDomainError):
    code = "invalid_sandbox_identity"


class SandboxCanonicalizationError(SandboxDomainError):
    code = "sandbox_canonicalization_error"


class UnsupportedSandboxFormat(SandboxDomainError):
    code = "unsupported_sandbox_format"


class SandboxInvariantViolation(SandboxDomainError):
    code = "sandbox_invariant_violation"


class InvalidAdmissionFacts(InvalidSandboxModel):
    code = "invalid_admission_facts"


class InvalidAdmissionPolicy(InvalidSandboxModel):
    code = "invalid_admission_policy"


class InvalidAdmissionDecision(InvalidSandboxModel):
    code = "invalid_admission_decision"


class InvalidExecutionPlan(InvalidSandboxModel):
    code = "invalid_execution_plan"

    def __init__(self, diagnostics: tuple[str, ...]) -> None:
        super().__init__("execution plan is structurally invalid")
        self.diagnostics = diagnostics


class InvalidCapabilityGrantSet(InvalidSandboxModel):
    code = "invalid_capability_grant_set"


class InvalidFilesystemBoundary(InvalidSandboxModel):
    code = "invalid_filesystem_boundary"


class InvalidNetworkBoundary(InvalidSandboxModel):
    code = "invalid_network_boundary"


class InvalidProcessBoundary(InvalidSandboxModel):
    code = "invalid_process_boundary"


class InvalidResourceLimitBoundary(InvalidSandboxModel):
    code = "invalid_resource_limit_boundary"


class InvalidSecretsBoundary(InvalidSandboxModel):
    code = "invalid_secrets_boundary"


class InvalidMaterialization(InvalidSandboxModel):
    code = "invalid_materialization"

    def __init__(self, diagnostics: str | tuple[str, ...]) -> None:
        super().__init__("sandbox materialization is structurally invalid")
        self.diagnostics = (diagnostics,) if isinstance(diagnostics, str) else diagnostics


class InvalidRuntimeSupervision(InvalidSandboxModel):
    code = "invalid_runtime_supervision"

    def __init__(self, diagnostics: str | tuple[str, ...]) -> None:
        super().__init__("sandbox runtime supervision is structurally invalid")
        self.diagnostics = (diagnostics,) if isinstance(diagnostics, str) else diagnostics


class InvalidCancellation(InvalidSandboxModel):
    code = "invalid_cancellation"

    def __init__(self, diagnostics: str | tuple[str, ...]) -> None:
        super().__init__("sandbox cancellation is structurally invalid")
        self.diagnostics = (diagnostics,) if isinstance(diagnostics, str) else diagnostics


class InvalidResultMaterialization(InvalidSandboxModel):
    code = "invalid_result_materialization"

    def __init__(self, diagnostics: str | tuple[str, ...]) -> None:
        super().__init__("sandbox result materialization is structurally invalid")
        self.diagnostics = (diagnostics,) if isinstance(diagnostics, str) else diagnostics


class SandboxPersistenceError(SandboxDomainError):
    """Safe base error for Slice 16 persistence failures."""


class SandboxPersistenceConflict(SandboxPersistenceError):
    pass


class SandboxPersistenceCorrupt(SandboxPersistenceError):
    pass


class SandboxPersistenceRecordNotFound(SandboxPersistenceError):
    pass


class SandboxPersistenceVersionUnsupported(SandboxPersistenceError):
    pass


class SandboxPersistenceMigrationMismatch(SandboxPersistenceError):
    pass


class SandboxPersistenceUnavailable(SandboxPersistenceError):
    pass
