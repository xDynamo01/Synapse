"""Local, memory-only voice adapter for the native client. One JSON object per line."""
import base64
import binascii
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata

INPUT_RATE = 16_000
MAX_TURN_SECONDS = 25
MAX_WAKE_BYTES = INPUT_RATE
WAKE_WINDOW_BYTES = INPUT_RATE * 2 * 2
WAKE_TAIL_BYTES = INPUT_RATE * 2
MAX_TURN_BYTES = INPUT_RATE * MAX_TURN_SECONDS * 2
MAX_REQUEST_BYTES = 4 * ((MAX_TURN_BYTES + 2) // 3) + 4096
MAX_TTS_SECONDS = 60
VOICE = "supertonic-3:F1"
LANGUAGE_CODES = {"pt-BR": "pt", "en-US": "en"}
LOCALES = {model_language: locale for locale, model_language in LANGUAGE_CODES.items()}
STT_FILES = ("config.json", "model.bin", "tokenizer.json", "vocabulary.txt")
TTS_FILES = (
    "config.json", "onnx/duration_predictor.onnx", "onnx/text_encoder.onnx",
    "onnx/tts.json", "onnx/unicode_indexer.json", "onnx/vector_estimator.onnx",
    "onnx/vocoder.onnx", "voice_styles/F1.json",
)


class VoiceError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def valid_fields(request, required, optional=()):
    if not required <= request.keys() or request.keys() - required - set(optional):
        raise VoiceError("invalid_request", "Unexpected or missing voice fields")


def decode_pcm(value, byte_limit):
    if not isinstance(value, str) or len(value) > 4 * ((byte_limit + 2) // 3):
        raise VoiceError("invalid_audio", "PCM payload exceeds the action limit")
    try:
        pcm = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise VoiceError("invalid_audio", "PCM payload is not valid base64") from None
    if not pcm or len(pcm) % 2 or len(pcm) > byte_limit:
        raise VoiceError("invalid_audio", "PCM payload must be nonempty mono PCM16")
    return pcm


def normalized_name(value):
    if not isinstance(value, str) or len(value) > 48:
        raise VoiceError("invalid_wake_name", "Use a short spoken agent name")
    normalized = unicodedata.normalize("NFKD", value.casefold())
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    normalized = " ".join(normalized.split())
    if not re.fullmatch(r"[a-z]+(?: [a-z]+){0,2}", normalized):
        raise VoiceError("invalid_wake_name", "Use one to three spoken words")
    return normalized


def assets_ready(directory, required):
    return directory is not None and all((directory / name).is_file() for name in required)


class Voice:
    def __init__(self, model_dir):
        self.model_dir = model_dir
        self.threads = self.thread_count()
        self.wake_name = "Artemis"
        self.wake_phones = None
        self.detector = None
        self.wake_bytes = 0
        self.wake_tail = bytearray()
        self.stt = None
        self.tts = None
        self.style = None

    @staticmethod
    def thread_count():
        configured = os.environ.get("SYNAPSE_VOICE_THREADS", "2")
        return int(configured) if configured in {"1", "2", "3", "4"} else 2

    def pack(self, name):
        return None if self.model_dir is None else self.model_dir / name

    def health(self):
        return {
            "wake": importlib.util.find_spec("pocketsphinx") is not None,
            "stt": importlib.util.find_spec("faster_whisper") is not None
                   and assets_ready(self.pack("whisper-base"), STT_FILES),
            "tts": importlib.util.find_spec("supertonic") is not None
                   and assets_ready(self.pack("supertonic-3"), TTS_FILES),
            "languages": list(LANGUAGE_CODES),
            "voice": VOICE,
        }

    def wake_reset(self, name, phones=None):
        from pocketsphinx import Decoder

        phrase = normalized_name(name)
        if self.detector is not None and name == self.wake_name and phones == self.wake_phones:
            self.restart_detector()
            return {"name": name}
        if phones is not None and (len(phrase.split()) != 1 or not isinstance(phones, str)
                                  or not re.fullmatch(r"[A-Z]{1,3}(?: [A-Z]{1,3}){1,19}", phones)):
            raise VoiceError("invalid_wake_name", "Custom pronunciation requires one word and ARPABET phones")
        # No language model or free-form search is configured. The single
        # search emits only a match against the requested name.
        detector = Decoder(lm=None, samprate=INPUT_RATE, loglevel="FATAL", kws_threshold=1e-28)
        try:
            if phones is not None:
                detector.add_word(phrase, phones, False)
            elif phrase == "artemis":
                detector.add_word("artemis", "AA R T EY M IY S", False)
                detector.add_word("artemispt", "AA R T CH IY M IY S", False)
            elif any(detector.lookup_word(word) is None for word in phrase.split()):
                raise VoiceError("invalid_wake_name", "Name needs an explicit pronunciation")
            if phrase == "artemis" and phones is None:
                # The keyword search requires separate word IDs for its two
                # pronunciations. The file contains only fixed lexical aliases.
                with tempfile.NamedTemporaryFile(mode="w", encoding="ascii", delete=False) as file:
                    config = Path(file.name)
                    file.write("artemis /1e-28/\nartemispt /1e-28/\n")
                try:
                    detector.add_kws("wake", str(config))
                finally:
                    config.unlink(missing_ok=True)
            else:
                detector.add_keyphrase("wake", phrase)
            detector.activate_search("wake")
            detector.start_utt()
        except (RuntimeError, ValueError):
            raise VoiceError("invalid_wake_name", "Wake pronunciation could not be configured") from None
        self.detector = detector
        self.wake_bytes = 0
        self.wake_tail.clear()
        self.wake_name = name
        self.wake_phones = phones
        return {"name": name}

    def restart_detector(self):
        self.detector.end_utt()
        self.detector.start_utt()
        self.wake_bytes = 0
        self.wake_tail.clear()

    def wake(self, pcm):
        if self.detector is None:
            self.wake_reset(self.wake_name, self.wake_phones)
        self.detector.process_raw(pcm, False, False)
        detected = self.detector.hyp() is not None
        if detected:
            self.restart_detector()
        else:
            # Keep a short overlap for a name crossing the decoder reset. An
            # indefinitely armed detector never retains an unbounded stream.
            self.wake_bytes += len(pcm)
            self.wake_tail.extend(pcm)
            del self.wake_tail[:-WAKE_TAIL_BYTES]
            if self.wake_bytes >= WAKE_WINDOW_BYTES:
                tail = bytes(self.wake_tail)
                self.restart_detector()
                self.detector.process_raw(tail, False, False)
                self.wake_bytes = len(tail)
                self.wake_tail.extend(tail)
        return {"detected": detected}

    def transcribe(self, pcm):
        import numpy as np
        from faster_whisper import WhisperModel

        samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768
        silent = {"text": "", "language": None, "confidence": 0.0, "ambiguous": False}
        if samples.size < INPUT_RATE // 5 or float(np.mean(samples ** 2)) < 0.0025 ** 2:
            return silent
        path = self.pack("whisper-base")
        if not assets_ready(path, STT_FILES):
            raise VoiceError("stt_unavailable", "Local transcription pack is missing")
        if self.stt is None:
            self.stt = WhisperModel(str(path.resolve()), device="cpu", compute_type="int8",
                                    cpu_threads=self.threads, num_workers=1, local_files_only=True)
        segments, info = self.stt.transcribe(samples, beam_size=3, temperature=0.0,
                                             vad_filter=True, condition_on_previous_text=False,
                                             without_timestamps=True, max_new_tokens=224)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        if not text:
            return silent
        language = LOCALES.get(info.language)
        if language is None:
            raise VoiceError("unsupported_voice_language", "Detected language has no validated voice pack")
        probabilities = dict(info.all_language_probs or ())
        competing = max((probabilities.get(code, 0.0) for code in LOCALES if code != info.language), default=0.0)
        confidence = float(info.language_probability)
        ambiguous = confidence < 0.45 or competing >= 0.20 and confidence - competing < 0.20
        if not ambiguous and samples.size >= INPUT_RATE * 4:
            # Flag a clear change of language within one captured turn. This
            # measures speech-language ambiguity, not physical speaker identity.
            for window in (samples[:INPUT_RATE * 2], samples[-INPUT_RATE * 2:]):
                other, probability, _ = self.stt.detect_language(audio=window)
                if other in LOCALES and other != info.language and probability >= 0.75:
                    ambiguous = True
                    break
        return {"text": text, "language": language, "confidence": confidence, "ambiguous": bool(ambiguous)}

    def synthesize(self, text, language):
        import numpy as np
        from supertonic import TTS

        if (not isinstance(text, str) or not text.strip() or len(text) > 720
                or len(text.encode("utf-8")) > 2048 or "\0" in text):
            raise VoiceError("invalid_text", "Synthesis needs nonempty text up to 720 characters")
        if not isinstance(language, str) or language not in LANGUAGE_CODES:
            raise VoiceError("unsupported_voice_language", "Choose an installed voice language")
        path = self.pack("supertonic-3")
        if not assets_ready(path, TTS_FILES):
            raise VoiceError("tts_unavailable", "Local speech synthesis pack is missing")
        if self.tts is None:
            tts = TTS(model="supertonic-3", model_dir=path.resolve(), auto_download=False,
                      intra_op_num_threads=self.threads, inter_op_num_threads=1)
            self.style = tts.get_voice_style("F1")
            self.tts = tts
        audio, _ = self.tts.synthesize(text.strip(), voice_style=self.style,
                                       lang=LANGUAGE_CODES[language], speed=1.0)
        audio = np.asarray(audio).squeeze()
        rate = int(self.tts.sample_rate)
        if audio.ndim != 1 or not audio.size or audio.size > rate * MAX_TTS_SECONDS or not np.isfinite(audio).all():
            raise VoiceError("invalid_synthesis", "Synthesis did not return bounded mono audio")
        pcm = np.rint(np.clip(audio, -1.0, 1.0) * 32767).astype("<i2").tobytes()
        return {"pcm": base64.b64encode(pcm).decode("ascii"), "sample_rate": rate, "voice": VOICE}

    def dispatch(self, request):
        base = {"id", "action"}
        action = request.get("action")
        if action == "health":
            valid_fields(request, base)
            return self.health()
        if action == "wake_reset":
            valid_fields(request, base, ("name", "phones"))
            name = request.get("name", self.wake_name)
            phones = request.get("phones", self.wake_phones if "name" not in request else None)
            return self.wake_reset(name, phones)
        if action == "wake":
            valid_fields(request, base | {"pcm"})
            return self.wake(decode_pcm(request["pcm"], MAX_WAKE_BYTES))
        if action == "transcribe":
            valid_fields(request, base | {"pcm"})
            return self.transcribe(decode_pcm(request["pcm"], MAX_TURN_BYTES))
        if action == "synthesize":
            valid_fields(request, base | {"text", "language"})
            return self.synthesize(request["text"], request["language"])
        raise VoiceError("invalid_request", "Unknown voice action")


def respond(voice, raw):
    request_id = None
    try:
        try:
            request = json.loads(raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise VoiceError("invalid_request", "Invalid voice request JSON") from None
        if not isinstance(request, dict) or type(request.get("id")) is not int or not 0 <= request["id"] < 2 ** 64:
            raise VoiceError("invalid_request", "Voice request requires an unsigned identifier")
        request_id = request["id"]
        result = voice.dispatch(request)
        return {"id": request_id, "ok": True, "result": result}
    except VoiceError as error:
        return {"id": request_id, "ok": False, "error": {"code": error.code, "message": str(error)}}
    except ImportError:
        return {"id": request_id, "ok": False, "error": {
            "code": "voice_runtime_unavailable", "message": "Local voice runtime dependency unavailable"}}
    except Exception:
        # Responses and logs never include transcript, audio, or exception text.
        return {"id": request_id, "ok": False, "error": {
            "code": "voice_runtime_failed", "message": "The local voice operation failed"}}


def main():
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    configured = os.environ.get("SYNAPSE_VOICE_MODELS")
    voice = Voice(Path(configured) if configured else None)
    while raw := sys.stdin.buffer.readline(MAX_REQUEST_BYTES + 1):
        if len(raw) > MAX_REQUEST_BYTES:
            return 2
        response = respond(voice, raw)
        print(json.dumps(response, ensure_ascii=True, allow_nan=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
