from __future__ import annotations

__all__ = ["RuntimeContainer", "create_runtime"]


def __getattr__(name: str):
    if name in __all__:
        from synapse.core.app import RuntimeContainer, create_runtime

        exports = {
            "RuntimeContainer": RuntimeContainer,
            "create_runtime": create_runtime,
        }
        return exports[name]
    raise AttributeError(name)
