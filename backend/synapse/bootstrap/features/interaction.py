from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from synapse.audio.runtime import AudioRuntime
from synapse.bootstrap.feature import BuiltFeature, FeatureMetadata
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.multimodal.runtime import MultimodalCommunicationRuntime
from synapse.perception.policy import PerceptionPolicyRuntime
from synapse.perception.runtime import PerceptionRuntime
from synapse.speech_adapters.runtime import SpeechAdapterRuntime
from synapse.speech_pipeline.runtime import SpeechPipelineRuntime
from synapse.vision.capture import CaptureRuntime
from synapse.vision.runtime import VisionRuntime
from synapse.voice.perception import VoicePerceptionSink
from synapse.voice.runtime import VoiceRuntime


@dataclass(frozen=True)
class InteractionFeatureDependencies:
    data_dir: DataDir
    events: EventBus
    agents: Any
    providers: Any
    speech_adapters: SpeechAdapterRuntime
    default_actor_id: str
    voice_perception_sink: VoicePerceptionSink | None = None


@dataclass(frozen=True)
class InteractionFeature:
    multimodal: MultimodalCommunicationRuntime
    perception: PerceptionRuntime
    capture: CaptureRuntime
    audio: AudioRuntime
    voice: VoiceRuntime
    vision: VisionRuntime
    speech_pipeline: SpeechPipelineRuntime


class InteractionFeatureBuilder:
    metadata = FeatureMetadata("multimodal-interaction")

    def build(
        self, dependencies: InteractionFeatureDependencies
    ) -> BuiltFeature[InteractionFeature]:
        data_dir = dependencies.data_dir
        events = dependencies.events
        multimodal = MultimodalCommunicationRuntime(data_dir, events)
        perception_policy = PerceptionPolicyRuntime(data_dir)
        perception = PerceptionRuntime(data_dir, events, multimodal, perception_policy)
        multimodal.bind_perception(perception)
        capture = CaptureRuntime(data_dir, events, perception_policy)
        audio = AudioRuntime(
            data_dir,
            events,
            dependencies.providers,
            multimodal,
            dependencies.speech_adapters,
        )
        voice = VoiceRuntime(
            data_dir,
            dependencies.agents,
            dependencies.providers,
            events,
            audio,
            dependencies.speech_adapters,
            dependencies.default_actor_id,
            perception_sink=dependencies.voice_perception_sink or perception,
        )
        vision = VisionRuntime(
            data_dir,
            events,
            dependencies.providers,
            multimodal,
            perception=perception,
            capture=capture,
        )
        speech_pipeline = SpeechPipelineRuntime(
            data_dir, events, audio, voice, perception, multimodal
        )
        return BuiltFeature(
            InteractionFeature(
                multimodal,
                perception,
                capture,
                audio,
                voice,
                vision,
                speech_pipeline,
            ),
            self.metadata,
        )
