from __future__ import annotations

from pathlib import Path

from synapse.core.exceptions import ValidationError

_RESOURCE_URI_PREFIX = "resource://"


def packaged_resources_root() -> Path:
    return Path(__file__).resolve().parents[1] / "resources"


def package_resource_reference(namespace: str, path: Path) -> str:
    root = (packaged_resources_root() / namespace).resolve()
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError:
        raise ValidationError("Package resource is outside the requested namespace.") from None
    return f"{_RESOURCE_URI_PREFIX}{namespace}/{relative.as_posix()}"


def resolve_package_resource_reference(reference: str, namespace: str) -> Path | None:
    prefix = f"{_RESOURCE_URI_PREFIX}{namespace}/"
    if not reference.startswith(prefix):
        return None
    relative_value = reference.removeprefix(prefix)
    relative = Path(relative_value)
    if not relative_value or relative.is_absolute() or ".." in relative.parts:
        raise ValidationError("Invalid package resource reference.")
    root = (packaged_resources_root() / namespace).resolve()
    resolved = (root / relative).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        raise ValidationError("Package resource escapes its namespace.") from None
    return resolved
