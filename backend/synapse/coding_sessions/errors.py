"""Safe typed errors for the Coding Sessions foundation."""


class CodingSessionDomainError(ValueError):
    """Base error whose message never includes rejected values."""


class InvalidCodingSessionIdentity(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session identity is invalid")


class InvalidCodingSessionReference(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session reference is invalid")


class CodingSessionCanonicalizationError(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session value is not canonically encodable")


class CodingSessionVersionMismatch(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session version is unsupported")


class CodingSessionFingerprintMismatch(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session fingerprint does not correspond")


class InvalidCodingSessionCausalRevision(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session causal revision is invalid")


class InvalidCodingSessionLineage(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session lineage is invalid")


class InvalidCodingSessionCorrespondence(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session correspondence is invalid")


class CodingSessionPersistenceUnavailable(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session persistence is unavailable")


class CodingSessionPersistenceCorrupt(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session persisted record is corrupt")


class CodingSessionPersistenceMigrationMismatch(CodingSessionDomainError):
    def __init__(self) -> None:
        super().__init__("coding session persistence migration does not correspond")
