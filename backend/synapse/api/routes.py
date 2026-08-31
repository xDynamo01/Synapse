"""Compatibility import for the canonical API router registry.

No handlers or runtime composition belong in this module.
"""

from synapse.api.router_registry import router

__all__ = ["router"]
