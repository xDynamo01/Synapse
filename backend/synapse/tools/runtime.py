from __future__ import annotations

import hashlib
import json
from contextvars import copy_context
from dataclasses import asdict
from datetime import UTC, datetime
from queue import Queue
from threading import Thread
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from synapse.agents.admin import AgentAdminRuntime
from synapse.audio.models import AudioInputRequest
from synapse.conversations.runtime import ConversationRuntime
from synapse.core.data_dir import DataDir
from synapse.core.events import EventBus
from synapse.core.exceptions import NotFound, ValidationError
from synapse.core.serialization import load_structured_file
from synapse.health.contracts import HealthSnapshotSource
from synapse.intelligence_boundary.models import (
    DataClassification,
    EgressRequest,
    InformationAsset,
    InformationOwnership,
    ProcessingBoundary,
    ProcessingPurpose,
    TrainingUsePolicy,
)
from synapse.missions.runtime import MissionRuntime
from synapse.observability.redaction import redact
from synapse.providers.runtime import ProviderRuntime
from synapse.readiness.contracts import ReadinessSnapshotSource
from synapse.resources.models import ResourceRef
from synapse.tools.errors import ToolError
from synapse.tools.models import (
    ToolCallPreview,
    ToolDefinition,
    ToolExecutionDecision,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolHandler,
    ToolHealth,
)
from synapse.tools.permission_bridge import ToolPermissionBridge
from synapse.tools.registry import RuntimeToolRegistry
from synapse.voice.runtime import VoiceRuntime

if TYPE_CHECKING:
    from synapse.intelligence_boundary.contracts import IntelligenceEgressPort


