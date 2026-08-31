from synapse.core.exceptions import SynapseError


class DesktopAutomationError(SynapseError):
    code = "desktop_automation_error"


class ProviderUnavailable(DesktopAutomationError):
    code = "desktop_provider_unavailable"


class TargetNotFound(DesktopAutomationError):
    code = "desktop_target_not_found"


class ActionFailed(DesktopAutomationError):
    code = "desktop_action_failed"


class VerificationFailed(DesktopAutomationError):
    code = "desktop_verification_failed"


class AutomationDenied(DesktopAutomationError):
    code = "desktop_automation_denied"


class AutomationCancelled(DesktopAutomationError):
    code = "desktop_automation_cancelled"
