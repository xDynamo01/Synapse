from pathlib import Path

from synapse.voice.base import STTDriver


class FasterWhisperDriver(STTDriver):
    def transcribe(self, audio_path: Path) -> str:
        raise NotImplementedError("faster-whisper driver scaffold only; install and implement when voice is enabled.")
