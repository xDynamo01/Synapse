from __future__ import annotations

import hashlib
from pathlib import Path

import synapse.audio as audio
import synapse.perception as perception
import synapse.speech_adapters as speech_adapters
import synapse.voice as voice
import synapse.voice_composition as voice_composition
from synapse.core.data_dir import DataDir
from synapse.perception.models import (
    MODALITIES,
    PerceptionArtifactKind,
    PerceptionBundleStatus,
    RetentionClass,
)
from synapse.perception.policy import DEFAULT_PERCEPTION_POLICY
from synapse.speech_adapters.execution import (
    EXECUTION_REQUEST_FORMAT,
    EXECUTION_RESULT_FORMAT,
)
from synapse.voice.frontend_events import (
    VOICE_FRONTEND_EVENT_V1,
    VoiceFrontendEventType,
    VoicePresentationState,
)
from synapse.voice.models import (
    VOICE_CONFIGURATION_POLICY_VERSION,
    VOICE_SETTINGS_SCHEMA_VERSION,
    VoiceSettings,
)
from synapse.voice.persistence_models import (
    VOICE_RECORD_FORMAT_V1,
    VOICE_SQLITE_SCHEMA_VERSION,
    VoiceCompleteness,
    VoicePersistenceState,
)
from synapse.voice.realtime import RealtimeVoiceState
from synapse.voice.sqlite_persistence import _MIGRATION_CHECKSUM
from synapse.voice_composition import (
    CapabilityLevel,
    OperationalCompletion,
    VoicePerceptionConfiguration,
    VoicePerceptionRuntimeBuilder,
)

from .support import SOURCE_ROOT, context_graph, cyclic_components
from .test_audio_speech_boundary import _runtime_context_graph

PACKAGE_MODULES = {
    "audio": (
        "__init__.py",
        "contracts.py",
        "devices.py",
        "errors.py",
        "ingestion.py",
        "models.py",
        "realtime_devices.py",
        "runtime.py",
    ),
    "voice": (
        "__init__.py",
        "frontend_events.py",
        "models.py",
        "perception.py",
        "persistence_contracts.py",
        "persistence_models.py",
        "realtime.py",
        "runtime.py",
        "sqlite_persistence.py",
        "vad.py",
    ),
    "perception": (
        "__init__.py",
        "errors.py",
        "models.py",
        "nonverbal.py",
        "policy.py",
        "runtime.py",
    ),
    "speech_adapters": (
        "__init__.py",
        "execution.py",
        "faster_whisper.py",
        "interfaces.py",
        "local_analysis.py",
        "models.py",
        "piper_tts.py",
        "registry.py",
        "runtime.py",
    ),
    "voice_composition": ("__init__.py", "conversation.py", "runtime.py"),
}

PUBLIC_EXPORT_FINGERPRINTS = {
    "audio": "e7fd24ed31a16781020490d21605b8afc46661ac67980693abdaf421c6320ef4",
    "perception": "ea631fa6b446714b8167a7e5d7abebb747e5c5939732e3126acf65e38a2cb45c",
    "speech_adapters": "285cc0b7aa0303c7072b605b4776ae1f58492d7a7e5903abd79a157bda2f88f4",
    "voice": "1c49860b236d2e8b8989347cdbf0a4c43f600fe1f79e5780b847786331e29fde",
    "voice_composition": "03882fb0a9c7e6ccc37a5be6bbf899a7bde7bbbbb42266533c6e704cf3f29e57",
}


class _NoSpeechClassifier:
    def is_speech(self, frame: bytes, sample_rate: int) -> bool:
        _ = frame, sample_rate
        return False


def _values(enum_type: type) -> tuple[str, ...]:
    return tuple(item.value for item in enum_type)


def test_frozen_module_inventory_and_public_exports() -> None:
    for package, expected in PACKAGE_MODULES.items():
        root = SOURCE_ROOT / package
        actual = tuple(sorted(path.relative_to(root).as_posix() for path in root.rglob("*.py")))
        assert actual == expected
    modules = {
        "audio": audio,
        "perception": perception,
        "speech_adapters": speech_adapters,
        "voice": voice,
        "voice_composition": voice_composition,
    }
    for name, module in modules.items():
        fingerprint = hashlib.sha256("\n".join(module.__all__).encode()).hexdigest()
        assert fingerprint == PUBLIC_EXPORT_FINGERPRINTS[name]


def test_frozen_versions_schema_and_migration_checksum() -> None:
    assert VOICE_RECORD_FORMAT_V1 == "voice-record-v1"
    assert VOICE_SQLITE_SCHEMA_VERSION == 1
    assert _MIGRATION_CHECKSUM == (
        "c614e9b17dfc27e3e43263f2a3332991be5a0b50f053d1161f944012a73c0c5f"
    )
    assert VOICE_FRONTEND_EVENT_V1 == "voice-frontend-event-v1"
    assert VOICE_SETTINGS_SCHEMA_VERSION == 3
    assert VOICE_CONFIGURATION_POLICY_VERSION == "voice-configuration-v1"
    assert EXECUTION_REQUEST_FORMAT == "speech-execution-request-v1"
    assert EXECUTION_RESULT_FORMAT == "speech-execution-result-v1"


