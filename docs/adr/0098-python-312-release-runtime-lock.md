# ADR 0098: Python 3.12 Release Runtime Lock

## Status

Accepted.

## Context

The first sidecar prototype inherited Python 3.14 from the developer machine,
which made release output non-deterministic and exposed compatibility warnings.
Development supports Python `>=3.12`, but release packaging needs a narrower,
tested runtime boundary.

## Decision

Lock desktop release builds to Python 3.12.x. Both backend and aggregate release
scripts require an explicit `-PythonPath` or `SYNAPSE_RELEASE_PYTHON`, execute
that interpreter to verify its exact version, and fail before modifying build
outputs when it is not 3.12.

The packaging dependency group contains PyInstaller and `tzdata`. The real
release manifest records Python version, resolved executable, PyInstaller
version, and a positive validation flag. Development launch remains unchanged
and may use the normal configured Python command.

No script downloads or globally installs Python. Environment provisioning is an
operator/build-machine responsibility; `.venv-release` is only a documented,
ignored local convention.

## Consequences

Accidental Python 3.14 release builds are blocked and release provenance is
visible. The initial validated runtime is Python 3.12.11. Exact patch selection,
dependency hashes, artifact signing, and clean-machine certification remain
future release engineering work.
