from __future__ import annotations

from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.exceptions import NotFound
from synapse.core.permissions import PermissionContext


class PerceptionVisionCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/vision-sessions",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f1fa525c52b6e98a3ea61f87e7d6f72a446a9fbaa2e56becb2665dc366032691",
        ),
        CommandMetadata(
            name="/vision-session",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e8eff7010d9b8ab1661a5c6486f2b1e23c4e1eeca79c6a91d6744952765bb432",
        ),
        CommandMetadata(
            name="/vision-cameras",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a41d1639b98ff7c06ffa2aa175a139794d4aa6e10fd50975a40a74504baa72f2",
        ),
        CommandMetadata(
            name="/vision-health",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="cc9001525d5c8fbe559fb8f5f64c3da56886d6bf7e7c605ddeb8adfb3ca0624a",
        ),
        CommandMetadata(
            name="/vision-sources",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="ee1b5cef4956fbd2fcedde54a465c4395a8dbcab6fc430ab166d2aaf84c5aa02",
        ),
        CommandMetadata(
            name="/vision-providers",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="4c0cea1995b3d3dd161f32da79a99affb2af79299fc7ab7b6f7ccd385986e067",
        ),
        CommandMetadata(
            name="/vision-analyze",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b3650e778c98d4e28ff30d8e8895dc222be23afb09e96cbc28d88904880d1803",
        ),
        CommandMetadata(
            name="/vision-capture-screen",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="558ab73128d33c1eea2d980d72dba53d8fa8102b03e408982191243c7f58011e",
        ),
        CommandMetadata(
            name="/vision-capture-sources",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2c23823bc5615d56ff2e62ad5708d4d5b8c8cd652b950c8d6893fc8e1fcdcd32",
        ),
        CommandMetadata(
            name="/camera-list",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="c395a937ca7a856cbd5780a66376000da9169c45aa7d94d895db6114a7a5ab35",
        ),
        CommandMetadata(
            name="/camera-test",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="b98eee25b7f090cc2082fab6809708acd828f0d55a635efcf1fac9bada72178e",
        ),
        CommandMetadata(
            name="/perception-signals",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f68e468ff4589f3069514499890dae0a871627d5dbdc4c9a3c71ebb8c7aa20b7",
        ),
        CommandMetadata(
            name="/perception-session",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fe6f6cd020ad8762f42a4f1913c6653fc8dd6e499c632d9024a89c0018fa7527",
        ),
        CommandMetadata(
            name="/perception-type",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="69efc6d1751d889a07588177772e18d18f4c0d2e6644d131774650f8c51a9fec",
        ),
        CommandMetadata(
            name="/perception-summary",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="389db87813a65015b697fffce938c1e81d85c22b369fdbd73f274ea3743cf034",
        ),
        CommandMetadata(
            name="/perception-observations",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fcea65448d40ca228c34b7a68767d7fe9d523662acfef1d9af130caedb250f1d",
        ),
        CommandMetadata(
            name="/perception-conflicts",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7fef82317d0d04529bf9b2f00c3d072c3bb707e62b8ee9225eb2b9e6806880a0",
        ),
        CommandMetadata(
            name="/perception-retention",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="b5dd6f1e2f028fdc400a523c15b9723edcba10507c39ee2775dd0fa49706a0d8",
        ),
        CommandMetadata(
            name="/perception-status",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="d1598fb554f01f8bc444547b40ada02f7b318b3815f85a4221f8912f58d8e3db",
        ),
        CommandMetadata(
            name="/perception-show",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="dbabe8bf6e0464170b654424e4f066e0c4c2ce87d6503730edd2e9c583dbea6c",
        ),
        CommandMetadata(
            name="/perception-cleanup",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("dry_run",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="02b8f102e190db0e3d987a67a7c7b3733e479053433b82247ed6c786d0d98965",
        ),
        CommandMetadata(
            name="/perception-cleanup-dry-run",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("dry_run",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="662e1145e4791e28e545206fd594ff1f9dc0325ef772f2a24fddc1d72c7142c8",
        ),
        CommandMetadata(
            name="/context-fusion",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6236f621b248e9b6a50676decd550f70a6e57b2639246a3c5a08058fb2510dcd",
        ),
        CommandMetadata(
            name="/context-mission",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c981800c3bda96799e582241ac03ecea97dd8b56b5c98d9cff2d7573c73f8247",
        ),
        CommandMetadata(
            name="/context-session",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="89dbdb2d87dc8c56ab1d2a20dd2d68f1e4c9ea65d2e7d98beb82f46ca75458e6",
        ),
        CommandMetadata(
            name="/context-validate",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="56bd82c6876036d0b2108a0d7d9a328d9c7bf84e8aae743935d0c883116c3e0b",
        ),
        CommandMetadata(
            name="/agent-context-preview",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="0ba0e81f7104ea1f611afabb78fe35f4ec4d1672bceeb3769d00463a1ffeaa3d",
        ),
        CommandMetadata(
            name="/agent-multimodal-policy",
            aliases=(),
            domain="perception_vision",
            handler="PerceptionVisionCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="34c54ac2713e6105ce3079cddbea9e447e1ea3e3b3a3f0f472bd0bff18ddce32",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        context = command_context.permission
        if command == "/vision-sessions":
            return self._vision_sessions()
        if command == "/vision-session":
            return self._vision_session(argument_text)
        if command == "/vision-cameras":
            return self._vision_cameras()
        if command == "/vision-health":
            return self._vision_health()
        if command == "/vision-sources":
            return self._vision_sources()
        if command == "/vision-providers":
            return self._vision_health()
        if command == "/vision-analyze":
            return self._vision_analyze(argument_text)
        if command == "/vision-capture-screen":
            return self._vision_capture_screen(argument_text)
        if command == "/vision-capture-sources":
            return self._vision_sources()
        if command == "/camera-list":
            return self._vision_cameras()
        if command == "/camera-test":
            return self._camera_test(argument_text)
        if command == "/perception-signals":
            return self._perception_signals()
        if command == "/perception-session":
            return self._perception_session(argument_text)
        if command == "/perception-type":
            return self._perception_type(argument_text)
        if command == "/perception-summary":
            return self._perception_summary(argument_text)
        if command == "/perception-observations":
            return self._perception_observations(argument_text)
        if command == "/perception-conflicts":
            return self._perception_conflicts()
        if command == "/perception-retention":
            return self._perception_retention(argument_text)
        if command == "/perception-status":
            return self._perception_status()
        if command == "/perception-show":
            return self._perception_show(argument_text)
        if command == "/perception-cleanup":
            return self._perception_cleanup(False)
        if command == "/perception-cleanup-dry-run":
            return self._perception_cleanup(True)
        if command == "/context-fusion":
            return self._context_fusion(argument_text)
        if command == "/context-mission":
            return self._context_mission(argument_text)
        if command == "/context-session":
            return self._context_session(argument_text)
        if command == "/context-validate":
            return self._context_validate(argument_text)
        if command == "/agent-context-preview":
            return self._agent_context_preview(context, argument_text)
        if command == "/agent-multimodal-policy":
            return self._agent_multimodal_policy()
        raise UnknownCommandError(command)

    def _vision_sessions(self) -> CommandResult:
        sessions = [asdict(item) for item in self.vision.list_sessions()]
        return CommandResult(
            command="/vision-sessions",
            status="ok",
            output=f"{len(sessions)} vision session(s).",
            data={"sessions": sessions},
        )

    def _vision_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/vision-session",
                status="error",
                output="Usage: /vision-session <session_id>",
            )
        session = self.vision.get_session(session_id)
        return CommandResult(
            command="/vision-session",
            status="ok",
            output=f"Vision session {session.session_id}: {session.status}",
            data={"session": asdict(session)},
        )

    def _vision_cameras(self) -> CommandResult:
        cameras = [asdict(item) for item in self.vision.list_cameras()]
        return CommandResult(
            command="/vision-cameras",
            status="ok",
            output=f"{len(cameras)} camera(s).",
            data={"cameras": cameras},
        )

    def _vision_health(self) -> CommandResult:
        health = self.vision.health()
        return CommandResult(
            command="/vision-health",
            status="ok",
            output=f"Vision provider state: {health['vision']['state']}",
            data={"health": health, "capabilities": self.vision.provider_capabilities()},
        )

    def _vision_sources(self) -> CommandResult:
        sources = [asdict(item) for item in self.vision.list_sources()]
        return CommandResult(
            command="/vision-sources",
            status="ok",
            output=f"{len(sources)} capture source(s).",
            data={"sources": sources},
        )

    def _vision_analyze(self, argument_text: str) -> CommandResult:
        input_id = argument_text.strip()
        if not input_id:
            return CommandResult("/vision-analyze", "error", "Usage: /vision-analyze <input_id>")
        result = self.vision.analyze_image(input_id)
        return CommandResult(
            "/vision-analyze", "ok", f"Vision result {result.id}.", {"result": asdict(result)}
        )

    def _vision_capture_screen(self, argument_text: str) -> CommandResult:
        source_id = argument_text.strip() or "primary"
        image = self.vision.capture_screenshot(owner="command", source_id=source_id)
        return CommandResult(
            "/vision-capture-screen",
            "ok",
            f"Captured explicit screenshot {image.id}.",
            {"input_id": image.id, "checksum": image.checksum, "expires_at": image.expires_at},
        )

    def _camera_test(self, argument_text: str) -> CommandResult:
        device_id = argument_text.strip()
        if not device_id:
            return CommandResult("/camera-test", "error", "Usage: /camera-test <device_id>")
        device = self.vision.open_camera(device_id)
        self.vision.close_camera(device_id)
        return CommandResult(
            "/camera-test",
            "ok",
            f"Camera {device_id} opened and closed.",
            {"camera": asdict(device)},
        )

    def _perception_signals(self) -> CommandResult:
        signals = [asdict(item) for item in self.perception.list_signals()]
        return CommandResult(
            command="/perception-signals",
            status="ok",
            output=f"{len(signals)} perception signal(s).",
            data={"signals": signals},
        )

    def _perception_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/perception-session",
                status="error",
                output="Usage: /perception-session <session_id>",
            )
        signals = [asdict(item) for item in self.perception.list_signals_by_session(session_id)]
        return CommandResult(
            command="/perception-session",
            status="ok",
            output=f"{len(signals)} signal(s) for session {session_id}.",
            data={"signals": signals},
        )

    def _perception_type(self, argument_text: str) -> CommandResult:
        signal_type = argument_text.strip()
        if not signal_type:
            return CommandResult(
                command="/perception-type",
                status="error",
                output="Usage: /perception-type <signal_type>",
            )
        signals = [asdict(item) for item in self.perception.list_signals_by_type(signal_type)]
        return CommandResult(
            command="/perception-type",
            status="ok",
            output=f"{len(signals)} {signal_type} signal(s).",
            data={"signals": signals},
        )

    def _perception_summary(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/perception-summary",
                status="error",
                output="Usage: /perception-summary <session_id>",
            )
        summary = self.perception.summarize_session(session_id)
        return CommandResult(
            command="/perception-summary",
            status="ok",
            output=f"{summary.total_signals} signal(s) summarized for session {session_id}.",
            data={"summary": asdict(summary)},
        )

    def _perception_observations(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip() or None
        observations = [
            asdict(item) for item in self.perception.list_observations(session_id=session_id)
        ]
        return CommandResult(
            command="/perception-observations",
            status="ok",
            output=f"{len(observations)} active observation(s).",
            data={"observations": observations},
        )

    def _perception_conflicts(self) -> CommandResult:
        conflicts = [asdict(item) for item in self.perception.list_conflicts()]
        return CommandResult(
            command="/perception-conflicts",
            status="ok",
            output=f"{len(conflicts)} perception conflict(s).",
            data={"conflicts": conflicts},
        )

    def _perception_retention(self, argument_text: str) -> CommandResult:
        mode = argument_text.strip()
        if mode in {"cleanup", "dry-run"}:
            result = asdict(self.perception.cleanup(dry_run=mode == "dry-run"))
            return CommandResult(
                command="/perception-retention",
                status="ok",
                output=f"Perception retention {mode} completed.",
                data={"result": result},
            )
        status = self.perception.retention_status()
        return CommandResult(
            command="/perception-retention",
            status="ok",
            output="Perception retention policy loaded.",
            data={"retention": status},
        )

    def _perception_status(self) -> CommandResult:
        signals = self.perception.list_signals()
        observations = self.perception.list_observations()
        return CommandResult(
            "/perception-status",
            "ok",
            f"Perception ready: {len(signals)} signal(s), {len(observations)} observation(s).",
            {
                "signals": len(signals),
                "observations": len(observations),
                "retention": self.perception.retention_status(),
            },
        )

    def _perception_show(self, argument_text: str) -> CommandResult:
        identifier = argument_text.strip()
        if not identifier:
            return CommandResult(
                "/perception-show", "error", "Usage: /perception-show <signal_or_observation_id>"
            )
        try:
            item = asdict(self.perception.get_signal(identifier))
            kind = "signal"
        except NotFound:
            item = asdict(self.perception.get_observation(identifier, allow_expired=True))
            kind = "observation"
        return CommandResult(
            "/perception-show", "ok", f"Perception {kind} {identifier}.", {kind: item}
        )

    def _perception_cleanup(self, dry_run: bool) -> CommandResult:
        result = self.perception.cleanup(dry_run=dry_run)
        return CommandResult(
            "/perception-cleanup-dry-run" if dry_run else "/perception-cleanup",
            "ok",
            "Perception cleanup preview completed." if dry_run else "Perception cleanup completed.",
            {"result": asdict(result)},
        )

    def _context_fusion(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/context-fusion",
                status="error",
                output="Usage: /context-fusion <conversation_id>",
            )
        result = self.context_fusion.build_conversation_context(conversation_id)
        return CommandResult(
            command="/context-fusion",
            status="ok",
            output=f"Context built for conversation {conversation_id}.",
            data={"context": asdict(result)},
        )

    def _context_mission(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/context-mission",
                status="error",
                output="Usage: /context-mission <mission_id>",
            )
        result = self.context_fusion.build_mission_context(mission_id)
        return CommandResult(
            command="/context-mission",
            status="ok",
            output=f"Context built for mission {mission_id}.",
            data={"context": asdict(result)},
        )

    def _context_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/context-session",
                status="error",
                output="Usage: /context-session <session_id>",
            )
        result = self.context_fusion.build_multimodal_context(session_id)
        return CommandResult(
            command="/context-session",
            status="ok",
            output=f"Context built for multimodal session {session_id}.",
            data={"context": asdict(result)},
        )

    def _context_validate(self, argument_text: str) -> CommandResult:
        conversation_id = argument_text.strip()
        if not conversation_id:
            return CommandResult(
                command="/context-validate",
                status="error",
                output="Usage: /context-validate <conversation_id>",
            )
        result = self.context_fusion.build_conversation_context(conversation_id)
        return CommandResult(
            command="/context-validate",
            status="ok",
            output="Context validation completed.",
            data={"consistency": asdict(result.consistency)},
        )

    def _agent_context_preview(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        parts = argument_text.split()
        if len(parts) < 2:
            return CommandResult(
                command="/agent-context-preview",
                status="error",
                output="Usage: /agent-context-preview <agent_id> <conversation_id>",
            )
        agent_id, conversation_id = parts[0], parts[1]
        preview = self.worker.preview_context(context, agent_id, conversation_id)
        return CommandResult(
            command="/agent-context-preview",
            status="ok",
            output=f"Context preview built for {agent_id}.",
            data={"context": preview},
        )

    def _agent_multimodal_policy(self) -> CommandResult:
        policy = self.worker.multimodal_context_policy()
        return CommandResult(
            command="/agent-multimodal-policy",
            status="ok",
            output="Agent multimodal context policy loaded.",
            data={"policy": policy},
        )
