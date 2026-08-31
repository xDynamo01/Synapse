from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, overload

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.serialization import dump_structured_file, load_structured_file


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    trusted: bool
    permissions: list[str] = field(default_factory=list)
    revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class DeviceRegistry:
    def __init__(self, data_dir: DataDir, event_bus: EventBus):
        self.data_dir = data_dir
        self.event_bus = event_bus

    def register_device(
        self,
        device_id: str,
        trusted: bool = False,
        permissions: list[str] | None = None,
        revoked: bool = False,
        metadata: dict[str, Any] | None = None,
        actor_id: str = "system",
    ) -> DeviceRecord:
        existing = self.get_device(device_id, missing_ok=True)
        now = datetime.now(UTC).isoformat()
        record = DeviceRecord(
            device_id=device_id,
            trusted=trusted and not revoked,
            permissions=permissions or [],
            revoked=revoked,
            metadata=metadata or {},
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._delete_existing(device_id)
        self._write(record)
        self.event_bus.emit("device.registered", actor_id, asdict(record))
        return record

    def revoke_device(self, device_id: str, actor_id: str = "system") -> DeviceRecord:
        existing = self.get_device(device_id)
        record = DeviceRecord(
            device_id=existing.device_id,
            trusted=False,
            permissions=existing.permissions,
            revoked=True,
            metadata=existing.metadata,
            created_at=existing.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._delete_existing(device_id)
        self._write(record)
        self.event_bus.emit("device.revoked", actor_id, asdict(record))
        return record

    def list_devices(self) -> list[DeviceRecord]:
        records: list[DeviceRecord] = []
        for state in ("trusted", "untrusted", "revoked"):
            directory = self.data_dir.resolve(f"devices/{state}")
            for path in sorted(directory.glob("*.yaml")):
                records.append(self._read(path))
        return sorted(records, key=lambda record: record.device_id)

    @overload
    def get_device(self, device_id: str, missing_ok: Literal[False] = False) -> DeviceRecord: ...

    @overload
    def get_device(self, device_id: str, missing_ok: Literal[True]) -> DeviceRecord | None: ...

    def get_device(self, device_id: str, missing_ok: bool = False) -> DeviceRecord | None:
        for state in ("trusted", "untrusted", "revoked"):
            path = self.data_dir.resolve(f"devices/{state}/{device_id}.yaml")
            if path.exists():
                return self._read(path)
        if missing_ok:
            return None
        raise NotFound(f"Device not found: {device_id}")

    def _state_dir(self, record: DeviceRecord) -> str:
        if record.revoked:
            return "revoked"
        return "trusted" if record.trusted else "untrusted"

    def _path(self, record: DeviceRecord) -> Path:
        return self.data_dir.resolve(f"devices/{self._state_dir(record)}/{record.device_id}.yaml")

    def _write(self, record: DeviceRecord) -> None:
        dump_structured_file(self._path(record), asdict(record))

    def _delete_existing(self, device_id: str) -> None:
        for state in ("trusted", "untrusted", "revoked"):
            path = self.data_dir.resolve(f"devices/{state}/{device_id}.yaml")
            if path.exists():
                path.unlink()

    @staticmethod
    def _read(path: Path) -> DeviceRecord:
        raw = load_structured_file(path)
        return DeviceRecord(**raw)
