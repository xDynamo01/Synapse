"""Pure validation errors for Deployment Runtime contracts."""


class DeploymentValidationError(ValueError):
    """Base class for invalid provider-neutral deployment facts."""


class InvalidDeploymentIdentity(DeploymentValidationError):
    pass


class InvalidDeploymentReference(DeploymentValidationError):
    pass


class InvalidDeploymentMetadata(DeploymentValidationError):
    pass


class InvalidDeploymentEnvironment(DeploymentValidationError):
    pass


class InvalidDeploymentTarget(DeploymentValidationError):
    pass


class InvalidDeploymentRevision(DeploymentValidationError):
    pass


class InvalidDeploymentArtifactReference(DeploymentValidationError):
    pass


class InvalidDeploymentIntent(DeploymentValidationError):
    pass


class InvalidDeploymentAttemptBinding(DeploymentValidationError):
    pass


class DeploymentTransitionError(DeploymentValidationError):
    """Base class for rejected pure state transitions."""


class InvalidDeploymentTransition(DeploymentTransitionError):
    pass


class DeploymentStateMismatch(DeploymentTransitionError):
    pass


class MissingDeploymentTransitionReference(DeploymentTransitionError):
    pass


class ContradictoryDeploymentTransition(DeploymentTransitionError):
    pass


class InvalidRolloutProgression(DeploymentTransitionError):
    pass


class InvalidRollbackProgression(DeploymentTransitionError):
    pass


class DeploymentPersistenceError(RuntimeError):
    """Base class for durable Deployment journal failures."""


class DeploymentPersistenceUnavailable(DeploymentPersistenceError):
    pass


class DeploymentSchemaIncompatible(DeploymentPersistenceError):
    pass


class DeploymentSequenceConflict(DeploymentPersistenceError):
    pass


class DeploymentSequenceGap(DeploymentPersistenceError):
    pass


class DeploymentEventContradiction(DeploymentPersistenceError):
    pass


class DeploymentPersistenceCorrupt(DeploymentPersistenceError):
    pass


class DeploymentReplayFailed(DeploymentPersistenceError):
    pass


class DeploymentFencingError(RuntimeError):
    """Base class for Deployment-owned fencing authority failures."""


class DeploymentFencingConflict(DeploymentFencingError):
    pass


class DeploymentFencingIntegrityError(DeploymentFencingError):
    pass


class DeploymentFencingUnavailable(DeploymentFencingError):
    pass


class DeploymentIdempotencyContradiction(DeploymentFencingError):
    pass


class DeploymentIdempotencyUnavailable(DeploymentFencingError):
    pass
