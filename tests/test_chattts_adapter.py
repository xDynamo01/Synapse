from pathlib import Path

from synapse.core.data_dir import DataDir
from synapse.speech_adapters.chattts_tts import ChatTTSTextToSpeechAdapter
from synapse.speech_adapters.models import SpeechAdapterManifest


def _manifest() -> SpeechAdapterManifest:
    return SpeechAdapterManifest(
        adapter_id="chattts_tts_adapter",
        provider_id="chattts",
        adapter_type="tts",
        name="ChatTTS",
        description="optional",
        version="1.0.0",
        supported_languages=["en-US", "zh-CN"],
        supports_streaming=False,
        supports_file_input=False,
        supports_realtime=False,
        requires_gpu=False,
        requires_network=False,
    )


def test_chattts_is_unconfigured_without_an_explicit_runtime(tmp_path: Path) -> None:
    adapter = ChatTTSTextToSpeechAdapter(_manifest(), DataDir(tmp_path))
    health = adapter.health()
    assert health.status == "unconfigured"
    assert health.metadata["model_license"] == "CC BY-NC 4.0"