def test_frozen_voice_frontend_and_lifecycle_taxonomies() -> None:
    assert _values(VoiceFrontendEventType) == (
        "idle",
        "listening",
        "speech_started",
        "speech_ended",
        "processing",
        "speaking_started",
        "speaking_ended",
        "interruption_detected",
        "interruption_requested",
        "interruption_confirmed",
        "paused",
        "cancelling",
        "cancelled",
        "reconciliation_required",
        "unavailable",
        "error",
    )
    assert _values(VoicePresentationState) == (
        "idle",
        "listening",
        "speech-detected",
        "processing",
        "speaking",
        "interrupted",
        "paused",
        "unavailable",
        "error",
    )
    assert _values(RealtimeVoiceState) == (
        "waiting",
        "listening",
        "user_speaking",
        "utterance_finalizing",
        "transcription_pending",
        "waiting_for_response",
        "synthesis_pending",
        "system_speaking",
        "interruption_pending",
        "cancellation_pending",
        "reconciliation_required",
        "error",
        "closed",
    )
    assert _values(VoiceCompleteness) == ("complete", "incomplete")
    assert _values(VoicePersistenceState) == (
        "available",
        "schema_mismatch",
        "migration_mismatch",
        "corrupt",
        "unavailable",
    )


def test_frozen_perception_retention_and_capability_taxonomies() -> None:
    assert _values(PerceptionArtifactKind) == (
        "raw_observation",
        "derived_feature",
        "model_inference",
        "contextual_interpretation",
    )
    assert _values(PerceptionBundleStatus) == (
        "pending",
        "available",
        "partial",
        "unavailable",
        "not_requested",
    )
    assert _values(RetentionClass) == (
        "transient_only",
        "policy_persistable",
        "raw_media_explicit_only",
    )
    assert tuple(sorted(MODALITIES)) == (
        "audio",
        "camera",
        "interaction",
        "multimodal",
        "screen",
        "speech",
        "system",
        "vision",
    )
    assert _values(CapabilityLevel) == (
        "supported",
        "degraded",
        "unavailable",
        "not_configured",
        "error",
        "corrupt",
        "schema_mismatch",
        "migration_mismatch",
    )
    assert _values(OperationalCompletion) == (
        "internally_complete",
        "externally_blocked",
        "intentionally_unavailable",
        "incomplete",
    )


def test_frozen_authority_privacy_and_local_provider_guards() -> None:
    settings = VoiceSettings()
    assert settings.preferred_voice_gender == "female"
    assert settings.store_raw_audio is False
    assert settings.delete_after_transcription is True
    assert settings.keep_synthesis_audio is False
    assert DEFAULT_PERCEPTION_POLICY["persist_transcripts"] is False
    assert DEFAULT_PERCEPTION_POLICY["camera_enabled"] is False
    assert DEFAULT_PERCEPTION_POLICY["persist_raw_visual"] is False
    roots = tuple(
        SOURCE_ROOT / name for name in ("voice", "audio", "speech_adapters", "voice_composition")
    )
    source = "\n".join(
        path.read_text(encoding="utf-8") for root in roots for path in root.rglob("*.py")
    )
    assert not any(term in source for term in ("subprocess", "Popen", "os.system", "shell=True"))
    assert "local_files_only=True" in (SOURCE_ROOT / "speech_adapters/faster_whisper.py").read_text(
        encoding="utf-8"
    )
    agents_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (SOURCE_ROOT / "agents").rglob("*.py")
    )
    assert "VoiceProfile" not in agents_source
    assert ".generate(" not in "\n".join(
        path.read_text(encoding="utf-8")
        for root in (SOURCE_ROOT / "voice", SOURCE_ROOT / "voice_composition")
        for path in root.rglob("*.py")
    )
    voice_source = "\n".join(
        path.read_text(encoding="utf-8") for path in (SOURCE_ROOT / "voice").rglob("*.py")
    )
    assert "synapse.knowledge" not in voice_source
    assert "synapse.chat.rag_policy" not in voice_source
    assert "context_fusion" not in voice_source


def test_frozen_presentation_absence_and_composition_isolation() -> None:
    assert not any((SOURCE_ROOT / name).exists() for name in ("avatar", "embodiment", "wardrobe"))
    assert not any(
        "synapse.voice_composition" in path.read_text(encoding="utf-8")
        for root in (
            SOURCE_ROOT / "voice",
            SOURCE_ROOT / "audio",
            SOURCE_ROOT / "perception",
            SOURCE_ROOT / "bootstrap",
        )
        for path in root.rglob("*.py")
    )
    assert {edge for edge in _runtime_context_graph() if "voice_composition" in edge} == {
        ("voice_composition", "audio"),
        ("voice_composition", "conversations"),
        ("voice_composition", "core"),
        ("voice_composition", "perception"),
        ("voice_composition", "speech_adapters"),
        ("voice_composition", "voice"),
    }


def test_frozen_tts_and_visual_external_blocker_classification(tmp_path: Path) -> None:
    runtime = VoicePerceptionRuntimeBuilder(
        data_dir=DataDir(tmp_path),
        configuration=VoicePerceptionConfiguration(stt_model=None, perception_enabled=False),
        frame_classifier=_NoSpeechClassifier(),
    ).build()
    health = runtime.health_snapshot()
    assert health.tts.fact("execution_boundary_available") is True
    assert health.tts.fact("execution_authority_available") is False
    assert health.tts.fact("operational_execution_available") is False
    completion = dict(health.operational_completion)
    assert completion["speech_output"] is OperationalCompletion.EXTERNALLY_BLOCKED
    assert completion["visual_perception"] is OperationalCompletion.INTENTIONALLY_UNAVAILABLE


def test_frozen_graph_and_tolerated_scc_baseline() -> None:
    runtime = _runtime_context_graph()
    source = context_graph()
    assert len(runtime) == 313  # Project Knowledge adds document/index lifecycle edges.
    assert [(len(members), edges) for members, edges in cyclic_components(runtime)] == [(11, 31)]
    assert len(source) == 352  # Source graph includes project knowledge ingestion facade.
    assert sorted((len(members), edges) for members, edges in cyclic_components(source)) == [
        (3, 4),
        (24, 80),
    ]
