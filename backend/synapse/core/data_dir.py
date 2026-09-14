from __future__ import annotations

from pathlib import Path

from synapse.core.exceptions import ValidationError
from synapse.core.serialization import dump_structured_file, load_structured_file

REQUIRED_DIRECTORIES = (
    "config",
    "memory",
    "agents",
    "projects",
    "skills",
    "tasks/active",
    "tasks/completed",
    "tasks/failed",
    "tools",
    "approvals",
    "jobs",
    "scheduler/recurring",
    "daemon",
    "presence",
    "lifecycle",
    "conversations",
    "dead_letter",
    "delegation",
    "delegation_execution",
    "delegation_inbox",
    "notifications",
    "locks",
    "logs",
    "migrations",
    "missions",
    "multimodal/sessions",
    "agent_provisioning",
    "agent_admin_requests",
    "audio/sessions",
    "audio/devices",
    "vision/sessions",
    "vision/inputs",
    "vision/results",
    "vision/raw",
    "perception/signals",
    "perception/observations",
    "perception/conflicts",
    "perception/batches",
    "multimodal/fusions",
    "context_fusion/snapshots",
    "world_state",
    "attention/items",
    "agent_loop/decisions",
    "agent_loop/executions",
    "insight/snapshots",
    "insight/diagnostics",
    "insight/cache",
    "desktop_automation/plans",
    "desktop_automation/results",
    "desktop_automation/history",
    "providers",
    "provider_plugins/manifests",
    "provider_plugins/states",
    "model_providers",
    "model_hub",
    "voice/sessions",
    "voice/utterances",
    "voice/recordings",
    "speech_pipeline/sessions",
    "speech_pipeline/input_turns",
    "speech_pipeline/output_turns",
    "library",
    "chats",
    "devices/trusted",
    "devices/untrusted",
    "devices/revoked",
)


