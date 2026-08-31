from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from synapse.observability.correlation import correlation_scope, new_correlation


class DesktopAuthorityError(Exception):
    def __init__(self, code: str, status_code: int) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class DesktopSession:
    session_id: str
    token: str
    project_id: str
    actor_id: str
    capabilities: tuple[str, ...]
    expires_at: datetime


class DesktopCommandAuthority:
    """Sidecar-lifetime authentication and narrow desktop command authorization."""

    SESSION_TTL = timedelta(minutes=15)
    COMMAND_CLOCK_SKEW = timedelta(minutes=5)
    CAPABILITIES = ("task.create",)

    def __init__(self, runtime: Any, launch_token: str) -> None:
        self.runtime = runtime
        self._launch_token = launch_token
        self._sessions: dict[str, DesktopSession] = {}
        self._ledger = runtime.data_dir.resolve("runtime/desktop-commands")
        self._ledger.mkdir(parents=True, exist_ok=True)

    def create_session(self, launch_token: str, project_id: str) -> DesktopSession:
        if not self._launch_token or not hmac.compare_digest(launch_token, self._launch_token):
            raise DesktopAuthorityError("invalid_launch_credential", 401)
        self.runtime.project_governance.projects.get(project_id)
        now = datetime.now(UTC)
        session = DesktopSession(
            session_id=secrets.token_urlsafe(18),
            token=secrets.token_urlsafe(32),
            project_id=project_id,
            actor_id=self.runtime.settings.default_actor_id,
            capabilities=self.CAPABILITIES,
            expires_at=now + self.SESSION_TTL,
        )
        self._sessions[session.token] = session
        self.runtime.events.emit(
            "desktop.session.created",
            session.actor_id,
            {"project_id": project_id, "session_id": session.session_id, "expires_at": session.expires_at.isoformat()},
        )
        return session

    def execute(self, token: str, envelope: dict[str, Any]) -> dict[str, Any]:
        session = self._authenticate(token)
        command_id = str(envelope["command_id"])
        command_type = str(envelope["command_type"])
        project_id = str(envelope["project_id"])
        session_id = str(envelope["session_id"])
        if session_id != session.session_id:
            raise DesktopAuthorityError("wrong_session", 403)
        if project_id != session.project_id:
            raise DesktopAuthorityError("wrong_project", 403)
        if command_type not in session.capabilities:
            raise DesktopAuthorityError("unauthorized_capability", 403)
        issued_at = datetime.fromisoformat(str(envelope["issued_at"]).replace("Z", "+00:00"))
        if abs(datetime.now(UTC) - issued_at) > self.COMMAND_CLOCK_SKEW:
            raise DesktopAuthorityError("stale_command", 401)

        fingerprint = hashlib.sha256(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        ledger_path = self._ledger / f"{command_id}.json"
        existing = self._read_ledger(ledger_path)
        if existing:
            if existing.get("fingerprint") != fingerprint:
                raise DesktopAuthorityError("command_id_conflict", 409)
            if existing.get("state") == "completed":
                return {**existing["result"], "replayed": True}
            raise DesktopAuthorityError("command_reconciliation_required", 409)

        reservation = {"command_id": command_id, "fingerprint": fingerprint, "state": "reserved"}
        try:
            with ledger_path.open("x", encoding="utf-8") as handle:
                json.dump(reservation, handle, sort_keys=True)
        except FileExistsError:
            raise DesktopAuthorityError("command_reconciliation_required", 409) from None

        try:
            result = self._execute_task_create(session, envelope)
            self._replace_ledger(ledger_path, {**reservation, "state": "completed", "result": result})
            return result
        except Exception:
            self._replace_ledger(ledger_path, {**reservation, "state": "reconciliation_required"})
            raise

    def _execute_task_create(self, session: DesktopSession, envelope: dict[str, Any]) -> dict[str, Any]:
        payload = envelope["payload"]
        agent_id = str(payload["agent_id"])
        self.runtime.agents.get(agent_id)
        context = self.runtime.context(
            actor_id=session.actor_id,
            actor_type="user",
            device_id=f"desktop:{session.session_id}",
        )
        correlation = new_correlation(
            "desktop.command",
            correlation_id=str(envelope["command_id"]),
            session_id=session.session_id,
            agent_id=agent_id,
        )
        with correlation_scope(correlation):
            task = self.runtime.tasks.create_task(
                context,
                title=str(payload["title"]),
                description=str(payload.get("description", "")),
                metadata={
                    "project_id": session.project_id,
                    "agent_id": agent_id,
                    "assigned_agent": agent_id,
                    "desktop_session_id": session.session_id,
                    "desktop_command_id": str(envelope["command_id"]),
                },
            )
            self.runtime.events.emit(
                "task.desktop_command_completed",
                session.actor_id,
                {
                    "project_id": session.project_id,
                    "session_id": session.session_id,
                    "command_id": str(envelope["command_id"]),
                    "command_type": "task.create",
                    "task_id": task.id,
                    "agent_id": agent_id,
                    "status": task.status,
                    "label": task.title,
                },
            )
        return {
            "command_id": str(envelope["command_id"]),
            "correlation_id": str(envelope["command_id"]),
            "project_id": session.project_id,
            "session_id": session.session_id,
            "status": "completed",
            "task": asdict(task),
            "replayed": False,
        }

    def _authenticate(self, token: str) -> DesktopSession:
        session = next(
            (item for key, item in self._sessions.items() if hmac.compare_digest(key, token)),
            None,
        )
        if session is None:
            raise DesktopAuthorityError("invalid_session_credential", 401)
        if datetime.now(UTC) >= session.expires_at:
            self._sessions.pop(session.token, None)
            raise DesktopAuthorityError("expired_session", 401)
        return session

    @staticmethod
    def _read_ledger(path: Path) -> dict[str, Any] | None:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _replace_ledger(path: Path, value: dict[str, Any]) -> None:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
