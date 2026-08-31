from __future__ import annotations

import shlex
from dataclasses import asdict

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata


class VoiceMultimodalCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/voice-sessions",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6a0e6cd4ff92400465a01b66d9025a8c069deef54a71f9b5e733b350fe9e2953",
        ),
        CommandMetadata(
            name="/voice-session",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="ecd025bbed57eb12071d49bffb25f49bc2c866577d77b3d8a19baba12020643f",
        ),
        CommandMetadata(
            name="/voice-queue",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="8d54184d4b25ac137d61b1fc2229cf1db7daf9317da3b2833c4b7b6a74bc1fae",
        ),
        CommandMetadata(
            name="/voice-utterances",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="47d0f416a67b98885213a01467494c0c5624c5f49d4d7a88970805421dad3dca",
        ),
        CommandMetadata(
            name="/voice-settings",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="e6b80b5badf1c4dfc41ced6c1af12c72784d7be019832286f0b21ad5da14e87a",
        ),
        CommandMetadata(
            name="/voice-devices-input",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("direction",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="eaf9a9b91534f3d98637b031ff5d6632d8350b814deb2a0f62b975d905476eb3",
        ),
        CommandMetadata(
            name="/voice-devices-output",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("direction",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f6c2a5f920024e730ba98dabd3cef5c26373d2c38a58aa004d8e10af49c62935",
        ),
        CommandMetadata(
            name="/voice-session-pause",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text", "action"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="0cd6217a8b6ee19a08d6061dd6dd9cfeb57aa49ab87f39f7a6fc0d43eeaee6fb",
        ),
        CommandMetadata(
            name="/voice-session-resume",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text", "action"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c1f74f25b03ddf61985b6495fa0cb7691af9f89a13cdcbac57a8f94af963840b",
        ),
        CommandMetadata(
            name="/voice-session-cancel",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text", "action"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="1bc32f6510aab5c11981c21c1ead941b6b1e77a125f1e2bc32cb1ab2393e8785",
        ),
        CommandMetadata(
            name="/voice-session-close",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text", "action"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6320507681db107419d6733136bbec499f7ccc37dac1602e20c513302ae1b7a1",
        ),
        CommandMetadata(
            name="/voice-cleanup",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("dry_run",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="caac6320fec59625518b7a6966ce67b6781234e60cb1ce6ae1f550923622ca9a",
        ),
        CommandMetadata(
            name="/voice-cleanup-dry-run",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("dry_run",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="36792329a93c69b329ebb50c9e1eff13aeab7f99f9b7e78bb0b0eaab42dfb60e",
        ),
        CommandMetadata(
            name="/speech-sessions",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="132b37d6c3b6518be8a41a60a700825020356bec6e59dd50641c28fbf8ae414c",
        ),
        CommandMetadata(
            name="/speech-session",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="0f75cfa8a2d77b268515fd3ecd1e4fe7f8335e778b7c9318c83f50bd09d4ce01",
        ),
        CommandMetadata(
            name="/speech-summary",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="b0e8e27a97f241e5c27d22b785d18775db7e9dd89bf9994bdefae743607d732b",
        ),
        CommandMetadata(
            name="/speech-adapters",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="3979afd033032eedd8b0498c86fa17309fdddccdeb6c03a79936c17405b20676",
        ),
        CommandMetadata(
            name="/speech-adapter",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2a7bc42a7cc2e03df2cfabdf1313eeda39dd5f63e23e51e5de485ecc1516de28",
        ),
        CommandMetadata(
            name="/speech-adapter-health",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="0ad18090e6e97177d5d8793f107c11aa24a7d9c8196f3236ac565570e32b257a",
        ),
        CommandMetadata(
            name="/speech-adapter-resolve",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="32b4209ed54d3fd4e77158ce7db810a40d71ea1e9e8d886c665d78f682b7dade",
        ),
        CommandMetadata(
            name="/multimodal-sessions",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="60e4ca34e6f632dd4b06eaf1c2ef2d44b3151c91b914fd0e4445d951453ba5f3",
        ),
        CommandMetadata(
            name="/multimodal-session",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fe42fa541cb540de453beae595c70c261302821b5ffa38ce881e3b110c5647ee",
        ),
        CommandMetadata(
            name="/multimodal-channels",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="0e170cee04d0663e4ce66621b13fdd8fd2483dc1e15a29d24a34e18df4448016",
        ),
        CommandMetadata(
            name="/multimodal-fusions",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="017e421b09df5bc51f80f14a61d4d1f5762f73b621080307b124618fcd5d6413",
        ),
        CommandMetadata(
            name="/multimodal-fuse",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="181dd92fe5de09ab6ced39307b24cca0036545dbe332dbcbe06830eae22f585e",
        ),
        CommandMetadata(
            name="/multimodal-show",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="acb7a75bfd1fd9eda2274be5f8222b757aaf1705c4ee6a100ceae3c47b417ed7",
        ),
        CommandMetadata(
            name="/audio-sessions",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d01d4dddc10affc60c301d8ca20a04637b7955d19954382e9898aa014b5ae4b3",
        ),
        CommandMetadata(
            name="/audio-session",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="296f21a1d6e2d3f7df4b25653ff5be1ad7f8cceeb677c7e300069952d532c689",
        ),
        CommandMetadata(
            name="/audio-devices",
            aliases=(),
            domain="voice_multimodal",
            handler="VoiceMultimodalCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="26a968162c110f01b8201790e9248ab8e1b1d0a078f10a37ca332720be8a4836",
        ),
    )

    def execute(
        self,
        command_context: CommandContext,
        invocation: CommandInvocation,
    ) -> CommandResult:
        command = invocation.command_name
        argument_text = invocation.argument_text
        if command == "/voice-sessions":
            return self._voice_sessions()
        if command == "/voice-session":
            return self._voice_session(argument_text)
        if command == "/voice-queue":
            return self._voice_queue(argument_text)
        if command == "/voice-utterances":
            return self._voice_utterances(argument_text)
        if command == "/voice-settings":
            return self._voice_settings()
        if command == "/voice-devices-input":
            return self._voice_devices("input")
        if command == "/voice-devices-output":
            return self._voice_devices("output")
        if command == "/voice-session-pause":
            return self._voice_session_action(argument_text, "pause")
        if command == "/voice-session-resume":
            return self._voice_session_action(argument_text, "resume")
        if command == "/voice-session-cancel":
            return self._voice_session_action(argument_text, "cancel")
        if command == "/voice-session-close":
            return self._voice_session_action(argument_text, "close")
        if command == "/voice-cleanup":
            return self._voice_cleanup(False)
        if command == "/voice-cleanup-dry-run":
            return self._voice_cleanup(True)
        if command == "/speech-sessions":
            return self._speech_sessions()
        if command == "/speech-session":
            return self._speech_session(argument_text)
        if command == "/speech-summary":
            return self._speech_summary(argument_text)
        if command == "/speech-adapters":
            return self._speech_adapters()
        if command == "/speech-adapter":
            return self._speech_adapter(argument_text)
        if command == "/speech-adapter-health":
            return self._speech_adapter_health()
        if command == "/speech-adapter-resolve":
            return self._speech_adapter_resolve(argument_text)
        if command == "/multimodal-sessions":
            return self._multimodal_sessions()
        if command == "/multimodal-session":
            return self._multimodal_session(argument_text)
        if command == "/multimodal-channels":
            return self._multimodal_channels()
        if command == "/multimodal-fusions":
            return self._multimodal_fusions(argument_text)
        if command == "/multimodal-fuse":
            return self._multimodal_fuse(argument_text)
        if command == "/multimodal-show":
            return self._multimodal_show(argument_text)
        if command == "/audio-sessions":
            return self._audio_sessions()
        if command == "/audio-session":
            return self._audio_session(argument_text)
        if command == "/audio-devices":
            return self._audio_devices()
        raise UnknownCommandError(command)

    def _voice_sessions(self) -> CommandResult:
        sessions = [asdict(item) for item in self.voice.list_sessions()]
        return CommandResult(
            command="/voice-sessions",
            status="ok",
            output=f"{len(sessions)} voice session(s).",
            data={"sessions": sessions},
        )

    def _voice_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/voice-session",
                status="error",
                output="Usage: /voice-session <session_id>",
            )
        summary = self.voice.summarize_session(session_id)
        return CommandResult(
            command="/voice-session",
            status="ok",
            output=f"Voice session {summary.session.session_id}: {summary.session.status}",
            data={"summary": asdict(summary)},
        )

    def _voice_queue(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 2:
            return CommandResult(
                command="/voice-queue",
                status="error",
                output='Usage: /voice-queue <session_id> "<text>"',
            )
        utterance = self.voice.queue_utterance(parts[0], " ".join(parts[1:]))
        return CommandResult(
            command="/voice-queue",
            status="ok",
            output=f"Queued voice utterance {utterance.utterance_id}.",
            data={"utterance": asdict(utterance)},
        )

    def _voice_utterances(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/voice-utterances",
                status="error",
                output="Usage: /voice-utterances <session_id>",
            )
        utterances = [asdict(item) for item in self.voice.list_utterances(session_id)]
        return CommandResult(
            command="/voice-utterances",
            status="ok",
            output=f"{len(utterances)} voice utterance(s).",
            data={"utterances": utterances},
        )

    def _voice_settings(self) -> CommandResult:
        settings = asdict(self.voice.get_settings())
        return CommandResult(
            command="/voice-settings",
            status="ok",
            output="Voice settings loaded.",
            data={"settings": settings},
        )

    def _voice_devices(self, direction: str) -> CommandResult:
        devices = [asdict(item) for item in self.audio.devices.list_devices(direction)]
        return CommandResult(
            command=f"/voice-devices-{direction}",
            status="ok",
            output=f"{len(devices)} {direction} device(s).",
            data={"devices": devices},
        )

    def _voice_session_action(self, argument_text: str, action: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command=f"/voice-session-{action}",
                status="error",
                output=f"Usage: /voice-session-{action} <session_id>",
            )
        handlers = {
            "pause": self.voice.pause_session,
            "resume": self.voice.resume_session,
            "cancel": self.voice.cancel_session,
            "close": self.voice.close_session,
        }
        session = handlers[action](session_id)
        return CommandResult(
            command=f"/voice-session-{action}",
            status="ok",
            output=f"Voice session {action}: {session.status}.",
            data={"session": asdict(session)},
        )

    def _voice_cleanup(self, dry_run: bool) -> CommandResult:
        report = self.voice.cleanup_voice_storage(dry_run=dry_run)
        return CommandResult(
            command="/voice-cleanup-dry-run" if dry_run else "/voice-cleanup",
            status="ok",
            output="Voice storage cleanup evaluated.",
            data={"report": asdict(report)},
        )

    def _speech_sessions(self) -> CommandResult:
        sessions = [asdict(item) for item in self.speech_pipeline.list_sessions()]
        return CommandResult(
            command="/speech-sessions",
            status="ok",
            output=f"{len(sessions)} speech pipeline session(s).",
            data={"sessions": sessions},
        )

    def _speech_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/speech-session",
                status="error",
                output="Usage: /speech-session <session_id>",
            )
        session = self.speech_pipeline.get_session(session_id)
        return CommandResult(
            command="/speech-session",
            status="ok",
            output=f"Speech pipeline session {session.pipeline_session_id}: {session.status}",
            data={"session": asdict(session)},
        )

    def _speech_summary(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/speech-summary",
                status="error",
                output="Usage: /speech-summary <session_id>",
            )
        summary = self.speech_pipeline.summarize_session(session_id)
        return CommandResult(
            command="/speech-summary",
            status="ok",
            output=(
                f"Speech summary: {summary.input_turn_count} input turn(s), "
                f"{summary.output_turn_count} output turn(s)."
            ),
            data={"summary": asdict(summary)},
        )

    def _speech_adapters(self) -> CommandResult:
        adapters = [asdict(adapter) for adapter in self.speech_adapters.list_adapters()]
        return CommandResult(
            command="/speech-adapters",
            status="ok",
            output=f"{len(adapters)} speech adapter(s).",
            data={"adapters": adapters},
        )

    def _speech_adapter(self, argument_text: str) -> CommandResult:
        adapter_id = argument_text.strip()
        if not adapter_id:
            return CommandResult(
                command="/speech-adapter",
                status="error",
                output="Usage: /speech-adapter <adapter_id>",
            )
        adapter = self.speech_adapters.get_adapter(adapter_id)
        return CommandResult(
            command="/speech-adapter",
            status="ok",
            output=f"Speech adapter {adapter.adapter_id}: {adapter.adapter_type}",
            data={"adapter": asdict(adapter)},
        )

    def _speech_adapter_health(self) -> CommandResult:
        health = [asdict(item) for item in self.speech_adapters.list_adapter_health()]
        return CommandResult(
            command="/speech-adapter-health",
            status="ok",
            output=f"{len(health)} speech adapter health record(s).",
            data={"health": health},
        )

    def _speech_adapter_resolve(self, argument_text: str) -> CommandResult:
        capability_id = argument_text.strip()
        if not capability_id:
            return CommandResult(
                command="/speech-adapter-resolve",
                status="error",
                output="Usage: /speech-adapter-resolve <capability_id>",
            )
        resolution = self.speech_adapters.resolve_adapter_for_capability(capability_id)
        return CommandResult(
            command="/speech-adapter-resolve",
            status="ok",
            output=f"Selected speech adapter {resolution.selected_adapter_id}.",
            data={"resolution": asdict(resolution)},
        )

    def _multimodal_sessions(self) -> CommandResult:
        sessions = [asdict(item) for item in self.multimodal.list_sessions()]
        return CommandResult(
            command="/multimodal-sessions",
            status="ok",
            output=f"{len(sessions)} multimodal session(s).",
            data={"sessions": sessions},
        )

    def _multimodal_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/multimodal-session",
                status="error",
                output="Usage: /multimodal-session <session_id>",
            )
        session = self.multimodal.get_session(session_id)
        return CommandResult(
            command="/multimodal-session",
            status="ok",
            output=f"Multimodal session {session.session_id}: {session.status}",
            data={"session": asdict(session)},
        )

    def _multimodal_channels(self) -> CommandResult:
        channels = self.multimodal.get_supported_channels()
        return CommandResult(
            command="/multimodal-channels",
            status="ok",
            output=f"{len(channels)} multimodal channel(s).",
            data={"channels": channels},
        )

    def _multimodal_fusions(self, argument_text: str) -> CommandResult:
        correlation_id = argument_text.strip() or None
        items = [asdict(item) for item in self.multimodal.list_fusions(correlation_id)]
        return CommandResult(
            command="/multimodal-fusions",
            status="ok",
            output=f"{len(items)} multimodal fusion(s).",
            data={"fusions": items},
        )

    def _multimodal_fuse(self, argument_text: str) -> CommandResult:
        observation_ids = [item.strip() for item in argument_text.split(",") if item.strip()]
        if not observation_ids:
            return CommandResult(
                "/multimodal-fuse", "error", "Usage: /multimodal-fuse <observation_id,...>"
            )
        fusion = self.multimodal.fuse(observation_ids)
        return CommandResult(
            "/multimodal-fuse", "ok", f"Created fusion {fusion.id}.", {"fusion": asdict(fusion)}
        )

    def _multimodal_show(self, argument_text: str) -> CommandResult:
        fusion_id = argument_text.strip()
        if not fusion_id:
            return CommandResult("/multimodal-show", "error", "Usage: /multimodal-show <fusion_id>")
        fusion = self.multimodal.get_fusion(fusion_id)
        return CommandResult(
            "/multimodal-show", "ok", f"Fusion {fusion.id}.", {"fusion": asdict(fusion)}
        )

    def _audio_sessions(self) -> CommandResult:
        sessions = [asdict(item) for item in self.audio.list_sessions()]
        return CommandResult(
            command="/audio-sessions",
            status="ok",
            output=f"{len(sessions)} audio session(s).",
            data={"sessions": sessions},
        )

    def _audio_session(self, argument_text: str) -> CommandResult:
        session_id = argument_text.strip()
        if not session_id:
            return CommandResult(
                command="/audio-session",
                status="error",
                output="Usage: /audio-session <session_id>",
            )
        session = self.audio.get_session(session_id)
        return CommandResult(
            command="/audio-session",
            status="ok",
            output=f"Audio session {session.session_id}: {session.status}",
            data={"session": asdict(session)},
        )

    def _audio_devices(self) -> CommandResult:
        devices = [asdict(item) for item in self.audio.list_devices()]
        return CommandResult(
            command="/audio-devices",
            status="ok",
            output=f"{len(devices)} audio device(s).",
            data={"devices": devices},
        )
