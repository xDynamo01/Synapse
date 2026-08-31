"""Closed, orthogonal Repository Runtime state vocabularies."""

from enum import StrEnum


class RepositoryHeadKind(StrEnum):
    NAMED_BRANCH = "named_branch"
    DETACHED = "detached"
    UNBORN_BRANCH = "unborn_branch"
    ABSENT = "absent"


class RepositoryIndexPresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    NOT_OBSERVED = "not_observed"


class RepositoryWorkspaceStatus(StrEnum):
    CLEAN = "clean"
    DIRTY = "dirty"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


class RepositoryObservationCompleteness(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    NOT_REQUIRED = "not_required"


class RepositoryPresence(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class RepositoryEntryStatus(StrEnum):
    UNCHANGED = "unchanged"
    MODIFIED = "modified"
    ADDED = "added"
    DELETED = "deleted"
    CONFLICTED = "conflicted"
    UNKNOWN = "unknown"


class RepositoryObservationDimension(StrEnum):
    REPOSITORY = "repository"
    CHECKOUT = "checkout"
    WORKTREE = "worktree"
    HEAD = "head"
    INDEX = "index"
    WORKSPACE = "workspace"
    PATHS = "paths"
    TOPOLOGY = "topology"
    PLATFORM = "platform"


class RepositoryCorrespondence(StrEnum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNKNOWN = "unknown"


class RepositoryObservationOutcome(StrEnum):
    SATISFIED = "satisfied"
    CONTRADICTORY = "contradictory"
    MISMATCH = "mismatch"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


class RepositoryGitTracking(StrEnum):
    TRACKED = "tracked"
    UNTRACKED = "untracked"
    IGNORED = "ignored"
    UNKNOWN = "unknown"


class RepositoryMaterialRole(StrEnum):
    SOURCE = "source"
    GENERATED = "generated"
    ARTIFACT = "artifact"
    RUNTIME_STATE = "runtime_state"
    UNKNOWN = "unknown"


class RepositorySensitivity(StrEnum):
    NORMAL = "normal"
    SECRET_RISK = "secret_risk"
    PRIVATE = "private"
    UNKNOWN = "unknown"


class RepositoryTopology(StrEnum):
    REGULAR = "regular"
    SUBMODULE = "submodule"
    NESTED_REPOSITORY = "nested_repository"
    SPARSE_EXCLUDED = "sparse_excluded"
    UNKNOWN = "unknown"


class RepositoryPlatformKind(StrEnum):
    WINDOWS = "windows"
    POSIX = "posix"
    OTHER = "other"


class RepositoryCaseSensitivity(StrEnum):
    SENSITIVE = "sensitive"
    INSENSITIVE = "insensitive"


class RepositoryUnicodeNormalization(StrEnum):
    PRESERVE = "preserve"
    NFC = "nfc"
    NFD = "nfd"


class RepositoryResourceKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    LINK = "link"
    UNKNOWN = "unknown"


class RepositoryContentKind(StrEnum):
    BINARY = "binary"
    TEXT = "text"
    UNKNOWN = "unknown"


class RepositorySizeClass(StrEnum):
    EMPTY = "empty"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    UNKNOWN = "unknown"


class RepositoryLinkPolicy(StrEnum):
    PRESERVE = "preserve"
    REJECT = "reject"


class RepositorySnapshotDimension(StrEnum):
    REPOSITORY_METADATA = "repository_metadata"
    HEAD = "head"
    INDEX = "index"
    SOURCE_TREE = "source_tree"
    WORKSPACE = "workspace"
    PATH_CATALOG = "path_catalog"
    SPARSE_CHECKOUT = "sparse_checkout"


class RepositorySparseCheckoutState(StrEnum):
    DISABLED = "disabled"
    ENABLED = "enabled"
    UNKNOWN = "unknown"


class RepositoryChangeType(StrEnum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    COPIED = "copied"
    TYPE_CHANGED = "type_changed"
    CLASSIFICATION_CHANGED = "classification_changed"
    METADATA_CHANGED = "metadata_changed"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"


class RepositoryChangeAxisState(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class RepositoryMutationOperationKind(StrEnum):
    CREATE = "create"
    REPLACE = "replace"
    APPEND = "append"
    DELETE = "delete"
    MOVE = "move"
    COPY = "copy"
    METADATA_UPDATE = "metadata_update"
    CLASSIFICATION_UPDATE = "classification_update"


class RepositoryMutationScope(StrEnum):
    RESOURCE = "resource"
    CONTENT = "content"
    METADATA = "metadata"
    CLASSIFICATION = "classification"


class RepositoryCollisionBehavior(StrEnum):
    FAIL_IF_EXISTS = "fail_if_exists"
    FAIL_IF_MISSING = "fail_if_missing"
    REPLACE_IF_MATCHES = "replace_if_matches"
    CREATE_ONLY = "create_only"
    EXPLICIT_OVERWRITE = "explicit_overwrite"


class RepositoryRecoveryRequirement(StrEnum):
    REQUIRED = "required"
    NOT_REQUIRED = "not_required"


class RepositoryMutationPreconditionKind(StrEnum):
    REPOSITORY_IDENTITY = "repository_identity"
    CHECKOUT_IDENTITY = "checkout_identity"
    WORKTREE_IDENTITY = "worktree_identity"
    HEAD_STATE = "head_state"
    BRANCH_STATE = "branch_state"
    INDEX_STATE = "index_state"
    WORKSPACE_STATE = "workspace_state"
    PATH_STATE = "path_state"
    COMPLETENESS = "completeness"
    TOPOLOGY_BOUNDARY = "topology_boundary"
    COLLISION_STATE = "collision_state"


class RepositoryPresenceExpectation(StrEnum):
    PRESENT = "present"
    ABSENT = "absent"
    NOT_APPLICABLE = "not_applicable"


class RepositoryAuthorizationPathScope(StrEnum):
    EXACT = "exact"
    PREFIX = "prefix"
    RECURSIVE = "recursive"
    WILDCARD = "wildcard"


class RepositoryAuthorizationFactEffect(StrEnum):
    ASSERTED = "asserted"
    REVOKED = "revoked"


class RepositoryAuthorizationFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class RepositoryAuthorizationOutcome(StrEnum):
    SATISFIED = "satisfied"
    PARTIAL = "partial"
    MISMATCH = "mismatch"
    CONFLICT = "conflict"
    INCOMPLETE = "incomplete"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    EXPIRED = "expired"


class RepositoryRestorePointCoverageKind(StrEnum):
    CREATED_ABSENCE = "created_absence"
    REPLACED_CONTENT = "replaced_content"
    DELETED_CONTENT = "deleted_content"
    MOVE_SOURCE = "move_source"
    MOVE_DESTINATION = "move_destination"
    METADATA = "metadata"
    HEAD_STATE = "head_state"
    BRANCH_STATE = "branch_state"
    INDEX_STATE = "index_state"
    UNTRACKED_COLLISION = "untracked_collision"
    TOPOLOGY_BOUNDARY = "topology_boundary"


class RepositoryRestorePointDimension(StrEnum):
    CONTENT = "content"
    METADATA = "metadata"
    HEAD = "head"
    BRANCH = "branch"
    INDEX = "index"
    UNTRACKED = "untracked"
    TOPOLOGY = "topology"


class RepositoryRestorePointMaterialHandling(StrEnum):
    INCLUDE = "include"
    EXCLUDE = "exclude"
    BLOCK = "block"


class RepositoryRestorePointVerificationState(StrEnum):
    VERIFIED = "verified"
    INCOMPLETE = "incomplete"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    CORRUPT = "corrupt"
    OVERSIZED = "oversized"
    SENSITIVE_CONTENT_BLOCKED = "sensitive_content_blocked"


class RepositoryMutationApplicationOutcome(StrEnum):
    NOT_STARTED = "not_started"
    PRECONDITION_FAILED = "precondition_failed"
    APPLIED = "applied"
    PARTIALLY_APPLIED = "partially_applied"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CLEANUP_REQUIRED = "cleanup_required"
    CLEANUP_FAILED = "cleanup_failed"
    MANUAL_INTERVENTION = "manual_intervention"


class RepositoryMutationPreconditionOutcome(StrEnum):
    SATISFIED = "satisfied"
    STALE = "stale"
    MISMATCH = "mismatch"
    UNAVAILABLE = "unavailable"


class RepositoryMutationSideEffect(StrEnum):
    NONE = "none"
    DECLARED = "declared"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    OUT_OF_SCOPE = "out_of_scope"


class RepositoryMutationCleanupRequirement(StrEnum):
    NOT_REQUIRED = "not_required"
    REQUIRED = "required"
