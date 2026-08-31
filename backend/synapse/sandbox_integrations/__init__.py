"""External adapters into the Sandbox boundary; no Composition Root wiring."""

from .skills_handoff import (
    SKILLS_SANDBOX_COMPATIBILITY_V1,
    SandboxSkillsHandoffAdapter,
    SandboxSkillsHandoffDiagnostic,
    SandboxSkillsHandoffDiagnosticCode,
    SandboxSkillsHandoffRequest,
    SandboxSkillsHandoffResult,
    SandboxSkillsHandoffStatus,
    SkillsSandboxCompatibility,
)

__all__ = [
    "SKILLS_SANDBOX_COMPATIBILITY_V1",
    "SandboxSkillsHandoffAdapter",
    "SandboxSkillsHandoffDiagnostic",
    "SandboxSkillsHandoffDiagnosticCode",
    "SandboxSkillsHandoffRequest",
    "SandboxSkillsHandoffResult",
    "SandboxSkillsHandoffStatus",
    "SkillsSandboxCompatibility",
]
