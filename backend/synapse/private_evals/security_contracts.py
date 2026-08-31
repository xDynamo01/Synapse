"""The single consumer-owned projection port required by the architecture."""

from __future__ import annotations

from typing import Protocol

from .security import EvalSecuritySnapshot


class SecuritySnapshotReadPort(Protocol):
    """Return a safe Intelligence policy/trust snapshot for run preparation.

    No frozen contract exposes this complete, secret-free reproducibility projection.
    A future bootstrap adapter will construct it from canonical Intelligence state;
    the port neither authorizes egress nor registers assets.
    """

    def snapshot(
        self,
        project_id: str,
        asset_ids: tuple[str, ...],
        provider_ids: tuple[str, ...],
    ) -> EvalSecuritySnapshot: ...
