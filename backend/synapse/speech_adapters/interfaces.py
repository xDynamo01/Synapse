from __future__ import annotations

from typing import Protocol

from synapse.audio.models import (
    AudioInputRequest,
    AudioOutputRequest,
    SpeechToTextResult,
    TextToSpeechResult,
)
from synapse.speech_adapters.models import SpeechAdapterHealth, SpeechAdapterManifest


class SpeechToTextAdapter(Protocol):
    def manifest(self) -> SpeechAdapterManifest: ...

    def health(self) -> SpeechAdapterHealth: ...

    def transcribe(self, request: AudioInputRequest) -> SpeechToTextResult: ...


class TextToSpeechAdapter(Protocol):
    def manifest(self) -> SpeechAdapterManifest: ...

    def health(self) -> SpeechAdapterHealth: ...

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult: ...


class VoiceAnalysisAdapter(Protocol):
    def manifest(self) -> SpeechAdapterManifest: ...

    def health(self) -> SpeechAdapterHealth: ...

    def analyze(self, request: AudioInputRequest) -> dict: ...
