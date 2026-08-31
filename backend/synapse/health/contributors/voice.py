from __future__ import annotations

from typing import Any

from synapse.health.contracts import HealthCheckContext, HealthContribution
from synapse.health.contributors.base import check, checks, component


class VoiceHealthContributor:
    contributor_id = "voice"

    def __init__(
        self,
        voice: Any,
        speech_adapters: Any,
        speech_pipeline: Any,
        multimodal: Any,
        audio: Any,
    ) -> None:
        self.voice = voice
        self.speech_adapters = speech_adapters
        self.speech_pipeline = speech_pipeline
        self.multimodal = multimodal
        self.audio = audio

    @staticmethod
    def _unavailable(runtime: Any) -> int:
        if not runtime:
            return 0
        try:
            return runtime.provider_unavailable_count()
        except Exception:
            return 0

    def collect_health(self, context: HealthCheckContext) -> HealthContribution:
        voice = self._unavailable(self.voice)
        try:
            speech = self.speech_adapters.unavailable_count() if self.speech_adapters else 0
        except Exception:
            speech = 0
        try:
            sessions = self.speech_pipeline.session_count() if self.speech_pipeline else 0
        except Exception:
            sessions = 0
        audio = 0
        if self.audio:
            for resolver in (self.audio.resolve_stt_provider, self.audio.resolve_tts_provider):
                try:
                    resolver()
                except Exception:
                    audio += 1
        active_voice = int(self.voice.diagnostics()["active_sessions"]) if self.voice else 0
        return HealthContribution(
            components=(
                component(6, "voice", self.voice, ["audio", "speech_adapters"]),
                component(9, "multimodal", self.multimodal, ["perception"]),
            ),
            summary={
                "voice_runtime_available": self.voice is not None,
                "voice_provider_unavailable_count": voice,
                "voice_diagnostics": self.voice.diagnostics() if self.voice else {},
                "speech_adapter_runtime_available": self.speech_adapters is not None,
                "speech_adapters_unavailable_count": speech,
                "speech_pipeline_runtime_available": self.speech_pipeline is not None,
                "speech_pipeline_sessions_count": sessions,
                "multimodal_runtime_available": self.multimodal is not None,
                "audio_runtime_available": self.audio is not None,
                "audio_provider_unavailable_count": audio,
            },
            checks=checks(
                check(
                    35,
                    "voice.unavailable_runtime",
                    self.voice is None,
                    "warning",
                    "voice runtime unavailable",
                ),
                check(
                    36,
                    "voice.providers_unavailable",
                    voice > 0,
                    "warning",
                    f"{voice} voice provider reference(s) unavailable",
                    {"voice_provider_unavailable_count": voice},
                ),
                check(
                    37,
                    "speech_pipeline.unavailable_runtime",
                    self.speech_pipeline is None,
                    "warning",
                    "speech pipeline runtime unavailable",
                ),
                check(
                    38,
                    "speech_adapters.unavailable_runtime",
                    self.speech_adapters is None,
                    "warning",
                    "speech adapter runtime unavailable",
                ),
                check(
                    39,
                    "speech_adapters.unavailable",
                    speech > 0,
                    "warning",
                    f"{speech} speech adapter(s) unavailable",
                    {"speech_adapters_unavailable_count": speech},
                ),
                check(
                    40,
                    "multimodal.unavailable_runtime",
                    self.multimodal is None,
                    "warning",
                    "multimodal communication runtime unavailable",
                ),
                check(
                    41,
                    "audio.unavailable_runtime",
                    self.audio is None,
                    "warning",
                    "audio runtime unavailable",
                ),
                check(
                    42,
                    "audio.providers_unavailable",
                    audio > 0,
                    "warning",
                    f"{audio} audio provider(s) unavailable",
                    {"audio_provider_unavailable_count": audio},
                ),
            ),
            metrics={"active_voice_sessions": active_voice},
        )
