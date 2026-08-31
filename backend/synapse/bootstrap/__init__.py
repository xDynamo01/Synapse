"""Canonical bootstrap surface for constructing Synapse applications."""

from synapse.bootstrap.application import Application, build_application, create_runtime
from synapse.bootstrap.bindings import (
    GlobalBindingActivationAuthority,
    GlobalBindingActivationState,
    GlobalBindingAvailability,
    GlobalBindingDeclaration,
    GlobalBindingId,
    GlobalBindingMode,
    GlobalBindingRequirement,
    canonical_global_binding_inventory,
)
from synapse.bootstrap.container import RuntimeContainer
from synapse.bootstrap.lifecycle import LifecycleManager

__all__ = [
    "LifecycleManager",
    "Application",
    "GlobalBindingActivationAuthority",
    "GlobalBindingActivationState",
    "GlobalBindingAvailability",
    "GlobalBindingDeclaration",
    "GlobalBindingId",
    "GlobalBindingMode",
    "GlobalBindingRequirement",
    "RuntimeContainer",
    "build_application",
    "canonical_global_binding_inventory",
    "create_runtime",
]
