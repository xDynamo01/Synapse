from pathlib import Path

from synapse.voice.base import STTDriver


class VoskDriver(STTDriver):
    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError("Vosk driver scaffold only; install and implement when voice is enabled.")