class ToolRuntime:
    def __init__(
        self,
        data_dir: DataDir,
        event_bus: EventBus,
        registry: RuntimeToolRegistry | None = None,
        permission_bridge: ToolPermissionBridge | None = None,
    ):
        self.data_dir = data_dir
        self.event_bus = event_bus
        self.registry = registry or RuntimeToolRegistry()
        self.permission_bridge = permission_bridge
        self.egress_gate: IntelligenceEgressPort | None = None
        self.execution_counts: dict[str, int] = {}
        self.failure_counts: dict[str, int] = {}
        self._results: dict[str, ToolExecutionResult] = {}
        self._requests: dict[str, ToolExecutionRequest] = {}
        self._idempotency: dict[str, str] = {}
        self._verifications: dict[str, dict[str, Any]] = {}
        self.log_path = self.data_dir.resolve("tools/execution_log.jsonl")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_history()

    def register(self, definition: ToolDefinition, handler: ToolHandler) -> None:
        self.registry.register(definition, handler)

    def execute(self, request: ToolExecutionRequest) -> ToolExecutionResult:
        return self.execute_tool_call(request)

    def preview(self, request: ToolExecutionRequest) -> ToolCallPreview:
        registered = self.registry.get_tool(request.tool_id)
        if not registered.definition.supports_preview:
            raise ToolError(
                "preview_not_supported",
                f"Preview is not supported: {request.tool_id}",
                status_code=422,
            )
        arguments = self._validate_arguments(registered.definition, request.arguments)
        decision = self._decision(registered.definition, request)
        permissions = list(registered.definition.permissions_required)
        if registered.definition.required_permission:
            permissions.append(registered.definition.required_permission)
        targets = [str(request.resource_ref)] if request.resource_ref else []
        config_hash = hashlib.sha256(
            json.dumps(
                {
                    "tool_id": request.tool_id,
                    "arguments": arguments,
                    "requester": request.requester or request.caller,
                    "agent_id": request.agent_id,
                    "targets": targets,
                    "permissions": sorted(set(permissions)),
                    "risk": registered.definition.risk_level,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return ToolCallPreview(
            request.tool_id,
            arguments,
            sorted(set(permissions)),
            registered.definition.risk_level,
            decision.requires_approval,
            list(registered.definition.metadata.get("side_effects", [])),
            registered.definition.supports_rollback,
            registered.definition.timeout_default,
            list(decision.reasons),
            list(decision.blocked_reasons),
            targets,
            config_hash,
        )

    def execute_tool_call(
        self, request: ToolExecutionRequest, options: dict[str, Any] | None = None
    ) -> ToolExecutionResult:
        options = options or {}
        started = perf_counter()
        started_at = datetime.now(UTC).isoformat()
        call_id = request.id or str(uuid4())
        egress_asset_id: str | None = None
        egress_manifest_id: str | None = None
        if request.idempotency_key and request.idempotency_key in self._idempotency:
            return self._results[self._idempotency[request.idempotency_key]]
        decision: ToolExecutionDecision | None = None
        try:
            registered = self.registry.get_tool(request.tool_id)
            if not registered.definition.enabled:
                reason = registered.definition.metadata.get("unavailable_reason")
                raise ValidationError(str(reason or f"Tool is disabled: {request.tool_id}"))
            if request.dry_run and not registered.definition.supports_dry_run:
                raise ToolError(
                    "dry_run_not_supported",
                    f"Dry-run is not supported: {request.tool_id}",
                    status_code=422,
                )
            normalized = self._validate_arguments(registered.definition, request.arguments)
            request = ToolExecutionRequest(
                **{**request.__dict__, "arguments": normalized, "id": call_id}
            )
            decision = self._decision(registered.definition, request)
            if decision.blocked or decision.requires_approval or request.dry_run:
                duration_ms = int((perf_counter() - started) * 1000)
                self.execution_counts[request.tool_id] = (
                    self.execution_counts.get(request.tool_id, 0) + 1
                )
                if decision.blocked:
                    self.failure_counts[request.tool_id] = (
                        self.failure_counts.get(request.tool_id, 0) + 1
                    )
                result = ToolExecutionResult(
                    success=False if decision.blocked or decision.requires_approval else True,
                    tool_id=request.tool_id,
                    output={},
                    duration_ms=duration_ms,
                    error="; ".join(decision.blocked_reasons) if decision.blocked else None,
                    metadata={
                        "dry_run": request.dry_run,
                        "decision": asdict(decision),
                        "approval_required": decision.requires_approval,
                        "approval_id": decision.approval_id,
                    },
                    call_id=call_id,
                    status="awaiting_approval"
                    if decision.requires_approval
                    else ("failed" if decision.blocked else "completed"),
                    started_at=started_at,
                    completed_at=datetime.now(UTC).isoformat(),
                )
                self._record_verification(
                    call_id,
                    request.tool_id,
                    not decision.blocked and not decision.requires_approval,
                    {},
                )
                self._log_execution(request, result, decision)
                self._remember_result(request, result)
                return result
            if self.egress_gate is not None:
                egress_asset_id, egress_manifest_id = self._authorize_tool_egress(
                    registered.definition, request
                )
            self.event_bus.emit(
                "tool_runtime.execution_started",
                request.caller,
                {
                    "tool_id": request.tool_id,
                    "conversation_id": request.conversation_id,
                    "mission_id": request.mission_id,
                },
            )
            running = ToolExecutionResult(
                success=False,
                tool_id=request.tool_id,
                output={},
                metadata={"decision": asdict(decision)},
                call_id=call_id,
                status="running",
                started_at=started_at,
            )
            self._remember_result(request, running)
            output = self._invoke_handler(
                registered.handler,
                request,
                request.timeout_seconds or registered.definition.timeout_default,
            )
            duration_ms = int((perf_counter() - started) * 1000)
            current = self._results.get(call_id)
            if current is not None and current.status == "cancelled":
                return current
            self.execution_counts[request.tool_id] = (
                self.execution_counts.get(request.tool_id, 0) + 1
            )
            result = ToolExecutionResult(
                success=True,
                tool_id=request.tool_id,
                output=output,
                duration_ms=duration_ms,
                metadata={
                    "decision": asdict(decision),
                    "egress_manifest_id": egress_manifest_id,
                },
                call_id=call_id,
                status="completed",
                structured_output=output,
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            self._record_verification(call_id, request.tool_id, True, output)
            self._log_execution(request, result, decision)
            self._remember_result(request, result)
            if self.egress_gate is not None and egress_asset_id:
                output_encoded = json.dumps(output, sort_keys=True, default=str).encode()
                derived = self.egress_gate.register_derived_asset(
                    asset_id=f"tool-output-{uuid4().hex}",
                    input_asset_ids=(egress_asset_id,),
                    source_reference=f"tool:{request.tool_id}:{call_id}",
                    content_type="application/json",
                    output_checksum=hashlib.sha256(output_encoded).hexdigest(),
                    purpose=ProcessingPurpose.TOOL_EXECUTION,
                    provider_id=registered.definition.provider_id,
                    manifest_id=egress_manifest_id,
                )
                if egress_manifest_id:
                    self.egress_gate.complete_egress(
                        egress_manifest_id, result_reference=derived.asset_id
                    )
            if request.approval_id and self.permission_bridge:
                from synapse.core.permissions import PermissionContext

                self.permission_bridge.approvals.mark_resumed(
                    PermissionContext(
                        actor_id=request.agent_id or request.caller,
                        actor_type="agent" if request.agent_id else request.caller_type,
                    ),
                    request.approval_id,
                    asdict(result),
                )
            self.event_bus.emit(
                "tool_runtime.execution_completed",
                request.caller,
                {"tool_id": request.tool_id, "success": True, "duration_ms": duration_ms},
            )
            return result
        except Exception as exc:
            current = self._results.get(call_id)
            if current is not None and current.status == "cancelled":
                return current
            duration_ms = int((perf_counter() - started) * 1000)
            self.execution_counts[request.tool_id] = (
                self.execution_counts.get(request.tool_id, 0) + 1
            )
            self.failure_counts[request.tool_id] = self.failure_counts.get(request.tool_id, 0) + 1
            timed_out = isinstance(exc, TimeoutError)
            result = ToolExecutionResult(
                success=False,
                tool_id=request.tool_id,
                output={},
                duration_ms=duration_ms,
                error=str(exc) or type(exc).__name__,
                metadata={"error_type": type(exc).__name__},
                call_id=call_id,
                status="timed_out" if timed_out else "failed",
                started_at=started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            self._record_verification(call_id, request.tool_id, False, {})
            self._log_execution(request, result, decision)
            self._remember_result(request, result)
            self.event_bus.emit(
                "tool_runtime.execution_failed",
                request.caller,
                {
                    "tool_id": request.tool_id,
                    "success": False,
                    "duration_ms": duration_ms,
                    "error": result.error,
                    "error_type": type(exc).__name__,
                },
            )
            if options.get("raise_errors"):
                raise
            return result

    def list_tools(self) -> list[ToolDefinition]:
        return self.registry.list_tools()

    def get_tool(self, tool_id: str) -> ToolDefinition:
        return self.registry.get_tool(tool_id).definition

    def validate_call(self, request: ToolExecutionRequest) -> dict[str, Any]:
        definition = self.get_tool(request.tool_id)
        return self._validate_arguments(definition, request.arguments)

    def list_executions(self) -> list[ToolExecutionResult]:
        return sorted(
            self._results.values(),
            key=lambda result: (result.started_at or "", result.call_id or ""),
        )

    def health(self) -> dict[str, ToolHealth]:
        health: dict[str, ToolHealth] = {}
        for definition in self.list_tools():
            health[definition.tool_id] = ToolHealth(
                available=True,
                enabled=definition.enabled,
                execution_count=self.execution_counts.get(definition.tool_id, 0),
                failure_count=self.failure_counts.get(definition.tool_id, 0),
            )
        return health

    def summary(self) -> dict[str, Any]:
        tools = self.list_tools()
        health = self.health()
        return {
            "available": True,
            "tool_count": len(tools),
            "enabled_tools": len([tool for tool in tools if tool.enabled]),
            "execution_count": sum(item.execution_count for item in health.values()),
            "failure_count": sum(item.failure_count for item in health.values()),
            "tools": [asdict(tool) for tool in tools],
        }

    def _decision(
        self,
        definition: ToolDefinition,
        request: ToolExecutionRequest,
    ) -> ToolExecutionDecision:
        if self.permission_bridge:
            return self.permission_bridge.evaluate(definition, request)
        return ToolExecutionDecision(
            allowed=False,
            blocked=True,
            requires_approval=False,
            reasons=[],
            blocked_reasons=["permission bridge unavailable; execution denied"],
        )

    def _authorize_tool_egress(
        self, definition: ToolDefinition, request: ToolExecutionRequest
    ) -> tuple[str, str | None]:
        assert self.egress_gate is not None
        encoded = json.dumps(request.arguments, sort_keys=True, default=str).encode()
        payload_checksum = hashlib.sha256(encoded).hexdigest()
        asset_id = f"tool-input-{payload_checksum[:24]}"
        self.egress_gate.ensure_asset(
            InformationAsset(
                asset_id=asset_id,
                owner=InformationOwnership(
                    request.metadata.get("information_owner", "user-owned")
                ),
                project_id=request.metadata.get("project_id"),
                source_domain="tools",
                source_reference=f"tool:{definition.tool_id}",
                content_type="application/json",
                classification=DataClassification(
                    request.metadata.get("classification", "internal")
                ),
                categories=tuple(request.metadata.get("categories", ("tool.input",))),
                training_use_policy=TrainingUsePolicy(
                    request.metadata.get("training_use_policy", "prohibited")
                ),
                external_processing_policy=str(
                    request.metadata.get(
                        "external_processing_policy", "policy-controlled"
                    )
                ),
                metadata={"estimated_tokens": max(1, len(encoded) // 4)},
            )
        )
        declared_boundary = definition.metadata.get("processing_boundary")
        if declared_boundary is None and (
            definition.provider_id != "internal" or definition.source != "builtin"
        ):
            declared_boundary = ProcessingBoundary.EXTERNAL_TOOL.value
        boundary = ProcessingBoundary(declared_boundary or "local_process")
        provider_id = definition.provider_id
        if boundary not in {
            ProcessingBoundary.LOCAL_PROCESS,
            ProcessingBoundary.LOCAL_MODEL,
            ProcessingBoundary.LOCAL_NETWORK,
            ProcessingBoundary.USER_DEVICE,
            ProcessingBoundary.AIR_GAPPED,
        }:
            provider_id = str(
                definition.metadata.get("provider_id")
                or definition.metadata.get("server_id")
                or definition.provider_id
            )
        authorization = self.egress_gate.authorize_egress(
            EgressRequest(
                asset_ids=(asset_id,),
                requester=request.requester or request.caller,
                destination=str(
                    definition.metadata.get("destination") or provider_id or definition.tool_id
                ),
                boundary=boundary,
                purpose=ProcessingPurpose.TOOL_EXECUTION,
                provider_id=provider_id,
                project_id=request.metadata.get("project_id"),
                rfc_id=request.metadata.get("rfc_id"),
                rfc_revision=request.metadata.get("rfc_revision"),
                mission_id=request.mission_id,
                task_id=request.metadata.get("task_id"),
                payload_checksum=payload_checksum,
                estimated_size=len(encoded),
                estimated_tokens=max(1, len(encoded) // 4),
                correlation_id=request.correlation_id or "",
                actor_type=request.caller_type,
                approval_reference=request.metadata.get("egress_approval_id"),
                constraints=tuple(request.metadata.get("egress_constraints", ())),
            )
        )
        return (
            asset_id,
            authorization.manifest.manifest_id if authorization.manifest else None,
        )

    def get_result(self, call_id: str) -> ToolExecutionResult:
        try:
            return self._results[call_id]
        except KeyError as exc:
            raise ToolError(
                "tool_not_found", f"Tool execution not found: {call_id}", status_code=404
            ) from exc

    def cancel(self, call_id: str) -> ToolExecutionResult:
        current = self.get_result(call_id)
        if current.status == "cancelled":
            return current
        if current.status in {"completed", "failed", "timed_out", "rolled_back"}:
            raise ToolError(
                "execution_conflict", f"Execution is already terminal: {call_id}", status_code=409
            )
        request = self._requests[call_id]
        registered = self.registry.get_tool(current.tool_id)
        cancel = getattr(registered.handler, "cancel", None)
        if not registered.definition.supports_cancel or not callable(cancel):
            raise ToolError(
                "cancel_not_supported",
                f"Cancellation is not supported: {current.tool_id}",
                status_code=422,
            )
        cancel(request)
        cancelled = ToolExecutionResult(
            **{
                **current.__dict__,
                "status": "cancelled",
                "success": False,
                "error": "execution_cancelled",
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._results[call_id] = cancelled
        self._record_verification(call_id, current.tool_id, False, {})
        self._log_execution(request, cancelled, None)
        self.event_bus.emit(
            "tool_execution_cancelled", "tools", {"call_id": call_id, "tool_id": current.tool_id}
        )
        return cancelled

    def _remember_result(self, request: ToolExecutionRequest, result: ToolExecutionResult) -> None:
        if result.call_id:
            self._results[result.call_id] = result
            self._requests[result.call_id] = request
            if request.idempotency_key:
                self._idempotency[request.idempotency_key] = result.call_id

    def retry(self, call_id: str) -> ToolExecutionResult:
        current = self.get_result(call_id)
        request = self._requests[call_id]
        definition = self.get_tool(current.tool_id)
        if current.status != "failed" or not definition.metadata.get("idempotent"):
            raise ToolError(
                "retry_not_allowed", f"Retry is not allowed: {call_id}", status_code=409
            )
        retry_request = ToolExecutionRequest(
            **{
                **request.__dict__,
                "id": str(uuid4()),
                "idempotency_key": None,
                "metadata": {**request.metadata, "retry_of": call_id},
            }
        )
        self.event_bus.emit(
            "tool_retry_scheduled", request.caller, {"call_id": call_id, "tool_id": current.tool_id}
        )
        return self.execute_tool_call(retry_request)

    def rollback(self, call_id: str) -> ToolExecutionResult:
        current = self.get_result(call_id)
        registered = self.registry.get_tool(current.tool_id)
        rollback = getattr(registered.handler, "rollback", None)
        if not registered.definition.supports_rollback or not callable(rollback):
            raise ToolError(
                "rollback_not_supported",
                f"Rollback is not supported: {current.tool_id}",
                status_code=422,
            )
        self.event_bus.emit(
            "tool_rollback_started", "tools", {"call_id": call_id, "tool_id": current.tool_id}
        )
        try:
            output = rollback(self._requests[call_id])
        except Exception as exc:
            self.event_bus.emit(
                "tool_rollback_failed",
                "tools",
                {"call_id": call_id, "tool_id": current.tool_id, "error_type": type(exc).__name__},
            )
            raise ToolError("rollback_failed", f"Rollback failed: {current.tool_id}") from exc
        result = ToolExecutionResult(
            **{
                **current.__dict__,
                "status": "rolled_back",
                "rollback_status": "completed",
                "output": output,
                "completed_at": datetime.now(UTC).isoformat(),
            }
        )
        self._results[call_id] = result
        self.event_bus.emit(
            "tool_rollback_completed", "tools", {"call_id": call_id, "tool_id": current.tool_id}
        )
        return result

    @staticmethod
    def _validate_arguments(
        definition: ToolDefinition, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        schema = definition.input_schema or {"type": "object", "properties": {}}
        properties = schema.get("properties", {})
        missing = [name for name in schema.get("required", []) if name not in arguments]
        if missing:
            raise ToolError(
                "invalid_tool_arguments", f"Missing required arguments: {', '.join(missing)}"
            )
        if schema.get("additionalProperties") is False:
            extra = sorted(set(arguments) - set(properties))
            if extra:
                raise ToolError("invalid_tool_arguments", f"Unknown arguments: {', '.join(extra)}")
        expected_types: dict[str, type[object] | tuple[type[object], ...]] = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "object": dict,
            "array": list,
        }
        for name, value in arguments.items():
            rule = properties.get(name, {})
            expected = expected_types.get(rule.get("type"))
            if expected and (
                not isinstance(value, expected)
                or rule.get("type") == "integer"
                and isinstance(value, bool)
            ):
                raise ToolError("invalid_tool_arguments", f"Invalid type for argument: {name}")
            if "enum" in rule and value not in rule["enum"]:
                raise ToolError("invalid_tool_arguments", f"Invalid value for argument: {name}")
            if (
                isinstance(value, str)
                and (".." in value or value.startswith(("/", "\\")))
                and rule.get("format") == "path"
            ):
                raise ToolError("path_not_allowed", f"Path is outside the allowed root: {name}")
        return dict(arguments)

    def _log_execution(
        self,
        request: ToolExecutionRequest,
        result: ToolExecutionResult,
        decision: ToolExecutionDecision | None,
    ) -> None:
        record = redact(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "tool": request.tool_id,
                "caller": request.caller,
                "caller_type": request.caller_type,
                "agent_id": request.agent_id,
                "success": result.success,
                "duration": result.duration_ms,
                "error": result.error,
                "conversation_id": request.conversation_id,
                "mission_id": request.mission_id,
                "decision": asdict(decision) if decision else None,
                "approval_id": decision.approval_id if decision else None,
                "call_id": result.call_id,
                "idempotency_key": request.idempotency_key,
                "request": asdict(request),
                "result": asdict(result),
                "verification": self._verifications.get(result.call_id or ""),
            }
        )
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    @staticmethod
    def _invoke_handler(
        handler: ToolHandler,
        request: ToolExecutionRequest,
        timeout_seconds: float,
    ) -> dict[str, Any]:
        result: Queue[tuple[bool, object]] = Queue(maxsize=1)
        context = copy_context()

        def invoke() -> None:
            try:
                result.put((True, context.run(handler, request)))
            except BaseException as exc:
                result.put((False, exc))

        thread = Thread(
            target=invoke,
            name=f"tool-execution-{request.tool_id}",
            daemon=True,
        )
        thread.start()
        thread.join(max(0.001, timeout_seconds))
        if thread.is_alive():
            raise TimeoutError(f"Tool execution timed out: {request.tool_id}")
        succeeded, value = result.get_nowait()
        if succeeded:
            if not isinstance(value, dict):
                raise ToolError("invalid_tool_result", "Tool result must be an object")
            return value
        raise value  # type: ignore[misc]

    def _record_verification(
        self,
        call_id: str,
        tool_id: str,
        verified: bool,
        output: dict[str, Any],
    ) -> None:
        verification = {
            "verified": verified,
            "tool_id": tool_id,
            "evidence": {"output_type": "object", "keys": sorted(output)},
        }
        self._verifications[call_id] = verification
        self.event_bus.emit(
            "tool_runtime.verification_completed",
            "tools",
            {"call_id": call_id, "tool_id": tool_id, "verified": verified},
        )

    def verification(self, call_id: str) -> dict[str, Any]:
        self.get_result(call_id)
        return dict(self._verifications.get(call_id, {}))

    def _load_history(self) -> None:
        if not self.log_path.exists():
            return
        for line in self.log_path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
                request_raw = record.get("request")
                result_raw = record.get("result")
                if not isinstance(request_raw, dict) or not isinstance(result_raw, dict):
                    continue
                if isinstance(request_raw.get("resource_ref"), dict):
                    request_raw["resource_ref"] = ResourceRef(**request_raw["resource_ref"])
                request = ToolExecutionRequest(**request_raw)
                result = ToolExecutionResult(**result_raw)
                if not result.call_id:
                    continue
                self._requests[result.call_id] = request
                self._results[result.call_id] = result
                if request.idempotency_key:
                    self._idempotency[request.idempotency_key] = result.call_id
                if isinstance(record.get("verification"), dict):
                    self._verifications[result.call_id] = record["verification"]
            except (TypeError, ValueError, json.JSONDecodeError):
                continue


def register_seed_runtime_tools(
    runtime: ToolRuntime,
    *,
    health: HealthSnapshotSource,
    readiness: ReadinessSnapshotSource,
    conversations: ConversationRuntime,
    missions: MissionRuntime,
    admin: AgentAdminRuntime,
    providers: ProviderRuntime,
    voice: VoiceRuntime,
) -> None:
    runtime.register(
        ToolDefinition(
            tool_id="health.summary",
            display_name="Health Summary",
            description="Return the current Homelab Health summary.",
            category="system",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: asdict(health.summary()),
    )
    runtime.register(
        ToolDefinition(
            tool_id="readiness.summary",
            display_name="Readiness Summary",
            description="Return the current operational readiness summary.",
            category="system",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: asdict(readiness.evaluate()),
    )
    runtime.register(
        ToolDefinition(
            tool_id="conversation.summary",
            display_name="Conversation Summary",
            description="Return a conversation summary by conversation_id.",
            category="conversation",
            input_schema={"type": "object", "required": ["conversation_id"]},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: _conversation_summary(conversations, request),
    )
    runtime.register(
        ToolDefinition(
            tool_id="mission.summary",
            display_name="Mission Summary",
            description="Return a mission summary by mission_id.",
            category="mission",
            input_schema={"type": "object", "required": ["mission_id"]},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: asdict(missions.summarize_mission(_required_arg(request, "mission_id"))),
    )
    runtime.register(
        ToolDefinition(
            tool_id="agent.summary",
            display_name="Agent Summary",
            description="Return administrative status for an agent.",
            category="agent",
            input_schema={"type": "object", "required": ["agent_id"]},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: asdict(admin.get_agent_admin_status(_required_arg(request, "agent_id"))),
    )
    runtime.register(
        ToolDefinition(
            tool_id="provider.summary",
            display_name="Provider Summary",
            description="Return provider runtime summary.",
            category="provider",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: _provider_summary(providers),
    )
    runtime.register(
        ToolDefinition(
            tool_id="audio.transcribe",
            display_name="Audio Transcribe",
            description="Transcribe an uploaded audio payload with the configured STT provider.",
            category="voice",
            input_schema={
                "type": "object",
                "required": ["audio_base64"],
                "properties": {
                    "audio_base64": {"type": "string"},
                    "audio_format": {"type": "string"},
                    "language": {"type": "string"},
                    "model": {"type": "string"},
                    "provider_id": {"type": "string"},
                    "duration_ms": {"type": "integer"},
                    "metadata": {"type": "object"},
                },
            },
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="medium",
            metadata={"read_only": True},
        ),
        lambda request: _audio_transcribe(voice, request),
    )
    runtime.register(
        ToolDefinition(
            tool_id="voice.transcribe",
            display_name="Voice Transcript",
            description="Return the transcript for a recorded voice capture.",
            category="voice",
            input_schema={"type": "object", "required": ["recording_id"]},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
            metadata={"read_only": True},
        ),
        lambda request: asdict(voice.get_recording(_required_arg(request, "recording_id"))),
    )
    runtime.register(
        ToolDefinition(
            tool_id="tool.summary",
            display_name="Tool Runtime Summary",
            description="Return tool runtime summary.",
            category="tool",
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object"},
            required_permission="tools.execute",
            risk_level="low",
        ),
        lambda request: runtime.summary(),
    )
    system_config = load_structured_file(runtime.data_dir.resolve("config/system.yaml"))
    if str(system_config.get("system", {}).get("mode", "")).lower() == "test":
        runtime.register(
            ToolDefinition(
                tool_id="danger.mock",
                display_name="Danger Mock",
                description="Explicit test-mode approval fixture.",
                category="test",
                input_schema={"type": "object", "properties": {}},
                output_schema={"type": "object"},
                required_permission="tools.execute",
                risk_level="critical",
                approval_required=True,
                metadata={"mock": True, "test_mode_only": True},
            ),
            lambda request: {"executed": True, "mock": True},
        )


def _conversation_summary(
    runtime: ConversationRuntime, request: ToolExecutionRequest
) -> dict[str, Any]:
    conversation_id = _required_arg(request, "conversation_id")
    try:
        return asdict(runtime.get_conversation_summary(conversation_id))
    except NotFound:
        conversation = runtime.get_conversation(conversation_id)
        messages = runtime.list_conversation_messages(conversation_id)
        return {
            "conversation_id": conversation.conversation_id,
            "summary": conversation.title or conversation.conversation_id,
            "message_count": len(messages),
            "last_message_id": messages[-1].message_id if messages else None,
            "metadata": {"generated": "fallback"},
        }


def _provider_summary(runtime: ProviderRuntime) -> dict[str, Any]:
    providers = runtime.list_providers()
    health = runtime.list_provider_health()
    return {
        "provider_count": len(providers),
        "providers": [asdict(provider) for provider in providers],
        "health": [asdict(item) for item in health],
    }


def _audio_transcribe(voice: VoiceRuntime, request: ToolExecutionRequest) -> dict[str, Any]:
    if voice.audio is None:
        raise ValidationError("Audio runtime is unavailable.")
    audio_payload = request.arguments.get("audio_base64")
    if not audio_payload:
        raise ValidationError("audio_base64 is required.")
    result = voice.audio.transcribe(
        AudioInputRequest(
            session_id=request.arguments.get("session_id"),
            multimodal_session_id=request.arguments.get("multimodal_session_id"),
            provider_id=request.arguments.get("provider_id"),
            language=request.arguments.get("language"),
            model=voice.resolve_model_name(request.arguments.get("model")),
            audio_base64=str(audio_payload),
            audio_format=request.arguments.get("audio_format"),
            duration_ms=request.arguments.get("duration_ms"),
            metadata=dict(request.arguments.get("metadata") or {}),
        )
    )
    return asdict(result)


def _required_arg(request: ToolExecutionRequest, name: str) -> str:
    value = request.arguments.get(name)
    if value is None or str(value).strip() == "":
        raise ValidationError(f"{request.tool_id} requires argument: {name}")
    return str(value)
