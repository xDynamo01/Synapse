from __future__ import annotations

import unittest

from synapse.contracts import (
    AgentContract,
    AgentIdentityDTO,
    ContextProvider,
    ContextRequestDTO,
    ContractError,
    ContractEvent,
    ContractResult,
    ContractStatus,
    MemorySnapshotDTO,
    MemoryStore,
    MemoryStoreEntryDTO,
    MissionDTO,
    MissionRuntime,
    ModelProvider,
    ModelProviderDTO,
    ModelRequestDTO,
    SystemInsightDTO,
    SystemInsightProvider,
    ToolExecutionRequestDTO,
    ToolExecutionResultDTO,
    ToolProvider,
    ToolSpecDTO,
    VoiceAnalysisProvider,
    VoiceAnalysisRequestDTO,
    VoiceSTTProvider,
    VoiceSTTRequestDTO,
    VoiceTTSProvider,
    VoiceTTSRequestDTO,
)


class ContractTests(unittest.TestCase):
    def test_base_contract_types_are_instantiable(self) -> None:
        status = ContractStatus(state="ready")
        event = ContractEvent(event_type="agent.created", source="tests")
        error = ContractError(code="provider_not_configured", message="missing")
        result = ContractResult(ok=False, error=error, events=[event])

        self.assertEqual(status.state, "ready")
        self.assertEqual(event.source, "tests")
        self.assertEqual(result.error.code, "provider_not_configured")

    def test_agent_dto_and_protocol_shape(self) -> None:
        identity = AgentIdentityDTO(agent_id="atlas", display_name="Atlas")

        class DummyAgent:
            def describe(self, agent_id: str) -> AgentIdentityDTO:
                return AgentIdentityDTO(agent_id=agent_id)

            def load_config(self, agent_id: str) -> object:
                return {"agent_id": agent_id}

            def get_runtime_state(self, agent_id: str) -> object:
                return {"agent_id": agent_id, "state": "idle"}

            def get_policy(self, agent_id: str) -> object:
                return {"agent_id": agent_id}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        self.assertEqual(identity.agent_id, "atlas")
        self.assertTrue(isinstance(DummyAgent(), AgentContract))

    def test_model_voice_memory_context_and_mission_contracts(self) -> None:
        model_request = ModelRequestDTO(model_id="mock", messages=[{"role": "user", "content": "hi"}])
        model_provider = ModelProviderDTO(provider_id="mock-provider")
        voice_stt_request = VoiceSTTRequestDTO(audio_ref="audio://sample.wav")
        voice_tts_request = VoiceTTSRequestDTO(text="hello")
        analysis_request = VoiceAnalysisRequestDTO(audio_ref="audio://sample.wav")
        memory_entry = MemoryStoreEntryDTO(scope="global", key="note", value="value")
        memory_snapshot = MemorySnapshotDTO(scope="global", entries=[memory_entry])
        context_request = ContextRequestDTO(agent_id="atlas")
        mission = MissionDTO(mission_id="mission-1", title="Mission", status="active")
        tool_spec = ToolSpecDTO(tool_id="health.check", name="Health", description="Health check")
        tool_request = ToolExecutionRequestDTO(tool_id="health.check")
        tool_result = ToolExecutionResultDTO(tool_id="health.check", ok=True)
        insight = SystemInsightDTO(status="ok")

        self.assertEqual(model_request.model_id, "mock")
        self.assertEqual(model_provider.provider_id, "mock-provider")
        self.assertEqual(voice_stt_request.audio_ref, "audio://sample.wav")
        self.assertEqual(voice_tts_request.text, "hello")
        self.assertEqual(analysis_request.audio_ref, "audio://sample.wav")
        self.assertEqual(memory_snapshot.scope, "global")
        self.assertEqual(context_request.agent_id, "atlas")
        self.assertEqual(mission.title, "Mission")
        self.assertEqual(tool_spec.tool_id, "health.check")
        self.assertEqual(tool_request.tool_id, "health.check")
        self.assertTrue(tool_result.ok)
        self.assertEqual(insight.status, "ok")

    def test_domain_protocols_accept_dummy_implementations(self) -> None:
        class DummyModelProvider:
            def list_models(self) -> list[ModelProviderDTO]:
                return [ModelProviderDTO(provider_id="mock")]

            def health(self) -> ModelProviderDTO:
                return ModelProviderDTO(provider_id="mock", status="ok")

            def generate(self, request: ModelRequestDTO) -> object:
                return {"model_id": request.model_id}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyVoiceSTTProvider:
            def transcribe(self, request: VoiceSTTRequestDTO) -> object:
                return {"transcript": request.audio_ref}

            def health(self) -> dict[str, str]:
                return {"status": "ok"}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyVoiceTTSProvider:
            def synthesize(self, request: VoiceTTSRequestDTO) -> object:
                return {"audio_ref": request.text}

            def health(self) -> dict[str, str]:
                return {"status": "ok"}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyVoiceAnalysisProvider:
            def analyze(self, request: VoiceAnalysisRequestDTO) -> object:
                return {"summary": request.audio_ref}

            def health(self) -> dict[str, str]:
                return {"status": "ok"}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyMemoryStore:
            def read(self, scope: str) -> MemorySnapshotDTO:
                return MemorySnapshotDTO(scope=scope)

            def write(self, entry: MemoryStoreEntryDTO) -> None:
                self.last_entry = entry

            def append(self, entry: MemoryStoreEntryDTO) -> None:
                self.last_entry = entry

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyContextProvider:
            def build(self, request: ContextRequestDTO) -> object:
                return {"agent_id": request.agent_id}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyMissionRuntime:
            def create(self, mission: MissionDTO) -> MissionDTO:
                return mission

            def get(self, mission_id: str) -> MissionDTO:
                return MissionDTO(mission_id=mission_id, title="Mission", status="active")

            def list_tasks(self, mission_id: str) -> list[object]:
                return []

            def state(self, mission_id: str) -> object:
                return {"mission_id": mission_id}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyToolProvider:
            def list_tools(self) -> list[ToolSpecDTO]:
                return [ToolSpecDTO(tool_id="health.check", name="Health", description="Health check")]

            def describe(self, tool_id: str) -> ToolSpecDTO:
                return ToolSpecDTO(tool_id=tool_id, name=tool_id, description=tool_id)

            def execute(self, request: ToolExecutionRequestDTO) -> object:
                return {"tool_id": request.tool_id}

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        class DummyInsightProvider:
            def inspect(self) -> SystemInsightDTO:
                return SystemInsightDTO(status="ok")

            def emit(self, event: ContractEvent) -> None:
                self.last_event = event

        self.assertTrue(isinstance(DummyModelProvider(), ModelProvider))
        self.assertTrue(isinstance(DummyVoiceSTTProvider(), VoiceSTTProvider))
        self.assertTrue(isinstance(DummyVoiceTTSProvider(), VoiceTTSProvider))
        self.assertTrue(isinstance(DummyVoiceAnalysisProvider(), VoiceAnalysisProvider))
        self.assertTrue(isinstance(DummyMemoryStore(), MemoryStore))
        self.assertTrue(isinstance(DummyContextProvider(), ContextProvider))
        self.assertTrue(isinstance(DummyMissionRuntime(), MissionRuntime))
        self.assertTrue(isinstance(DummyToolProvider(), ToolProvider))
        self.assertTrue(isinstance(DummyInsightProvider(), SystemInsightProvider))


if __name__ == "__main__":
    unittest.main()
