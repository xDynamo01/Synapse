"""Explicit, opt-in local Composition Root for the concrete Windows Sandbox driver."""

from .windows import (
    WindowsCapabilityClassification,
    WindowsCompositionCapabilityFact,
    WindowsCompositionConfig,
    WindowsCompositionDependencies,
    WindowsExecutionProfileV1,
    WindowsExecutionReadinessV1,
    WindowsIsolationLevel,
    WindowsLocalComposition,
    WindowsLocalCompositionHealth,
    build_windows_sandbox_driver,
)

__all__ = [
    "WindowsCapabilityClassification",
    "WindowsCompositionCapabilityFact",
    "WindowsCompositionConfig",
    "WindowsCompositionDependencies",
    "WindowsExecutionProfileV1",
    "WindowsExecutionReadinessV1",
    "WindowsIsolationLevel",
    "WindowsLocalComposition",
    "WindowsLocalCompositionHealth",
    "build_windows_sandbox_driver",
]
