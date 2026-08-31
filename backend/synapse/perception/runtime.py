from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from synapse.audio.models import AudioPayload, SpeechToTextResult, TextToSpeechResult
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound
from synapse.core.serialization import dump_structured_file, load_structured_file
from synapse.multimodal.runtime import MultimodalCommunicationRuntime
from synapse.observability.correlation import current_correlation_fields
from synapse.observability.redaction import redact
from synapse.perception.errors import (
    ObservationExpired,
    ObservationNotFound,
    PerceptionSignalDenied,
    PerceptionSignalInvalid,
    RetentionFailed,
)
from synapse.perception.models import (
    MODALITIES,
    SENSITIVITY_LEVELS,
    CleanupResult,
    PerceptionArtifactKind,
    PerceptionArtifactReference,
    PerceptionBatch,
    PerceptionBundleStatus,
    PerceptionConflict,
    PerceptionObservation,
    PerceptionResultBundle,
    PerceptionSignal,
    RetentionClass,
    SignalSummary,
    VoicePerceptionRequest,
)
from synapse.perception.nonverbal import (
    AcousticFeatureProvider,
    LocalDSPAcousticFeatureProvider,
)
from synapse.perception.policy import PerceptionPolicyRuntime

CHANNEL_BY_MODALITY = {
    "audio": "audio",
    "speech": "voice",
    "vision": "vision",
    "screen": "vision",
    "camera": "vision",
    "system": "system",
    "interaction": "system",
    "multimodal": "system",
}


class PerceptionRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        events: EventBus,
        multimodal: MultimodalCommunicationRuntime,
        policy: PerceptionPolicyRuntime | None = None,
        acoustic_provider: AcousticFeatureProvider | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.events = events
        self.multimodal = multimodal
        self.policy = policy or PerceptionPolicyRuntime(data_dir)
        self.acoustic_provider = acoustic_provider or LocalDSPAcousticFeatureProvider()

    def analyze_acoustic_features(
        self,
        payload: AudioPayload,
        *,
        input_reference: str,
        source_identity: str,
        session_id: str | None = None,
        occurrence_started_at: str | None = None,
        occurrence_ended_at: str | None = None,
    ) -> list[PerceptionSignal]:
        policy = self.policy.load()
        if not policy.get("acoustic_features_enabled", True):
            raise PerceptionSignalDenied("Acoustic feature production is disabled by policy")
        result = self.acoustic_provider.analyze(payload)
        artifacts: list[PerceptionSignal] = []
        for feature in result.features:
            artifacts.append(
                self.ingest_signal(
                    PerceptionSignal(
                        type=f"audio.{feature.name}",
                        modality="audio",
                        source="audio",
                        values={
                            "value": feature.value,
                            "unit": feature.unit,
                            "available": feature.available,
                            "limitations": feature.limitations,
                        },
                        session_id=session_id,
                        provenance=[
                            {
                                "provider": result.provider,
                                "algorithm": result.algorithm,
                                "algorithm_version": result.algorithm_version,
                                "input_reference": input_reference,
                            }
                        ],
                        sensitivity="sensitive",
                        artifact_kind=PerceptionArtifactKind.DERIVED_FEATURE,
                        source_identity=source_identity,
                        provider=result.provider,
                        model=result.algorithm,
                        model_version=result.algorithm_version,
                        occurrence_started_at=occurrence_started_at,
                        occurrence_ended_at=occurrence_ended_at,
                        input_references=[input_reference],
                        lineage=[input_reference],
                        policy_version="perception-policy-v1",
                        external_processing=False,
                        metadata={"raw_audio_persisted": False},
                    )
                )
            )
        return artifacts

    def nonverbal_capability_health(self) -> dict[str, dict[str, str]]:
        acoustic = self.acoustic_provider.health()
        if not self.policy.load().get("acoustic_features_enabled", True):
            acoustic = {"status": "not_configured", "provider": acoustic["provider"]}
        return {
            "acoustic_features": dict(acoustic),
            "pitch": dict(acoustic),
            "pause_analysis": dict(acoustic),
            "speech_rate": dict(acoustic),
            "face_detection": {"status": "not_configured"},
            "head_pose": {"status": "unavailable"},
            "gaze": {"status": "unavailable"},
            "body_pose": {"status": "unavailable"},
            "gesture": {"status": "unavailable"},
        }

    def create_result_bundle(
        self,
        request: VoicePerceptionRequest,
        artifacts: list[PerceptionSignal],
        *,
        status: PerceptionBundleStatus,
        missing_capabilities: tuple[str, ...] = (),
        limitations: tuple[str, ...] = (),
    ) -> PerceptionResultBundle:
        references = tuple(
            PerceptionArtifactReference(
                artifact_id=artifact.id,
                artifact_kind=artifact.artifact_kind or self._legacy_artifact_kind(artifact.type),
                type=artifact.type,
                provider=artifact.provider,
                model=artifact.model,
                model_version=artifact.model_version,
                confidence=artifact.confidence,
                occurrence_started_at=artifact.occurrence_started_at,
                occurrence_ended_at=artifact.occurrence_ended_at,
                lineage=tuple(artifact.lineage),
                sensitivity=artifact.sensitivity,
                retention_class=artifact.retention_class,
            )
            for artifact in artifacts
        )
        semantic = {
            "status": status,
            "voice_session_id": request.voice_session_id,
            "utterance_id": request.utterance_id,
            "transcription_id": request.transcription_id,
            "correlation_reference": request.correlation_reference,
            "artifact_references": [asdict(item) for item in references],
            "provenance": request.provenance,
            "missing_capabilities": missing_capabilities,
            "limitations": limitations,
        }
        fingerprint = hashlib.sha256(
            json.dumps(semantic, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        bundle = PerceptionResultBundle(
            bundle_id=f"perception-bundle-{fingerprint[:24]}",
            fingerprint=fingerprint,
            status=status,
            voice_session_id=request.voice_session_id,
            utterance_id=request.utterance_id,
            transcription_id=request.transcription_id,
            correlation_reference=request.correlation_reference,
            artifact_references=references,
            provenance=request.provenance,
            sensitivity="sensitive",
            missing_capabilities=missing_capabilities,
            limitations=limitations,
        )
        path = self._bundle_path(bundle.bundle_id)
        if path.exists():
            existing = self.get_result_bundle(bundle.bundle_id)
            if existing.fingerprint != bundle.fingerprint:
                raise PerceptionSignalInvalid("Perception bundle identity conflict")
            return existing
        dump_structured_file(path, asdict(bundle))
        return bundle

    def get_result_bundle(self, bundle_id: str) -> PerceptionResultBundle:
        path = self._bundle_path(bundle_id)
        if not path.exists():
            raise NotFound(f"Perception result bundle not found: {bundle_id}")
        raw = load_structured_file(path)
        raw["status"] = PerceptionBundleStatus(raw["status"])
        raw["artifact_references"] = tuple(
            PerceptionArtifactReference(
                **{
                    **item,
                    "artifact_kind": PerceptionArtifactKind(item["artifact_kind"]),
                    "retention_class": RetentionClass(item["retention_class"]),
                    "lineage": tuple(item.get("lineage", [])),
                }
            )
            for item in raw.get("artifact_references", [])
        )
        for field_name in ("provenance", "missing_capabilities", "limitations"):
            raw[field_name] = tuple(raw.get(field_name, []))
        return PerceptionResultBundle(**raw)

    def ingest_signal(self, signal: PerceptionSignal) -> PerceptionSignal:
        policy = self.policy.load()
        normalized = self._validate_and_normalize(signal, policy)
        fingerprint = self._fingerprint(normalized)
        duplicate = next(
            (
                item
                for item in self.list_signals(include_expired=True)
                if item.metadata.get("fingerprint") == fingerprint
            ),
            None,
        )
        if duplicate:
            self.events.emit(
                "perception.signal_received",
                normalized.source,
                {
                    "signal_id": duplicate.id,
                    "duplicate": True,
                    "correlation_id": normalized.correlation_id,
                },
            )
            return duplicate

        normalized = replace(
            normalized,
            metadata={**normalized.metadata, "fingerprint": fingerprint},
        )
        dump_structured_file(self._signal_path(normalized.id), asdict(normalized))
        self.events.emit(
            "perception.signal_received",
            normalized.source,
            self._safe_signal_event(normalized),
        )
        observation = self._observation_from_signal(normalized, policy)
        dump_structured_file(self._observation_path(observation.id), asdict(observation))
        self.events.emit(
            "perception.observation_created",
            "perception",
            self._safe_observation_event(observation),
        )
        self._detect_conflicts(observation)
        self._emit_multimodal(normalized)
        return normalized

    def emit(self, voice_signal: Any) -> None:
        values = dict(getattr(voice_signal, "values", {}) or {})
        metadata = dict(getattr(voice_signal, "metadata", {}) or {})
        signal_type = str(getattr(voice_signal, "type", "voice.signal"))
        modality = "speech" if signal_type.startswith("speech.") else "audio"
        provenance = [{"source": "voice", "voice_signal_id": getattr(voice_signal, "id", None)}]
        input_references = [
            str(value)
            for value in (
                getattr(voice_signal, "recording_id", None),
                getattr(voice_signal, "utterance_id", None),
            )
            if value
        ]
        self.ingest_signal(
            PerceptionSignal(
                id=str(
                    getattr(voice_signal, "id", "")
                    or PerceptionSignal(
                        type=signal_type, modality=modality, source="voice", values={}
                    ).id
                ),
                type=signal_type,
                modality=modality,
                source="voice",
                timestamp=str(getattr(voice_signal, "timestamp", "") or _now()),
                session_id=getattr(voice_signal, "session_id", None),
                conversation_id=getattr(voice_signal, "conversation_id", None),
                confidence=getattr(voice_signal, "confidence", None),
                values=values,
                provenance=provenance,
                sensitivity="sensitive"
                if "transcript" in values or "text" in values
                else "internal",
                correlation_id=getattr(voice_signal, "correlation_id", None),
                metadata={
                    **metadata,
                    "utterance_id": getattr(voice_signal, "utterance_id", None),
                    "recording_id": getattr(voice_signal, "recording_id", None),
                },
                artifact_kind=(
                    PerceptionArtifactKind.RAW_OBSERVATION
                    if signal_type in {"speech.started", "speech.ended", "voice.activity"}
                    else None
                ),
                source_identity="voice_runtime",
                occurrence_started_at=str(getattr(voice_signal, "timestamp", "") or _now()),
                occurrence_ended_at=str(getattr(voice_signal, "timestamp", "") or _now()),
                input_references=input_references,
                lineage=input_references,
            )
        )

    def create_signal(
        self,
        signal_type: str,
        source_runtime: str,
        payload: dict[str, Any],
        source_provider: str | None = None,
        session_id: str | None = None,
        multimodal_session_id: str | None = None,
        confidence: float | None = None,
        metadata: dict[str, Any] | None = None,
        artifact_kind: PerceptionArtifactKind | None = None,
        retention_class: RetentionClass = RetentionClass.POLICY_PERSISTABLE,
        model: str | None = None,
        model_version: str | None = None,
        input_references: list[str] | None = None,
    ) -> PerceptionSignal:
        modality = self._legacy_modality(signal_type)
        supplied_metadata = dict(metadata or {})
        conversation_id = supplied_metadata.pop("conversation_id", None)
        mission_id = supplied_metadata.pop("mission_id", None)
        task_id = supplied_metadata.pop("task_id", None)
        agent_id = supplied_metadata.pop("agent_id", None)
        provenance = [{"source": source_runtime}]
        if source_provider:
            provenance[0]["provider"] = source_provider
        return self.ingest_signal(
            PerceptionSignal(
                type=signal_type,
                modality=modality,
                source=source_runtime,
                values=payload,
                session_id=session_id,
                conversation_id=str(conversation_id) if conversation_id else None,
                mission_id=str(mission_id) if mission_id else None,
                task_id=str(task_id) if task_id else None,
                agent_id=str(agent_id) if agent_id else None,
                confidence=confidence,
                provenance=provenance,
                correlation_id=current_correlation_fields().get("correlation_id"),
                metadata={**supplied_metadata, "multimodal_session_id": multimodal_session_id},
                artifact_kind=artifact_kind,
                retention_class=retention_class,
                provider=source_provider,
                model=model,
                model_version=model_version,
                input_references=list(input_references or []),
            )
        )

    def emit_signal(self, signal: PerceptionSignal) -> PerceptionSignal:
        # Canonical ingestion already emitted the correlated event. Retained as a
        # compatibility no-op so callers cannot create duplicate observations/events.
        return signal

    def get_signal(self, signal_id: str) -> PerceptionSignal:
        path = self._signal_path(signal_id)
        if not path.exists():
            raise NotFound(f"Perception signal not found: {signal_id}")
        return self._signal_from_raw(load_structured_file(path))

    def list_signals(
        self,
        *,
        session_id: str | None = None,
        conversation_id: str | None = None,
        mission_id: str | None = None,
        correlation_id: str | None = None,
        include_expired: bool = False,
    ) -> list[PerceptionSignal]:
        signals = [
            self._signal_from_raw(load_structured_file(path))
            for path in sorted(self._signals_root().glob("*.json"))
        ]
        signals.extend(self._legacy_signals())
        if not include_expired:
            signals = [item for item in signals if not _is_expired(item.expires_at)]
        filters = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "mission_id": mission_id,
            "correlation_id": correlation_id,
        }
        for field_name, value in filters.items():
            if value is not None:
                signals = [item for item in signals if getattr(item, field_name) == value]
        unique = {item.id: item for item in signals}
        return sorted(unique.values(), key=lambda item: (item.timestamp, item.id))

    def list_signals_by_session(self, session_id: str) -> list[PerceptionSignal]:
        return self.list_signals(session_id=session_id)

    def list_signals_by_type(self, signal_type: str) -> list[PerceptionSignal]:
        return [item for item in self.list_signals() if item.type == signal_type]

    def get_observation(
        self, observation_id: str, *, allow_expired: bool = False
    ) -> PerceptionObservation:
        path = self._observation_path(observation_id)
        if not path.exists():
            raise ObservationNotFound(f"Observation not found: {observation_id}")
        observation = PerceptionObservation(**load_structured_file(path))
        if not allow_expired and _is_expired(observation.valid_until):
            raise ObservationExpired(f"Observation expired: {observation_id}")
        return observation

    def list_observations(
        self,
        *,
        session_id: str | None = None,
        conversation_id: str | None = None,
        mission_id: str | None = None,
        correlation_id: str | None = None,
        include_expired: bool = False,
    ) -> list[PerceptionObservation]:
        observations = [
            PerceptionObservation(**load_structured_file(path))
            for path in sorted(self._observations_root().glob("*.json"))
        ]
        if not include_expired:
            observations = [item for item in observations if not _is_expired(item.valid_until)]
        filters = {
            "session_id": session_id,
            "conversation_id": conversation_id,
            "mission_id": mission_id,
            "correlation_id": correlation_id,
        }
        for field_name, value in filters.items():
            if value is not None:
                observations = [item for item in observations if getattr(item, field_name) == value]
        return sorted(observations, key=lambda item: (item.timestamp, item.id))

    def expire_observation(self, observation_id: str) -> PerceptionObservation:
        observation = self.get_observation(observation_id, allow_expired=True)
        updated = replace(observation, valid_until=_now())
        dump_structured_file(self._observation_path(observation_id), asdict(updated))
        self.events.emit(
            "perception.observation_expired", "perception", {"observation_id": observation_id}
        )
        return updated

    def delete_observation(self, observation_id: str) -> None:
        self.get_observation(observation_id, allow_expired=True)
        self._observation_path(observation_id).unlink()

    def list_conflicts(self) -> list[PerceptionConflict]:
        return [
            PerceptionConflict(**load_structured_file(path))
            for path in sorted(self._conflicts_root().glob("*.json"))
        ]

    def create_batch(
        self,
        signals: list[PerceptionSignal],
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PerceptionBatch:
        batch = PerceptionBatch(
            session_id=session_id, signals=signals, metadata=redact(metadata or {})
        )
        dump_structured_file(self._batch_path(batch.batch_id), self._batch_payload(batch))
        return batch

    def summarize_batch(self, batch_id: str) -> SignalSummary:
        path = self._batch_path(batch_id)
        if not path.exists():
            raise NotFound(f"Perception batch not found: {batch_id}")
        raw = load_structured_file(path)
        return self._summarize(
            [self._signal_from_raw(item) for item in raw.get("signals", [])], {"batch_id": batch_id}
        )

    def summarize_session(self, session_id: str) -> SignalSummary:
        return self._summarize(self.list_signals(session_id=session_id), {"session_id": session_id})

    def cleanup(self, *, dry_run: bool = True, now: datetime | None = None) -> CleanupResult:
        instant = now or datetime.now(UTC)
        signal_paths = [
            path
            for path in self._signals_root().glob("*.json")
            if _path_expired(path, "expires_at", instant)
        ]
        observation_paths = [
            path
            for path in self._observations_root().glob("*.json")
            if _path_expired(path, "valid_until", instant)
        ]
        raw_paths = self._expired_raw_assets(instant)
        deleted: list[str] = []
        if not dry_run:
            try:
                for path in [*signal_paths, *observation_paths, *raw_paths]:
                    relative = path.relative_to(self.data_dir.root).as_posix()
                    path.unlink(missing_ok=True)
                    deleted.append(relative)
            except OSError as exc:
                raise RetentionFailed(
                    "Perception retention cleanup failed", details={"error": str(exc)}
                ) from exc
        result = CleanupResult(
            dry_run, len(signal_paths), len(observation_paths), len(raw_paths), deleted
        )
        self.events.emit("perception.retention_cleanup", "perception", asdict(result))
        return result

    def retention_status(self) -> dict[str, Any]:
        policy = self.policy.load()
        return {
            "signal_retention_hours": policy["signal_retention_hours"],
            "observation_retention_days": policy["observation_retention_days"],
            "raw_visual_retention_minutes": policy["raw_visual_retention_minutes"],
            "persist_raw_visual": policy["persist_raw_visual"],
        }

    def signal_from_speech_to_text(
        self,
        result: SpeechToTextResult,
        session_id: str | None = None,
        multimodal_session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PerceptionSignal:
        return self.create_signal(
            "speech",
            "audio",
            asdict(result),
            result.provider_id,
            session_id,
            multimodal_session_id,
            result.confidence,
            metadata,
        )

    def signal_from_text_to_speech(
        self,
        result: TextToSpeechResult,
        session_id: str | None = None,
        multimodal_session_id: str | None = None,
    ) -> PerceptionSignal:
        return self.create_signal(
            "voice", "audio", asdict(result), result.provider_id, session_id, multimodal_session_id
        )

    def _validate_and_normalize(
        self, signal: PerceptionSignal, policy: dict[str, Any]
    ) -> PerceptionSignal:
        try:
            if not policy.get("enabled", True):
                raise PerceptionSignalDenied("Perception is disabled by policy")
            if not signal.type.strip() or signal.modality not in MODALITIES:
                raise PerceptionSignalInvalid("Invalid signal type or modality")
            if signal.source not in set(policy["allowed_sources"]):
                raise PerceptionSignalDenied(
                    "Perception source is not authorized", details={"source": signal.source}
                )
            if signal.sensitivity not in SENSITIVITY_LEVELS:
                raise PerceptionSignalInvalid("Invalid signal sensitivity")
            if signal.confidence is not None and not 0 <= float(signal.confidence) <= 1:
                raise PerceptionSignalInvalid("Signal confidence must be between 0 and 1")
            artifact_kind = signal.artifact_kind or self._legacy_artifact_kind(signal.type)
            if signal.retention_class == RetentionClass.TRANSIENT_ONLY:
                raise PerceptionSignalInvalid("Transient-only artifacts cannot be durably ingested")
            semantic_fields = {"emotion", "engagement", "angry", "user_is_engaged"}
            if artifact_kind != PerceptionArtifactKind.MODEL_INFERENCE and (
                semantic_fields & {key.lower() for key in signal.values}
            ):
                raise PerceptionSignalInvalid(
                    "Semantic inference cannot be recorded as an observation or feature"
                )
            if artifact_kind == PerceptionArtifactKind.MODEL_INFERENCE:
                if not signal.provider or not signal.model or not signal.model_version:
                    raise PerceptionSignalInvalid(
                        "Model inference requires provider, model, and model version"
                    )
            if artifact_kind == PerceptionArtifactKind.CONTEXTUAL_INTERPRETATION and (
                not signal.external_interpretation_owner
                or not signal.external_interpretation_reference
            ):
                raise PerceptionSignalInvalid(
                    "Contextual interpretation requires an external owner and reference"
                )
            timestamp = _parse_time(signal.timestamp)
            if timestamp > datetime.now(UTC) + timedelta(minutes=5):
                raise PerceptionSignalInvalid("Signal timestamp is in the future")
            values = redact(signal.values)
            if not policy.get("persist_transcripts", False):
                values = {
                    key: ("[REDACTED]" if key.lower() in {"text", "transcript"} else value)
                    for key, value in values.items()
                }
            if len(json.dumps(values, default=str).encode("utf-8")) > int(
                policy["max_signal_bytes"]
            ):
                raise PerceptionSignalInvalid("Signal exceeds maximum size")
            expires_at = (
                signal.expires_at
                or (timestamp + timedelta(hours=int(policy["signal_retention_hours"]))).isoformat()
            )
            correlation_id = (
                signal.correlation_id
                or current_correlation_fields().get("correlation_id")
                or signal.id
            )
            return replace(
                signal,
                type=signal.type.strip(),
                values=values,
                metadata=redact(signal.metadata),
                expires_at=expires_at,
                correlation_id=correlation_id,
                artifact_kind=artifact_kind,
                occurrence_started_at=signal.occurrence_started_at or signal.timestamp,
                occurrence_ended_at=signal.occurrence_ended_at or signal.timestamp,
            )
        except (PerceptionSignalInvalid, PerceptionSignalDenied) as exc:
            self.events.emit(
                "perception.signal_rejected",
                signal.source,
                {
                    "signal_id": signal.id,
                    "reason": getattr(exc, "code", "perception_signal_invalid"),
                },
            )
            raise

    def _observation_from_signal(
        self, signal: PerceptionSignal, policy: dict[str, Any]
    ) -> PerceptionObservation:
        supplied_description = signal.values.get("description")
        summary = signal.values.get("summary") or signal.values.get("event") or signal.type
        description = (
            {**supplied_description, "modality": signal.modality}
            if isinstance(supplied_description, dict)
            else {"summary": summary, "modality": signal.modality}
        )
        valid_until = (
            datetime.now(UTC) + timedelta(days=int(policy["observation_retention_days"]))
        ).isoformat()
        if signal.expires_at and _parse_time(signal.expires_at) < _parse_time(valid_until):
            valid_until = signal.expires_at
        return PerceptionObservation(
            type=signal.type,
            description=description,
            signal_ids=[signal.id],
            confidence=signal.confidence,
            relevance=self._recency_relevance(signal.timestamp),
            timestamp=signal.timestamp,
            valid_until=valid_until,
            entities=[item for item in signal.values.get("entities", []) if isinstance(item, dict)]
            if isinstance(signal.values.get("entities"), list)
            else [],
            attributes=signal.values.get("attributes", {})
            if isinstance(signal.values.get("attributes"), dict)
            else {},
            provenance=[*signal.provenance, {"signal_id": signal.id, "source": signal.source}],
            sensitivity=signal.sensitivity,
            correlation_id=signal.correlation_id,
            session_id=signal.session_id,
            conversation_id=signal.conversation_id,
            mission_id=signal.mission_id,
            task_id=signal.task_id,
            agent_id=signal.agent_id,
            warnings=signal.values.get("warnings", [])
            if isinstance(signal.values.get("warnings"), list)
            else [],
            metadata={"modality": signal.modality, "source": signal.source},
            artifact_kind=signal.artifact_kind,
            retention_class=signal.retention_class,
            input_references=[signal.id, *signal.input_references],
        )

    def _detect_conflicts(self, observation: PerceptionObservation) -> None:
        entity_keys = {
            str(item.get("id") or item.get("name"))
            for item in observation.entities
            if item.get("id") or item.get("name")
        }
        if not entity_keys or not observation.attributes:
            return
        for existing in self.list_observations(include_expired=False):
            if existing.id == observation.id or existing.type != observation.type:
                continue
            existing_keys = {
                str(item.get("id") or item.get("name"))
                for item in existing.entities
                if item.get("id") or item.get("name")
            }
            contradictions = {
                key: [existing.attributes[key], observation.attributes[key]]
                for key in existing.attributes.keys() & observation.attributes.keys()
                if existing.attributes[key] != observation.attributes[key]
            }
            if entity_keys & existing_keys and contradictions:
                conflict = PerceptionConflict(
                    [existing.id, observation.id],
                    "contradictory_attributes",
                    attributes=contradictions,
                    correlation_id=observation.correlation_id,
                )
                dump_structured_file(self._conflict_path(conflict.id), asdict(conflict))
                self.events.emit(
                    "perception.conflict_detected",
                    "perception",
                    {
                        "conflict_id": conflict.id,
                        "observation_ids": conflict.observation_ids,
                        "reason": conflict.reason,
                        "correlation_id": conflict.correlation_id,
                    },
                )

    def _emit_multimodal(self, signal: PerceptionSignal) -> None:
        session_id = signal.multimodal_session_id
        if not session_id:
            return
        legacy_channel = signal.type if signal.type in {"face", "body"} else None
        self.multimodal.emit_event(
            session_id,
            legacy_channel or CHANNEL_BY_MODALITY[signal.modality],
            "perception.signal",
            signal.source,
            {"signal_id": signal.id, "type": signal.type, "modality": signal.modality},
            metadata={"confidence": signal.confidence, "sensitivity": signal.sensitivity},
            correlation_id=signal.correlation_id,
        )

    def _summarize(
        self, signals: list[PerceptionSignal], metadata: dict[str, Any]
    ) -> SignalSummary:
        by_type: dict[str, int] = {}
        confidences: list[float] = []
        for signal in signals:
            by_type[signal.type] = by_type.get(signal.type, 0) + 1
            if signal.confidence is not None:
                confidences.append(float(signal.confidence))
        return SignalSummary(
            len(signals),
            by_type,
            sum(confidences) / len(confidences) if confidences else None,
            sorted({item.source for item in signals}),
            len(self.list_observations(session_id=metadata.get("session_id"))),
            sum(_is_expired(item.expires_at) for item in signals),
            metadata,
        )

    def _legacy_signals(self) -> list[PerceptionSignal]:
        path = self.data_dir.resolve("perception/signals.jsonl")
        if not path.exists():
            return []
        result = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                result.append(self._signal_from_raw(json.loads(line)))
        return result

    @staticmethod
    def _signal_from_raw(raw: dict[str, Any]) -> PerceptionSignal:
        if "signal_id" in raw:
            provider = raw.get("source_provider")
            return PerceptionSignal(
                type=raw.get("signal_type", "system"),
                modality=PerceptionRuntime._legacy_modality(raw.get("signal_type", "system")),
                source=raw.get("source_runtime", "system"),
                values=raw.get("payload", {}),
                id=raw["signal_id"],
                timestamp=raw.get("timestamp", _now()),
                session_id=raw.get("session_id"),
                confidence=raw.get("confidence"),
                provenance=[{"source": raw.get("source_runtime", "system"), "provider": provider}]
                if provider
                else [{"source": raw.get("source_runtime", "system")}],
                correlation_id=raw.get("correlation_id"),
                metadata={
                    **raw.get("metadata", {}),
                    "multimodal_session_id": raw.get("multimodal_session_id"),
                },
            )
        return PerceptionSignal(**raw)

    @staticmethod
    def _legacy_modality(signal_type: str) -> str:
        if signal_type.startswith("speech"):
            return "speech"
        if signal_type in {"voice", "stress", "silence"} or signal_type.startswith("voice."):
            return "audio"
        if signal_type.startswith(("vision.", "face.", "body.", "gaze.", "gesture.")) or signal_type in {
            "face",
            "body",
            "gaze",
            "gesture",
            "emotion",
            "engagement",
        }:
            return "vision"
        return "system"

    @staticmethod
    def _legacy_artifact_kind(signal_type: str) -> PerceptionArtifactKind:
        raw_types = {
            "voice.activity",
            "speech.started",
            "speech.ended",
            "audio.pcm",
            "vision.frame",
            "camera.frame",
        }
        return (
            PerceptionArtifactKind.RAW_OBSERVATION
            if signal_type in raw_types
            else PerceptionArtifactKind.DERIVED_FEATURE
        )

    @staticmethod
    def _fingerprint(signal: PerceptionSignal) -> str:
        raw = {
            "type": signal.type,
            "modality": signal.modality,
            "source": signal.source,
            "values": signal.values,
            "session_id": signal.session_id,
            "conversation_id": signal.conversation_id,
            "mission_id": signal.mission_id,
            "artifact_kind": signal.artifact_kind,
        }
        return hashlib.sha256(json.dumps(raw, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _recency_relevance(timestamp: str) -> float:
        age = max(0.0, (datetime.now(UTC) - _parse_time(timestamp)).total_seconds())
        return round(max(0.0, 1.0 - age / 3600.0), 4)

    @staticmethod
    def _safe_signal_event(signal: PerceptionSignal) -> dict[str, Any]:
        return {
            "signal_id": signal.id,
            "type": signal.type,
            "modality": signal.modality,
            "source": signal.source,
            "confidence": signal.confidence,
            "sensitivity": signal.sensitivity,
            "correlation_id": signal.correlation_id,
        }

    @staticmethod
    def _safe_observation_event(observation: PerceptionObservation) -> dict[str, Any]:
        return {
            "observation_id": observation.id,
            "type": observation.type,
            "signal_ids": observation.signal_ids,
            "confidence": observation.confidence,
            "sensitivity": observation.sensitivity,
            "correlation_id": observation.correlation_id,
        }

    def _expired_raw_assets(self, instant: datetime) -> list[Path]:
        minutes = int(self.policy.load()["raw_visual_retention_minutes"])
        root = self.data_dir.resolve("vision/raw")
        if not root.exists():
            return []
        cutoff = instant - timedelta(minutes=minutes)
        return [
            path
            for path in root.iterdir()
            if path.is_file()
            and not path.name.endswith(".active")
            and not Path(f"{path}.active").exists()
            and datetime.fromtimestamp(path.stat().st_mtime, UTC) <= cutoff
        ]

    def _signals_root(self) -> Path:
        root = self.data_dir.resolve("perception/signals")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _observations_root(self) -> Path:
        root = self.data_dir.resolve("perception/observations")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _conflicts_root(self) -> Path:
        root = self.data_dir.resolve("perception/conflicts")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _signal_path(self, signal_id: str) -> Path:
        return self._signals_root() / f"{signal_id}.json"

    def _observation_path(self, observation_id: str) -> Path:
        return self._observations_root() / f"{observation_id}.json"

    def _conflict_path(self, conflict_id: str) -> Path:
        return self._conflicts_root() / f"{conflict_id}.json"

    def _batch_path(self, batch_id: str) -> Path:
        root = self.data_dir.resolve("perception/batches")
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{batch_id}.yaml"

    def _bundle_path(self, bundle_id: str) -> Path:
        root = self.data_dir.resolve("perception/bundles")
        root.mkdir(parents=True, exist_ok=True)
        return root / f"{bundle_id}.json"

    @staticmethod
    def _batch_payload(batch: PerceptionBatch) -> dict[str, Any]:
        return {
            "batch_id": batch.batch_id,
            "session_id": batch.session_id,
            "signals": [asdict(signal) for signal in batch.signals],
            "created_at": batch.created_at,
            "metadata": batch.metadata,
        }


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PerceptionSignalInvalid("Invalid ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise PerceptionSignalInvalid("Timestamp must include timezone")
    return parsed.astimezone(UTC)


def _is_expired(value: str | None) -> bool:
    return bool(value and _parse_time(value) <= datetime.now(UTC))


def _path_expired(path: Path, field_name: str, instant: datetime) -> bool:
    raw = load_structured_file(path)
    value = raw.get(field_name)
    return bool(value and _parse_time(str(value)) <= instant)
