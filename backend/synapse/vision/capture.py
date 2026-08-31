from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from mss import MSS
from mss.tools import to_png
from PIL import Image

from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.observability.redaction import redact
from synapse.perception.policy import PerceptionPolicyRuntime
from synapse.vision.errors import (
    CaptureSourceNotFound,
    InvalidImage,
    ScreenshotPermissionDenied,
    UnsupportedImageFormat,
)
from synapse.vision.models import CaptureSource, VisionInput


class ScreenCaptureProvider(Protocol):
    provider_id: str

    def list_sources(self) -> list[CaptureSource]: ...
    def capture(
        self, source_id: str, region: dict[str, int] | None = None
    ) -> tuple[bytes, dict[str, Any]]: ...
    def health(self) -> dict[str, Any]: ...


class MSSScreenCaptureProvider:
    provider_id = "mss_local"

    def list_sources(self) -> list[CaptureSource]:
        try:
            with MSS() as grabber:
                return [
                    CaptureSource(
                        str(index),
                        "monitor",
                        f"Monitor {index}",
                        True,
                        {key: int(value) for key, value in monitor.items()},
                    )
                    for index, monitor in enumerate(grabber.monitors[1:], start=1)
                ]
        except Exception as exc:
            return [
                CaptureSource(
                    "primary", "monitor", "Primary monitor", False, {"error": type(exc).__name__}
                )
            ]

    def capture(
        self, source_id: str, region: dict[str, int] | None = None
    ) -> tuple[bytes, dict[str, Any]]:
        try:
            with MSS() as grabber:
                index = 1 if source_id == "primary" else int(source_id)
                if index < 1 or index >= len(grabber.monitors):
                    raise CaptureSourceNotFound(f"Capture source not found: {source_id}")
                monitor = dict(grabber.monitors[index])
                target = monitor
                if region:
                    target = {
                        "left": monitor["left"] + int(region["x"]),
                        "top": monitor["top"] + int(region["y"]),
                        "width": int(region["width"]),
                        "height": int(region["height"]),
                    }
                shot = grabber.grab(target)
                return cast(bytes, to_png(shot.rgb, shot.size)), {
                    "source_id": str(index),
                    "region": target,
                }
        except CaptureSourceNotFound:
            raise
        except Exception as exc:
            raise ScreenshotPermissionDenied(
                "Screen capture failed or was denied", details={"error": type(exc).__name__}
            ) from exc

    def health(self) -> dict[str, Any]:
        sources = self.list_sources()
        return {
            "provider": self.provider_id,
            "state": "ready" if any(item.available for item in sources) else "unavailable",
            "sources": len([item for item in sources if item.available]),
        }


class CaptureRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        policy: PerceptionPolicyRuntime,
        provider: ScreenCaptureProvider | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.policy = policy
        self.provider = provider or MSSScreenCaptureProvider()
        self._transient_directory = tempfile.TemporaryDirectory(prefix="synapse-vision-")
        self._transient_root = Path(self._transient_directory.name)
        self._transient_paths: dict[str, Path] = {}

    def list_sources(self) -> list[CaptureSource]:
        return self.provider.list_sources()

    def capture_screenshot(
        self,
        *,
        owner: str,
        source_id: str = "primary",
        region: dict[str, int] | None = None,
        policy_context: dict[str, Any] | None = None,
    ) -> VisionInput:
        policy = self.policy.load()
        context = redact(policy_context or {})
        self._authorize(context, policy)
        self.events.emit(
            "vision.capture_started", owner, {"source_id": source_id, "region": region}
        )
        payload, metadata = self.provider.capture(source_id, region)
        image = self.store_image(payload, "image/png", "screenshot", owner, context, metadata)
        self.events.emit(
            "vision.capture_completed",
            owner,
            {"input_id": image.id, "checksum": image.checksum, "source_type": image.source_type},
        )
        return image

    def store_image(
        self,
        payload: bytes,
        mime: str,
        source_type: str,
        owner: str,
        policy_context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> VisionInput:
        if len(payload) == 0 or len(payload) > 25 * 1024 * 1024:
            raise InvalidImage("Image is empty or exceeds 25 MiB")
        try:
            from io import BytesIO

            with Image.open(BytesIO(payload)) as decoded:
                decoded.verify()
            with Image.open(BytesIO(payload)) as decoded:
                width, height = decoded.size
                detected_mime = Image.MIME.get(decoded.format or "")
        except Exception as exc:
            raise InvalidImage("Image could not be decoded") from exc
        if detected_mime != mime:
            raise InvalidImage("Declared MIME does not match image content")
        identifier = str(uuid4())
        suffix = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}.get(mime)
        if not suffix:
            raise UnsupportedImageFormat("Unsupported image format")
        policy = self.policy.load()
        persist_raw = bool(policy.get("persist_raw_visual", False))
        path = (self._raw_root() if persist_raw else self._transient_root) / f"{identifier}{suffix}"
        path.write_bytes(payload)
        if not persist_raw:
            self._transient_paths[identifier] = path
        expires_at = None
        if persist_raw:
            expires_at = (
                datetime.now(UTC)
                + timedelta(minutes=int(policy["raw_visual_retention_minutes"]))
            ).isoformat()
        return VisionInput(
            id=identifier,
            image_reference=(
                path.relative_to(self.data_dir.root).as_posix()
                if persist_raw
                else f"transient:{identifier}"
            ),
            mime=mime,
            dimensions={"width": width, "height": height},
            checksum=hashlib.sha256(payload).hexdigest(),
            source_type=source_type,
            owner=owner,
            policy_context=redact(policy_context or {}),
            expires_at=expires_at,
            metadata=redact(metadata or {}),
            retention_class=("raw_media_explicit_only" if persist_raw else "transient_only"),
            persisted=persist_raw,
            provenance=[
                {
                    "source_type": source_type,
                    "source_identity": owner,
                    "policy": "perception_policy",
                    "persist_raw_visual": persist_raw,
                }
            ],
        )

    def resolve_path(self, image: VisionInput) -> Path:
        if image.image_reference.startswith("transient:"):
            return self._transient_paths.get(image.id, self._transient_root / "missing")
        return self.data_dir.resolve(image.image_reference)

    def delete_raw_asset(self, image: VisionInput) -> bool:
        path = self.resolve_path(image)
        existed = path.exists()
        path.unlink(missing_ok=True)
        self._transient_paths.pop(image.id, None)
        return existed

    def health(self) -> dict[str, Any]:
        return self.provider.health()

    def _authorize(self, context: dict[str, Any], policy: dict[str, Any]) -> None:
        if not policy.get("screenshots_enabled", False):
            raise ScreenshotPermissionDenied("Screenshots are disabled by policy")
        app = str(context.get("application", "")).lower()
        title = str(context.get("window_title", "")).lower()
        if app and app in {str(item).lower() for item in policy.get("sensitive_applications", [])}:
            raise ScreenshotPermissionDenied("Application is denied by visual privacy policy")
        if any(
            str(pattern).lower() in title for pattern in policy.get("sensitive_window_patterns", [])
        ):
            raise ScreenshotPermissionDenied("Window is denied by visual privacy policy")
        if (
            policy.get("require_approval_for_sensitive_capture", True)
            and context.get("sensitive") is True
            and context.get("approved") is not True
        ):
            raise ScreenshotPermissionDenied("Sensitive capture requires approval")

    def _raw_root(self) -> Path:
        root = self.data_dir.resolve("vision/raw")
        root.mkdir(parents=True, exist_ok=True)
        return root
