from synapse.core.exceptions import NotFound, PermissionDenied, ValidationError


class MaintenanceError(ValidationError):
    pass


class MaintenanceNotFound(NotFound):
    pass


class MaintenanceConflict(MaintenanceError):
    pass


class MaintenancePlanExpired(MaintenanceError):
    pass


class MaintenanceApprovalRequired(PermissionDenied):
    pass
