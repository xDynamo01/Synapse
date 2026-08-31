from enum import StrEnum


class SuiteStatus(StrEnum):
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class DefinitionStatus(StrEnum):
    DRAFT = "draft"
    FROZEN = "frozen"
    DEPRECATED = "deprecated"


class InputKind(StrEnum):
    INLINE = "inline"
    DATASET_ITEM_REFERENCE = "dataset_item_reference"


class DatasetCustodyKind(StrEnum):
    GOVERNED_LOCAL = "governed_local"


class SideEffectPolicy(StrEnum):
    NONE = "none"
    IDEMPOTENT = "idempotent"
    FORBIDDEN = "forbidden"


class RunStatus(StrEnum):
    CREATED = "created"
    VALIDATING = "validating"
    BLOCKED = "blocked"
    READY = "ready"
    RUNNING = "running"
    PARTIALLY_FAILED = "partially_failed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INVALID = "invalid"
    POLICY_DENIED = "policy_denied"


class ResultStatus(StrEnum):
    VALID = "valid"
    INFRASTRUCTURE_FAILED = "infrastructure_failed"
    INVALID = "invalid"
    POLICY_DENIED = "policy_denied"
    CANCELLED = "cancelled"


class ScoreKind(StrEnum):
    BINARY = "binary"
    NUMERIC = "numeric"


class ScoreStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MISSING = "missing"


class Verdict(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"
    INVALID = "invalid"
    BLOCKED = "blocked"
    POLICY_DENIED = "policy_denied"


class BaselineStatus(StrEnum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


class ComparisonResult(StrEnum):
    IMPROVED = "improved"
    STABLE = "stable"
    REGRESSED = "regressed"
    INCOMPATIBLE = "incompatible"
    INSUFFICIENT_DATA = "insufficient_data"


class DeterminismMode(StrEnum):
    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"
