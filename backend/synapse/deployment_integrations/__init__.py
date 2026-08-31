"""Consumer-owned Deployment authorization integration."""

from .custody import DeploymentCustodyFactsAdapter
from .governance import (
    AuthorizationDecisionProjection,
    AuthorizationEvidenceV1,
    AuthorizationIntent,
    AuthorizationProjectionRegistry,
    DeploymentGovernanceAdapter,
    DeploymentOperationIntentV1,
    PromotionAuthorizationIntentV1,
    RollbackAuthorizationIntentV1,
    RolloutAuthorizationIntentV1,
    bind_authorization_event,
    project_authority_decision,
)
from .local_apply import (
    CurrentDeploymentApplyAuthorizationPort,
    LocalApplyOrchestrator,
    SandboxLocalApplyPort,
)
from .local_rollback import (
    CurrentRollbackAuthorizationPort,
    LocalRollbackOrchestrator,
    RollbackObserverPort,
    SandboxRollbackStartPort,
)
from .local_verification import LocalIndependentVerificationFlow
from .sandbox_handoff import (
    DeploymentSandboxWindowsHandoffAdapter,
    DeploymentSandboxWindowsHandoffV1,
    DeploymentWindowsProcessApplyAdapter,
    DeploymentWindowsProcessBindingV1,
    WindowsProcessStartPort,
)

__all__ = [
    "AuthorizationDecisionProjection",
    "AuthorizationEvidenceV1",
    "AuthorizationIntent",
    "AuthorizationProjectionRegistry",
    "DeploymentGovernanceAdapter",
    "DeploymentCustodyFactsAdapter",
    "DeploymentOperationIntentV1",
    "PromotionAuthorizationIntentV1",
    "RollbackAuthorizationIntentV1",
    "RolloutAuthorizationIntentV1",
    "bind_authorization_event",
    "project_authority_decision",
    "DeploymentSandboxWindowsHandoffAdapter",
    "DeploymentSandboxWindowsHandoffV1",
    "DeploymentWindowsProcessApplyAdapter",
    "DeploymentWindowsProcessBindingV1",
    "WindowsProcessStartPort",
    "CurrentDeploymentApplyAuthorizationPort",
    "LocalApplyOrchestrator",
    "SandboxLocalApplyPort",
    "LocalIndependentVerificationFlow",
    "LocalRollbackOrchestrator",
    "RollbackObserverPort",
    "SandboxRollbackStartPort",
    "CurrentRollbackAuthorizationPort",
]