SEED_FILES = {
    "memory/USER.md": "# User Memory\n\nPersistent facts about the user belong here.\n",
    "memory/MEMORY.md": "# Global Memory\n\nPersistent system-wide memory belongs here.\n",
    "memory/SYSTEM.md": "# System Memory\n\nDurable operating notes for Synapse belong here.\n",
    "agents/orchestrator/CONFIG.yaml": (
        "{\n"
        '  "id": "orchestrator",\n'
        '  "name": "Orchestrator",\n'
        '  "role": "Coordinates Synapse runtime activity.",\n'
        '  "preferred_model": "lmstudio/gemma-4-e2b-it-qat",\n'
        '  "autonomy": "manual",\n'
        '  "skills": ["coordinate_tasks", "route_messages", "use_core_tools"],\n'
        '  "permissions": [\n'
        '    "filesystem.read",\n'
        '    "filesystem.write",\n'
        '    "filesystem.list",\n'
        '    "filesystem.search",\n'
        '    "web.search",\n'
        '    "agents.message",\n'
        '    "tasks.create",\n'
        '    "tasks.update"\n'
        "  ]\n"
        "}\n"
    ),
    "agents/orchestrator/SOUL.md": (
        "# Orchestrator\n\n"
        "The orchestrator coordinates agents, tasks, memory, and tools while respecting permissions.\n"
    ),
    "agents/orchestrator/MEMORY.md": (
        "# Orchestrator Memory\n\nPersistent memory for the orchestrator agent.\n"
    ),
    "agents/orchestrator/SKILLS.md": (
        "# Orchestrator Skills\n\n- coordinate_tasks\n- route_messages\n- use_core_tools\n"
    ),
    "agents/orchestrator/INBOX.md": "# Inbox\n",
    "config/approval_policy.yaml": (
        "{\n"
        '  "approval": {\n'
        '    "required_risk_levels": ["high", "critical"],\n'
        '    "bypass_agents": [],\n'
        '    "approver_device_permissions": ["approve_actions"],\n'
        '    "explicit_permission_bypasses_approval": false,\n'
        '    "default_expires_minutes": null\n'
        "  }\n"
        "}\n"
    ),
    "config/permissions.yaml": (
        '{\n  "subjects": {\n    "local_owner": ["*"],\n    "user:local_owner": ["*"]\n  }\n}\n'
    ),
    "config/system.yaml": (
        "{\n"
        '  "system": {\n'
        '    "name": "Synapse V2",\n'
        '    "mode": "local",\n'
        '    "default_agent_id": null\n'
        "  },\n"
        '  "models": {\n'
        '    "default_provider": "lmstudio",\n'
        '    "providers": {\n'
        '      "lmstudio": {\n'
        '        "base_url": "http://127.0.0.1:1234/v1",\n'
        '        "model": "gemma-4-e2b-it-qat"\n'
        "      },\n"
        '      "ollama": {\n'
        '        "base_url": "http://127.0.0.1:11434",\n'
        '        "model": null\n'
        "      },\n"
        '      "openai_compatible": {\n'
        '        "base_url": null,\n'
        '        "model": null\n'
        "      }\n"
        "    }\n"
        "  }\n"
        "}\n"
    ),
    "config/notification_policy.yaml": (
        "{\n"
        '  "notifications": {\n'
        '    "retention_days": 30,\n'
        '    "max_total_notifications": 500,\n'
        '    "preserve_unread": true,\n'
        '    "preserve_critical": true\n'
        "  }\n"
        "}\n"
    ),
    "config/perception_policy.yaml": (
        "{\n"
        '  "perception": {\n'
        '    "enabled": true,\n'
        '    "allowed_sources": ["voice", "audio", "vision", "screen", "camera", "system", "interaction", "test"],\n'
        '    "max_signal_bytes": 262144,\n'
        '    "signal_retention_hours": 24,\n'
        '    "observation_retention_days": 30,\n'
        '    "raw_visual_retention_minutes": 15,\n'
        '    "persist_transcripts": false,\n'
        '    "screenshots_enabled": true,\n'
        '    "camera_enabled": false,\n'
        '    "ocr_enabled": false,\n'
        '    "persist_raw_visual": false,\n'
        '    "require_approval_for_sensitive_capture": true,\n'
        '    "sensitive_applications": [],\n'
        '    "sensitive_window_patterns": ["private", "incognito", "password"],\n'
        '    "sensitive_regions": [],\n'
        '    "default_fusion_window_seconds": 15\n'
        "  }\n"
        "}\n"
    ),
    "config/scheduler_policy.yaml": (
        '{\n  "scheduler_lock": {\n    "timeout_seconds": 300\n  },\n  "recurring_jobs": []\n}\n'
    ),
    "config/insight_policy.yaml": (
        "{\n"
        '  "resource_pressure": {\n'
        '    "moderate": 0.70,\n'
        '    "high": 0.85,\n'
        '    "critical": 0.95\n'
        "  },\n"
        '  "persistence": {\n'
        '    "max_snapshots": 48\n'
        "  }\n"
        "}\n"
    ),
    "config/agent_provisioning_policy.yaml": (
        "{\n"
        '  "agent_provisioning": {\n'
        '    "default_autonomy_level": "manual",\n'
        '    "max_direct_create_autonomy_level": "manual",\n'
        '    "require_approval_for_high_risk_capabilities": true,\n'
        '    "require_approval_for_critical_capabilities": true,\n'
        '    "sensitive_capabilities": [\n'
        '      "filesystem.write",\n'
        '      "scheduler.run",\n'
        '      "approval.review"\n'
        "    ],\n"
        '    "sensitive_tools": ["write_file", "delete_file", "camera_control"],\n'
        '    "blocked_capabilities": [],\n'
        '    "blocked_tools": [],\n'
        '    "require_forbidden_tools_for_sensitive_agents": true,\n'
        '    "allow_direct_create": true,\n'
        '    "allow_direct_update": true\n'
        "  }\n"
        "}\n"
    ),
    "config/admin_policy.yaml": (
        "{\n"
        '  "admin_policy": {\n'
        '    "allow_user_admin_actions": true,\n'
        '    "require_approval_for_archive": false,\n'
        '    "require_approval_for_deactivate": false,\n'
        '    "require_approval_for_restore": false,\n'
        '    "protected_agents": [],\n'
        '    "blocked_admin_actions": [],\n'
        '    "admin_capabilities_required": {}\n'
        "  }\n"
        "}\n"
    ),
    "config/agent_admin_retention_policy.yaml": (
        "{\n"
        '  "agent_admin_retention": {\n'
        '    "enabled": true,\n'
        '    "delete_applied_after_days": 30,\n'
        '    "delete_rejected_after_days": 30,\n'
        '    "delete_failed_after_days": 60,\n'
        '    "delete_cancelled_after_days": 30,\n'
        '    "preserve_awaiting_approval": true,\n'
        '    "preserve_approved_not_applied": true,\n'
        '    "max_requests": 500,\n'
        '    "dry_run_default": true\n'
        "  }\n"
        "}\n"
    ),
    "config/readiness_policy.yaml": (
        "{\n"
        '  "readiness": {\n'
        '    "require_daemon": false,\n'
        '    "require_scheduler": true,\n'
        '    "require_capabilities": true,\n'
        '    "pending_approvals_state": "action_required",\n'
        '    "failed_jobs_state": "degraded",\n'
        '    "critical_notifications_state": "action_required",\n'
        '    "stale_lock_state": "action_required",\n'
        '    "require_world_state": true,\n'
        '    "require_policy": true,\n'
        '    "require_observability": true\n'
        "  }\n"
        "}\n"
    ),
    "config/proactive_behavior.yaml": (
        "{\n"
        '  "proactive_behavior": {\n'
        '    "mode": "observe",\n'
        '    "max_proactive_actions_per_hour": 2,\n'
        '    "cooldown_seconds": 300,\n'
        '    "allowed_dispositions": ["record_only", "notify"],\n'
        '    "quiet_hours": {},\n'
        '    "notification_budget_per_hour": 4,\n'
        '    "mission_concurrency": 1,\n'
        '    "tool_risk_ceiling": "low"\n'
        "  }\n"
        "}\n"
    ),
    "config/provider_policy.yaml": (
        "{\n"
        '  "providers": {\n'
        '    "allow_network_providers": false,\n'
        '    "allow_gpu_providers": false,\n'
        '    "prefer_local_providers": true,\n'
        '    "disabled_providers": [],\n'
        '    "provider_priority_overrides": {}\n'
        "  }\n"
        "}\n"
    ),
    "config/provider_plugin_policy.yaml": (
        "{\n"
        '  "provider_plugin_policy": {\n'
        '    "enabled": true,\n'
        '    "allow_network_plugins": false,\n'
        '    "allow_gpu_plugins": false,\n'
        '    "disabled_plugins": [],\n'
        '    "prefer_local_plugins": true,\n'
        '    "allow_experimental_plugins": false\n'
        "  }\n"
        "}\n"
    ),
    "config/lmstudio_provider.yaml": (
        "{\n"
        '  "lmstudio": {\n'
        '    "enabled": true,\n'
        '    "base_url": "http://127.0.0.1:1234/v1",\n'
        '    "timeout_seconds": 30,\n'
        '    "default_model": "gemma-4-e2b-it-qat",\n'
        '    "metadata": {}\n'
        "  }\n"
        "}\n"
    ),
    "config/provider_settings.yaml": (
        "{\n"
        '  "schema_version": 1,\n'
        '  "providers": {\n'
        '    "lmstudio_local": {\n'
        '      "enabled": true,\n'
        '      "endpoint": "http://127.0.0.1:1234/v1",\n'
        '      "default_model": "gemma-4-e2b-it-qat",\n'
        '      "status": "configured",\n'
        '      "updated_at": null,\n'
        '      "last_tested_at": null,\n'
        '      "test_message": null\n'
        "    },\n"
        '    "synapse_local": {\n'
        '      "enabled": false,\n'
        '      "endpoint": "F:/SynapseRuntime/models",\n'
        '      "default_model": null,\n'
        '      "status": "unconfigured",\n'
        '      "updated_at": null,\n'
        '      "last_tested_at": null,\n'
        '      "test_message": null\n'
        "    },\n"
        '    "ollama_local": {\n'
        '      "enabled": false,\n'
        '      "endpoint": "http://127.0.0.1:11434",\n'
        '      "default_model": null,\n'
        '      "status": "unconfigured",\n'
        '      "updated_at": null,\n'
        '      "last_tested_at": null,\n'
        '      "test_message": null\n'
        "    }\n"
        "  }\n"
        "}\n"
    ),
    "model_hub/defaults.yaml": (
        "{\n"
        '  "default_chat_model": "gemma-4-e2b-it-qat",\n'
        '  "default_provider": "lmstudio",\n'
        '  "preferred_runtime": "lmstudio",\n'
        '  "updated_at": null\n'
        "}\n"
    ),
    "voice/settings.yaml": (
        "{\n"
        '  "schema_version": 3,\n'
        '  "provider_id": "faster_whisper",\n'
        '  "stt_provider_id": "faster_whisper",\n'
        '  "stt_model": "tiny",\n'
        '  "stt_device": "cpu",\n'
        '  "stt_compute_type": "int8",\n'
        '  "device_id": null,\n'
        '  "language": "pt-BR",\n'
        '  "model": "tiny",\n'
        '  "tts_provider_id": "piper",\n'
        '  "tts_model": null,\n'
        '  "default_tts_voice": null,\n'
        '  "preferred_voice_gender": "female",\n'
        '  "tts_speed": null,\n'
        '  "provider_configuration_references": {},\n'
        '  "policy_version": "voice-configuration-v1",\n'
        '  "enabled": true,\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "config/local_chat_policy.yaml": (
        "{\n"
        '  "local_chat": {\n'
        '    "enabled": true,\n'
        '    "provider_id": "lmstudio_local",\n'
        '    "require_explicit_provider": true,\n'
        '    "persist_conversations": true,\n'
        '    "max_context_messages": 10,\n'
        '    "include_conversation_summary": true,\n'
        '    "include_multimodal_context": false\n'
        "  }\n"
        "}\n"
    ),
    "provider_plugins/manifests/faster_whisper_plugin.yaml": (
        "{\n"
        '  "plugin_id": "faster_whisper_plugin",\n'
        '  "name": "Faster-Whisper Plugin",\n'
        '  "description": "High-performance local speech-to-text using Faster-Whisper.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "speech",\n'
        '  "providers": ["faster_whisper"],\n'
        '  "capabilities": ["speech.transcribe"],\n'
        '  "adapters": ["faster_whisper_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": false,\n'
        '  "supported_platforms": ["windows", "linux", "darwin"],\n'
        '  "requirements": ["faster-whisper>=1.0.0"],\n'
        '  "entrypoint": "faster_whisper_plugin.entrypoint",\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "provider_plugins/manifests/piper_plugin.yaml": (
        "{\n"
        '  "plugin_id": "piper_plugin",\n'
        '  "name": "Piper TTS Plugin",\n'
        '  "description": "Fast local text-to-speech using Piper.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "speech",\n'
        '  "providers": ["piper"],\n'
        '  "capabilities": ["speech.synthesize"],\n'
        '  "adapters": ["piper_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": false,\n'
        '  "supported_platforms": ["windows", "linux", "darwin"],\n'
        '  "requirements": ["piper-tts>=1.2.0"],\n'
        '  "entrypoint": "piper_plugin.entrypoint",\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "provider_plugins/manifests/kokoro_plugin.yaml": (
        "{\n"
        '  "plugin_id": "kokoro_plugin",\n'
        '  "name": "Kokoro TTS Plugin",\n'
        '  "description": "High-quality text-to-speech using Kokoro model.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "speech",\n'
        '  "providers": ["kokoro"],\n'
        '  "capabilities": ["speech.synthesize"],\n'
        '  "adapters": ["kokoro_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": true,\n'
        '  "supported_platforms": ["windows", "linux"],\n'
        '  "requirements": ["kokoro-onnx>=0.1.0"],\n'
        '  "entrypoint": "kokoro_plugin.entrypoint",\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "provider_plugins/manifests/mediapipe_plugin.yaml": (
        "{\n"
        '  "plugin_id": "mediapipe_plugin",\n'
        '  "name": "MediaPipe Plugin",\n'
        '  "description": "Face, hand, and pose tracking using Google MediaPipe.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "vision",\n'
        '  "providers": ["mediapipe"],\n'
        '  "capabilities": ["vision.pose_tracking", "vision.face_mesh"],\n'
        '  "adapters": ["mediapipe_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": false,\n'
        '  "supported_platforms": ["windows", "linux", "darwin"],\n'
        '  "requirements": ["mediapipe>=0.10.0"],\n'
        '  "entrypoint": "mediapipe_plugin.entrypoint",\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "provider_plugins/manifests/opencv_plugin.yaml": (
        "{\n"
        '  "plugin_id": "opencv_plugin",\n'
        '  "name": "OpenCV Vision Plugin",\n'
        '  "description": "Image processing and camera utility functions using OpenCV.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "vision",\n'
        '  "providers": ["opencv"],\n'
        '  "capabilities": ["vision.capture", "vision.process"],\n'
        '  "adapters": ["opencv_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": false,\n'
        '  "supported_platforms": ["windows", "linux", "darwin"],\n'
        '  "requirements": ["opencv-python>=4.9.0"],\n'
        '  "entrypoint": "opencv_plugin.entrypoint",\n'
        '  "metadata": {}\n'
        "}\n"
    ),
    "provider_plugins/manifests/lmstudio_plugin.yaml": (
        "{\n"
        '  "plugin_id": "lmstudio_plugin",\n'
        '  "name": "LM Studio Provider Plugin",\n'
        '  "description": "Local OpenAI-compatible chat completions through LM Studio.",\n'
        '  "version": "1.0.0",\n'
        '  "plugin_type": "model",\n'
        '  "providers": ["lmstudio_local"],\n'
        '  "capabilities": ["local_llm", "chat_completion"],\n'
        '  "adapters": ["lmstudio_openai_compatible_adapter"],\n'
        '  "enabled": false,\n'
        '  "installed": false,\n'
        '  "local_only": true,\n'
        '  "requires_network": false,\n'
        '  "requires_gpu": false,\n'
        '  "supported_platforms": ["windows", "linux", "darwin"],\n'
        '  "requirements": [],\n'
        '  "entrypoint": null,\n'
        '  "metadata": {"external_process_required": true}\n'
        "}\n"
    ),
    "config/delegation_scheduling_policy.yaml": (
        "{\n"
        '  "delegation_scheduling": {\n'
        '    "enabled": true,\n'
        '    "status_order": ["in_progress", "accepted", "pending"],\n'
        '    "priority_weights": {\n'
        '      "critical": 400,\n'
        '      "high": 300,\n'
        '      "normal": 200,\n'
        '      "low": 100\n'
        "    },\n"
        '    "due_at_weight": 50,\n'
        '    "aging_weight": 1,\n'
        '    "max_items_per_agent_cycle": 1,\n'
        '    "allow_critical_first": true,\n'
        '    "preserve_fifo_within_same_score": true\n'
        "  }\n"
        "}\n"
    ),
    "config/delegation_autonomy_policy.yaml": (
        "{\n"
        '  "delegation_autonomy": {\n'
        '    "enabled": true,\n'
        '    "allow_auto_accept": false,\n'
        '    "allow_auto_start": true,\n'
        '    "allow_auto_reject": false,\n'
        '    "max_auto_priority": "high",\n'
        '    "require_approval_for_critical": true,\n'
        '    "allowed_requester_agents": [],\n'
        '    "blocked_requester_agents": [],\n'
        '    "require_capability_match": false,\n'
        '    "require_due_at_for_auto_accept": false,\n'
        '    "manual_autonomy_blocks_auto_accept": true,\n'
        '    "conservative_default": true\n'
        "  }\n"
        "}\n"
    ),
    "config/delegation_retry_policy.yaml": (
        "{\n"
        '  "delegation_retry": {\n'
        '    "enabled": true,\n'
        '    "max_attempts_default": 3,\n'
        '    "max_attempts_by_priority": {\n'
        '      "critical": 2,\n'
        '      "high": 3,\n'
        '      "normal": 3,\n'
        '      "low": 2\n'
        "    },\n"
        '    "allow_retry_failed_tasks": true,\n'
        '    "allow_retry_completed_tasks": false,\n'
        '    "require_approval_for_critical_retry": true,\n'
        '    "require_approval_after_attempts": 2,\n'
        '    "reset_task_status_on_retry": true,\n'
        '    "default_retry_status": "accepted"\n'
        "  }\n"
        "}\n"
    ),
    "config/delegation_timeout_policy.yaml": (
        "{\n"
        '  "delegation_timeout": {\n'
        '    "enabled": true,\n'
        '    "default_timeout_minutes": 60,\n'
        '    "timeout_by_priority": {\n'
        '      "critical": 30,\n'
        '      "high": 45,\n'
        '      "normal": 60,\n'
        '      "low": 120\n'
        "    },\n"
        '    "timeout_by_status": {\n'
        '      "in_progress": 60\n'
        "    },\n"
        '    "mark_execution_failed_on_timeout": true,\n'
        '    "mark_task_failed_on_timeout": false,\n'
        '    "require_human_review_for_critical": true,\n'
        '    "dry_run_default": true,\n'
        '    "max_timeouts_per_run": 50\n'
        "  }\n"
        "}\n"
    ),
    "config/multimodal_context_policy.yaml": (
        "{\n"
        '  "multimodal_context": {\n'
        '    "enabled": true,\n'
        '    "include_for_conversations": true,\n'
        '    "include_for_missions": true,\n'
        '    "include_for_sessions": true,\n'
        '    "max_signals_per_context": 50,\n'
        '    "attach_health_summary": true,\n'
        '    "attach_readiness_summary": true\n'
        "  }\n"
        "}\n"
    ),
    "config/speech_pipeline_policy.yaml": (
        "{\n"
        '  "speech_pipeline": {\n'
        '    "enabled": true,\n'
        '    "complete_mock_utterance_immediately": true,\n'
        '    "emit_perception_signals": true,\n'
        '    "emit_multimodal_events": true\n'
        "  }\n"
        "}\n"
    ),
    "config/speech_adapter_policy.yaml": (
        "{\n"
        '  "speech_adapters": {\n'
        '    "enabled": true,\n'
        '    "prefer_local_adapters": true,\n'
        '    "allow_network_adapters": false,\n'
        '    "allow_gpu_adapters": false,\n'
        '    "disabled_adapters": [],\n'
        '    "adapter_priority_overrides": {}\n'
        "  }\n"
        "}\n"
    ),
    "config/voice_settings.yaml": (
        "{\n"
        '  "provider_id": null,\n'
        '  "device_id": null,\n'
        '  "language": "pt-BR",\n'
        '  "model": "auto",\n'
        '  "enabled": true,\n'
        '  "metadata": {}\n'
        "}\n"
    ),
}


class DataDir:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in REQUIRED_DIRECTORIES:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        for relative_path, content in SEED_FILES.items():
            self.ensure_file(relative_path, content)
        self._normalize_voice_settings()

    def ensure_file(self, relative_path: str, content: str) -> Path:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        return path

    def resolve(self, relative_path: str | Path) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute():
            path = candidate.resolve()
        else:
            path = (self.root / candidate).resolve()

        if not path.is_relative_to(self.root):
            raise ValidationError(f"Path escapes DATA_DIR: {relative_path}")
        return path

    def append_text(self, relative_path: str, text: str) -> Path:
        path = self.resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def _normalize_voice_settings(self) -> None:
        path = self.resolve("voice/settings.yaml")
        if not path.exists():
            return
        settings = load_structured_file(path)
        provider_id = str(
            settings.get("stt_provider_id") or settings.get("provider_id") or ""
        ).strip()
        if provider_id != "piper":
            return
        settings["stt_provider_id"] = "faster_whisper"
        settings["provider_id"] = "faster_whisper"
        dump_structured_file(path, settings)
