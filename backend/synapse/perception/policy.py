from __future__ import annotations

from typing import Any

from synapse.core.data_dir import DataDir
from synapse.core.exceptions import ValidationError
from synapse.core.serialization import load_structured_file

DEFAULT_PERCEPTION_POLICY: dict[str, Any] = {
    "enabled": True,
    "allowed_sources": [
        "voice",
        "audio",
        "vision",
        "screen",
        "camera",
        "system",
        "interaction",
        "test",
    ],
    "max_signal_bytes": 262_144,
    "signal_retention_hours": 24,
    "observation_retention_days": 30,
    "raw_visual_retention_minutes": 15,
    "persist_transcripts": False,
    "screenshots_enabled": True,
    "camera_enabled": False,
    "ocr_enabled": False,
    "persist_raw_visual": False,
    "acoustic_features_enabled": True,
    "require_approval_for_sensitive_capture": True,
    "sensitive_applications": [],
    "sensitive_window_patterns": ["private", "incognito", "password"],
    "sensitive_regions": [],
    "default_fusion_window_seconds": 15,
}


class PerceptionPolicyRuntime:
    def __init__(self, data_dir: DataDir) -> None:
        self.data_dir = data_dir

    def load(self) -> dict[str, Any]:
        path = self.data_dir.resolve("config/perception_policy.yaml")
        raw = load_structured_file(path) if path.exists() else {}
        policy = dict(DEFAULT_PERCEPTION_POLICY)
        policy.update(raw.get("perception", raw))
        self.validate(policy)
        return policy

    @staticmethod
    def validate(policy: dict[str, Any]) -> None:
        for key in (
            "max_signal_bytes",
            "signal_retention_hours",
            "observation_retention_days",
            "raw_visual_retention_minutes",
        ):
            if int(policy.get(key, 0)) < 0:
                raise ValidationError(f"Invalid perception policy value: {key}")
        if not isinstance(policy.get("allowed_sources"), list):
            raise ValidationError("perception.allowed_sources must be a list")
