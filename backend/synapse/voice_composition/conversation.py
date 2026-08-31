from __future__ import annotations

import hashlib
from dataclasses import dataclass

from synapse.conversations.models import AgentMessage
from synapse.conversations.runtime import ConversationRuntime
from synapse.conversations.voice_contracts import (
    ConversationResponseReference,
    VoiceConversationRequest,
)
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext


@dataclass(frozen=True, slots=True)
class ConversationWiringHealth:
    contract_available: bool
    runtime_available: bool
    target_configured: bool
    target_available: bool
    request_path_available: bool
    response_path_available: bool

    @property
    def supported(self) -> bool:
        return all(
            (
                self.contract_available,
                self.runtime_available,
                self.target_configured,
                self.target_available,
                self.request_path_available,
                self.response_path_available,
            )
        )


class LocalConversationHandoff:
    """Consumer-owned Voice adapter over factual Conversation messages.

    It records requests and explicit authority responses. It never selects an
    Agent, invokes a model, executes tools, or synthesizes speech.
    """

    def __init__(
        self,
        runtime: ConversationRuntime,
        context: PermissionContext,
        target_agent_id: str,
    ) -> None:
        target = target_agent_id.strip().lower()
        if not target:
            raise ValidationError("Voice Conversation target Agent is not configured.")
        runtime.agents.get(target)
        self._runtime = runtime
        self._context = context
        self.target_agent_id = target

    def submit(self, request: VoiceConversationRequest) -> None:
        conversation_id = _conversation_id(request.conversation_reference)
        self._runtime.send_message(
            self._context,
            "local_chat",
            self.target_agent_id,
            {
                "role": "user",
                "transcript_reference": request.transcript_reference,
                "purpose": request.purpose,
            },
            conversation_id=conversation_id,
            message_id=request.request_id,
            correlation_id=request.correlation_reference,
            causation_id=request.transcription_id,
            idempotency_key=request.request_id,
            metadata={
                "voice_session_id": request.voice_session_id,
                "utterance_id": request.utterance_id,
                "transcription_id": request.transcription_id,
                "conversation_turn_id": request.conversation_turn_id,
                "correlation_reference": request.correlation_reference,
                "response_deadline_at": request.response_deadline_at,
                "provenance": list(request.provenance),
                "voice_request": True,
            },
        )
        return None

    def accept_authority_response(
        self,
        request: VoiceConversationRequest,
        *,
        response_reference: str,
        text: str,
        provenance: tuple[str, ...],
    ) -> ConversationResponseReference:
        request_message = self._runtime.message_status(request.request_id)
        self._validate_request_message(request, request_message)
        if not text.strip():
            raise ValidationError("Conversation authority response text is required.")
        response_id = _response_id(request.request_id, response_reference)
        response_message = self._runtime.send_message(
            self._context,
            self.target_agent_id,
            "local_chat",
            {"role": "assistant", "body": text},
            conversation_id=request_message.conversation_id,
            message_id=response_id,
            correlation_id=request.correlation_reference,
            causation_id=request.request_id,
            idempotency_key=response_id,
            parent_message_id=request.request_id,
            metadata={
                "response_reference": response_reference,
                "voice_request_id": request.request_id,
                "provenance": list(provenance),
            },
        )
        if (
            response_message.payload.get("body") != text
            or response_message.metadata.get("response_reference") != response_reference
            or tuple(response_message.metadata.get("provenance", ())) != provenance
        ):
            raise ValidationError("Contradictory Conversation authority response identity.")
        return self._response_reference(request, response_message, response_reference, provenance)

    def _validate_request_message(
        self, request: VoiceConversationRequest, message: AgentMessage
    ) -> None:
        expected = {
            "voice_session_id": request.voice_session_id,
            "utterance_id": request.utterance_id,
            "transcription_id": request.transcription_id,
            "conversation_turn_id": request.conversation_turn_id,
            "correlation_reference": request.correlation_reference,
            "response_deadline_at": request.response_deadline_at,
        }
        if (
            message.sender_agent_id != "local_chat"
            or message.receiver_agent_id != self.target_agent_id
            or any(message.metadata.get(key) != value for key, value in expected.items())
        ):
            raise ValidationError("Conversation request message correspondence mismatch.")

    @staticmethod
    def _response_reference(
        request: VoiceConversationRequest,
        message: AgentMessage,
        response_reference: str,
        provenance: tuple[str, ...],
    ) -> ConversationResponseReference:
        if (
            message.parent_message_id != request.request_id
            or message.correlation_id != request.correlation_reference
        ):
            raise ValidationError("Conversation response message correspondence mismatch.")
        return ConversationResponseReference(
            response_id=message.message_id,
            response_reference=response_reference,
            request_id=request.request_id,
            conversation_turn_id=request.conversation_turn_id,
            voice_session_id=request.voice_session_id,
            utterance_id=request.utterance_id,
            transcription_id=request.transcription_id,
            correlation_reference=request.correlation_reference,
            text=str(message.payload["body"]),
            provenance=provenance,
        )


def conversation_wiring_health(
    runtime: ConversationRuntime | None,
    context: PermissionContext | None,
    target_agent_id: str | None,
) -> ConversationWiringHealth:
    target_configured = bool(target_agent_id and target_agent_id.strip())
    target_available = False
    if runtime is not None and target_configured:
        try:
            runtime.agents.get(str(target_agent_id).strip().lower())
            target_available = True
        except Exception:
            target_available = False
    permission_available = bool(
        runtime is not None
        and context is not None
        and runtime.permissions.is_allowed(context, "agents.message").allowed
    )
    path = bool(
        runtime is not None and context is not None and target_available and permission_available
    )
    return ConversationWiringHealth(
        True, runtime is not None, target_configured, target_available, path, path
    )


def _conversation_id(reference: str | None) -> str | None:
    if reference is None:
        return None
    prefix = "conversation://"
    return reference[len(prefix) :] if reference.startswith(prefix) else reference


def _response_id(request_id: str, response_reference: str) -> str:
    digest = hashlib.sha256(f"{request_id}:{response_reference}".encode()).hexdigest()
    return f"voice-response-{digest[:24]}"
