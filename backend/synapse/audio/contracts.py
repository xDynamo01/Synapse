from __future__ import annotations

from typing import Protocol

from synapse.audio.models import (
    AudioInputRequest,
    AudioOutputRequest,
    SpeechToTextResult,
    TextToSpeechResult,
)


class SpeechExecutionPort(Protocol):
    def transcribe(self, request: AudioInputRequest) -> SpeechToTextResult: ...

    def synthesize(self, request: AudioOutputRequest) -> TextToSpeechResult: ...
