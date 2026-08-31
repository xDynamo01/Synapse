from .catalog import LegacyCatalogAdapter
from .errors import (
    SkillLegacyCompatibilityConflict,
    SkillLegacyCompatibilityError,
    SkillLegacyCompatibilityIncomplete,
    SkillLegacyCompatibilityInvalidMapping,
    SkillLegacyCompatibilityNotFound,
    SkillLegacyCompatibilityUnavailable,
)
from .lifecycle import LegacyLifecycleAdapter
from .models import (
    LegacyLifecycleView,
    LegacyLookupOutcome,
    LegacySkillListResult,
    LegacySkillLookup,
    LegacySkillLookupResult,
    LegacySkillView,
)

__all__ = [
    "LegacyCatalogAdapter",
    "LegacyLifecycleAdapter",
    "LegacyLifecycleView",
    "LegacyLookupOutcome",
    "LegacySkillListResult",
    "LegacySkillLookup",
    "LegacySkillLookupResult",
    "LegacySkillView",
    "SkillLegacyCompatibilityConflict",
    "SkillLegacyCompatibilityError",
    "SkillLegacyCompatibilityIncomplete",
    "SkillLegacyCompatibilityInvalidMapping",
    "SkillLegacyCompatibilityNotFound",
    "SkillLegacyCompatibilityUnavailable",
]
