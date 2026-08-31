"""Compatibility adapter for the canonical bootstrap package.

New production code must import application construction from
``synapse.bootstrap``. This module intentionally contains no composition logic.
"""

from synapse.bootstrap.application import create_runtime
from synapse.bootstrap.container import RuntimeContainer

__all__ = ["RuntimeContainer", "create_runtime"]
