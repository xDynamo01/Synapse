from __future__ import annotations

import json
import shlex
from dataclasses import asdict
from typing import Any

from synapse.commands.context import CommandContext, CommandInvocation, CommandResult
from synapse.commands.errors import UnknownCommandError
from synapse.commands.handlers.base import BaseCommandHandler
from synapse.commands.registry import CommandMetadata
from synapse.core.exceptions import ValidationError
from synapse.core.permissions import PermissionContext


class MissionsSwarmCommandHandler(BaseCommandHandler):
    metadata = (
        CommandMetadata(
            name="/missions",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=("argument_text=''",),
            category="user/admin useful",
            status="active",
            source_sha256="db2e1547a20142c4210a12766894587811d520524e3f88a414877ca907b5dc35",
        ),
        CommandMetadata(
            name="/mission",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="93e32999c822e1c504e44307f6c09a134bef904a473dab1d05fa844907d6a8e9",
        ),
        CommandMetadata(
            name="/create-mission",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("context", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="2e175f919b0f18ca02fd285e460b3966376513e07c7684acd26b939fa3098de4",
        ),
        CommandMetadata(
            name="/link-mission-task",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="42c9ca43da70860eb91d8d9cb22cf17c20fdbf7a85103c979a5768286e5adb2e",
        ),
        CommandMetadata(
            name="/mission-summary",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="f115e1eef64c6e216c17fbfb0e645d9e2c0ecc17b0a1b28e18b232f6f6100797",
        ),
        CommandMetadata(
            name="/mission-context",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="4740b2ffe2ca3fc3e4e970c52d660c92321cbbfbf46b97cc0fe35ee9f9f77606",
        ),
        CommandMetadata(
            name="/mission-health",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="4fd2e9085cdf35183f345b0d1266ecef863365209f804a1b7f0a77cafab62e9c",
        ),
        CommandMetadata(
            name="/mission-recovery",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="c6b431807dc1f7a87275ed7387fce196ec866402604bddcf67dd6584390ad1c8",
        ),
        CommandMetadata(
            name="/mission-supervision",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="bfc6f3b96c30a481af93548f2052c2730e84fb9adff2fc81b13b1c0f2458875e",
        ),
        CommandMetadata(
            name="/mission-attention",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="56c515c3f76b0a6a5cabd7d5c56155b717ea4a763c519bdf66176db08052b388",
        ),
        CommandMetadata(
            name="/mission-status",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="392a6c67a141dffc0e560fd7a51a8a8a48917d9c054192ed58c07352e8654a79",
        ),
        CommandMetadata(
            name="/mission-start",
            aliases=("/mission-run-once",),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7ffc84192b5121ca277ffc867e8d6ae1eb863f86e3a2aec5f9ac846945f7670c",
        ),
        CommandMetadata(
            name="/mission-pause",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="21c7cb24c94078c24b4d9e21c51968caf8b7ccec9ff8f6f006b53c6e622c666f",
        ),
        CommandMetadata(
            name="/mission-resume",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="cdbddc8b7c5e3d5b9b6e79d8938e494db47175f6570cede744a62786a6532ffc",
        ),
        CommandMetadata(
            name="/mission-cancel",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="fe3ca4142251c0710f2469b843eec009ff3444864d1cf97b99e9bc505c18cdc4",
        ),
        CommandMetadata(
            name="/mission-progress",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="673855a3d7bcc30fc962aaba59aca6c8d677d0d1f87ea1fc5e4232de3d0e2ab4",
        ),
        CommandMetadata(
            name="/mission-dispatch",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="84ace3763a13670ae7b25210a3468524529efbdc45d12771450a60e349bd0af3",
        ),
        CommandMetadata(
            name="/mission-plan",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f21a21647cdc4950dc4313800b17cc0f2a3df35529bac7d28f18acbf4a2ebbd8",
        ),
        CommandMetadata(
            name="/mission-plan-show",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="fcc09eb4313fc5486f9978d7674499e2168c453455059f1b9eba1e3c2e275c46",
        ),
        CommandMetadata(
            name="/mission-plan-validate",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="internal/test",
            status="active",
            source_sha256="60ccd450f775f1ee8d53a3fc78181e2ccca03221b4c21b9df9c3b44edeeb9044",
        ),
        CommandMetadata(
            name="/mission-plan-replace",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="b86718f3ee70f86af623caeba2f9bc75227d2207ea0d3cb75a54393c55e9b89e",
        ),
        CommandMetadata(
            name="/mission-plan-history",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="22b6967e453eabd0978d40bd2af3ec3ab4af6169d72c7a5c1573c41822405d46",
        ),
        CommandMetadata(
            name="/mission-ready-tasks",
            aliases=("/mission-blocked-tasks", "/mission-dependency-graph"),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="187f7cb7abe4a54275c183f93494f6023579eb83ef289930f8280b8ab28d8157",
        ),
        CommandMetadata(
            name="/mission-attempts",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="d69c67082e553bae060d0900ab62361f3b78e2ae7ea541d047ed213dfb344d72",
        ),
        CommandMetadata(
            name="/mission-trace",
            aliases=("/mission-trace-export",),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text"),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="f59a99ceee2b5f454abad62b6937c6cb21b4ea64904a989651d8324678d56c91",
        ),
        CommandMetadata(
            name="/swarm-status",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="d546f62fbaa966d6c23f4d5e9937d051d4e0e564349bb2d09942c031b76ee0b2",
        ),
        CommandMetadata(
            name="/swarm-start",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="4678f7f2980623c17f237f952691945d589d1082d2418753c5cc5569ff2b0ea1",
        ),
        CommandMetadata(
            name="/swarm-list",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="1a34aed6b2a76c4e67d50a2eeee8ad9fd21497c786d2d79334d5448cafc25b9b",
        ),
        CommandMetadata(
            name="/swarm-create",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="699e77867f4f802f07349c87067e23d002dc0687b33b3cc7d08de545f5e26440",
        ),
        CommandMetadata(
            name="/swarm-show",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="beee2c91cd167c1fe1ec26440487084c87036be2c48874141f7bff35fcdc330f",
        ),
        CommandMetadata(
            name="/swarm-pause",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="06fd6a83b87bdd1a8b82cc08e5f259f6ef4a34d7584470f509883346ef02156d",
        ),
        CommandMetadata(
            name="/swarm-resume",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7ce6eb6440a4451adf7e7c07d9509223b1c51a215027663f392f9ec230b22044",
        ),
        CommandMetadata(
            name="/swarm-cancel",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "argument_text", "operation"),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="367a52d969e2d9848a8aae3f0c82107205dda3b7187e1cb63bbe96c8b056b0f8",
        ),
        CommandMetadata(
            name="/swarm-result",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="093533d83570bd164340fd7fef7aa0410df02df4b9a021f702bdc321067e6b1b",
        ),
        CommandMetadata(
            name="/swarm-members",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="a5d035d257ae15dfa05d4f68cd1b50293bd19455e745ec2671a443539f5b5133",
        ),
        CommandMetadata(
            name="/swarm-trace",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="diagnostics",
            status="active",
            source_sha256="72c4b037b0ce2904e7dd7457bfd20e999fa9a958e2872b1ea2a283df2d1dff4d",
        ),
        CommandMetadata(
            name="/scheduler-pause",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "context", "argument_text", "operation"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="b1f43953cf39abe695dffc3cbf2210c32c79311e91b6adb81a1ff3fd3c77919e",
        ),
        CommandMetadata(
            name="/scheduler-resume",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "context", "argument_text", "operation"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="3c216520923bb8f8d2871f4cc2ae3f550a3b3da0cccec48aafc96be20952cc05",
        ),
        CommandMetadata(
            name="/scheduler-cancel",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command", "context", "argument_text", "operation"),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="9df221143efdb80d9ed2d960b54361504fea3e2bbecd01b21c72238e6da02765",
        ),
        CommandMetadata(
            name="/daemon-lock",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("command",),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="e6bc46e8d4892d8530905e4e26353e0174e361e09507834917947457fe868c2a",
        ),
        CommandMetadata(
            name="/daemon-recover-lock",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="operational",
            status="active",
            source_sha256="4fe827ae4a2de2483319204adaa00b7659de2bcb593a96a2a7ca1b0e82d8fa83",
        ),
        CommandMetadata(
            name="/mission-control",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="7448e2cd320905019726959ee660368b7e14c52f6ea88770228d183685e00344",
        ),
        CommandMetadata(
            name="/mission-control-card",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="6066384cf108b0e8e992a434966fa2772608e22ebbf3a4557a361fe50013d602",
        ),
        CommandMetadata(
            name="/mission-control-attention",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=(),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="f39d74c471e59974ca91d78b89628d302c3edb8e08fc6545e9e12309eab91e0a",
        ),
        CommandMetadata(
            name="/mission-control-work-queue",
            aliases=(),
            domain="missions_swarm",
            handler="MissionsSwarmCommandHandler",
            argument_names=("argument_text",),
            defaults=(),
            category="user/admin useful",
            status="active",
            source_sha256="62d0cd6d58dfeef236a4e32bd0f4456b974c69ef48906e4640b026cefa12284c",
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
        if command == "/missions":
            return self._missions(argument_text)
        if command == "/mission":
            return self._mission(argument_text)
        if command == "/create-mission":
            return self._create_mission(context, argument_text)
        if command == "/link-mission-task":
            return self._link_mission_task(argument_text)
        if command == "/mission-summary":
            return self._mission_summary(argument_text)
        if command == "/mission-context":
            return self._mission_context(argument_text)
        if command == "/mission-health":
            return self._mission_health(argument_text)
        if command == "/mission-recovery":
            return self._mission_recovery(argument_text)
        if command == "/mission-supervision":
            return self._mission_supervision()
        if command == "/mission-attention":
            return self._mission_attention()
        if command == "/mission-status":
            return self._mission_status(argument_text)
        if command in {"/mission-start", "/mission-run-once"}:
            return self._mission_transition(command, argument_text, "run_mission")
        if command == "/mission-pause":
            return self._mission_transition(command, argument_text, "pause")
        if command == "/mission-resume":
            return self._mission_transition(command, argument_text, "resume")
        if command == "/mission-cancel":
            return self._mission_transition(command, argument_text, "cancel")
        if command == "/mission-progress":
            return self._mission_progress(argument_text)
        if command == "/mission-dispatch":
            return self._mission_dispatch(argument_text)
        if command == "/mission-plan":
            return self._mission_plan_command(argument_text)
        if command == "/mission-plan-show":
            return self._mission_plan_show(argument_text)
        if command == "/mission-plan-validate":
            return self._mission_plan_validate(argument_text)
        if command == "/mission-plan-replace":
            return self._mission_plan_replace(argument_text)
        if command == "/mission-plan-history":
            return self._mission_plan_history(argument_text)
        if command in {
            "/mission-ready-tasks",
            "/mission-blocked-tasks",
            "/mission-dependency-graph",
        }:
            return self._mission_graph_command(command, argument_text)
        if command == "/mission-attempts":
            return self._mission_attempts(argument_text)
        if command in {"/mission-trace", "/mission-trace-export"}:
            return self._mission_trace_export(command, argument_text)
        if command == "/swarm-status":
            return self._swarm_status(argument_text)
        if command == "/swarm-start":
            return self._swarm_start(argument_text)
        if command == "/swarm-list":
            return self._swarm_list()
        if command == "/swarm-create":
            return self._swarm_create(argument_text)
        if command == "/swarm-show":
            return self._swarm_status(argument_text)
        if command == "/swarm-pause":
            return self._swarm_transition(command, argument_text, "pause")
        if command == "/swarm-resume":
            return self._swarm_transition(command, argument_text, "resume")
        if command == "/swarm-cancel":
            return self._swarm_transition(command, argument_text, "cancel")
        if command == "/swarm-result":
            return self._swarm_result(argument_text)
        if command == "/swarm-members":
            return self._swarm_members(argument_text)
        if command == "/swarm-trace":
            return self._swarm_trace(argument_text)
        if command == "/scheduler-pause":
            return self._scheduler_transition(command, context, argument_text, "pause_job")
        if command == "/scheduler-resume":
            return self._scheduler_transition(command, context, argument_text, "resume_job")
        if command == "/scheduler-cancel":
            return self._scheduler_transition(command, context, argument_text, "cancel_job")
        if command == "/daemon-lock":
            return self._daemon_lock(command)
        if command == "/daemon-recover-lock":
            return self._daemon_recover_lock()
        if command == "/mission-control":
            return self._mission_control()
        if command == "/mission-control-card":
            return self._mission_control_card(argument_text)
        if command == "/mission-control-attention":
            return self._mission_control_attention()
        if command == "/mission-control-work-queue":
            return self._mission_control_work_queue(argument_text)
        raise UnknownCommandError(command)

    def _missions(self, argument_text: str = "") -> CommandResult:
        status = argument_text.strip() or None
        missions = [asdict(mission) for mission in self.missions.list_missions(status=status)]
        return CommandResult(
            command="/missions",
            status="ok",
            output=f"{len(missions)} mission(s).",
            data={"missions": missions},
        )

    def _mission(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission",
                status="error",
                output="Usage: /mission <mission_id>",
            )
        mission = self.missions.get_mission(mission_id)
        return CommandResult(
            command="/mission",
            status="ok",
            output=f"Mission {mission.mission_id}: {mission.status}.",
            data={"mission": asdict(mission)},
        )

    def _create_mission(
        self,
        context: PermissionContext,
        argument_text: str,
    ) -> CommandResult:
        title = argument_text.strip().strip('"')
        if not title:
            return CommandResult(
                command="/create-mission",
                status="error",
                output='Usage: /create-mission "title"',
            )
        mission = self.missions.create_mission(
            title=title,
            status="draft",
            created_by=context.actor_id,
        )
        return CommandResult(
            command="/create-mission",
            status="ok",
            output=f"Created mission {mission.mission_id}.",
            data={"mission": asdict(mission)},
        )

    def _link_mission_task(self, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if len(parts) != 2:
            return CommandResult(
                command="/link-mission-task",
                status="error",
                output="Usage: /link-mission-task <mission_id> <task_id>",
            )
        link = self.missions.link_task(parts[0], parts[1])
        return CommandResult(
            command="/link-mission-task",
            status="ok",
            output=f"Linked task {link.task_id} to mission {link.mission_id}.",
            data={"link": asdict(link)},
        )

    def _mission_summary(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-summary",
                status="error",
                output="Usage: /mission-summary <mission_id>",
            )
        summary = self.missions.summarize_mission(mission_id)
        return CommandResult(
            command="/mission-summary",
            status="ok",
            output=f"Mission {mission_id}: {summary.total_tasks} task(s).",
            data={"summary": asdict(summary)},
        )

    def _mission_context(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-context",
                status="error",
                output="Usage: /mission-context <mission_id>",
            )
        context = self.mission_context.build_context(mission_id)
        return CommandResult(
            command="/mission-context",
            status="ok",
            output=f"Mission {mission_id} context health: {context.summary.health}.",
            data={"context": asdict(context)},
        )

    def _mission_health(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-health",
                status="error",
                output="Usage: /mission-health <mission_id>",
            )
        health = self.mission_context.mission_health(mission_id)
        return CommandResult(
            command="/mission-health",
            status="ok",
            output=f"Mission {mission_id} health: {health}.",
            data={"health": health},
        )

    def _mission_recovery(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-recovery",
                status="error",
                output="Usage: /mission-recovery <mission_id>",
            )
        decisions = [
            asdict(decision)
            for decision in self.mission_context.list_mission_recovery_candidates(mission_id)
        ]
        return CommandResult(
            command="/mission-recovery",
            status="ok",
            output=f"Mission {mission_id}: {len(decisions)} recovery candidate(s).",
            data={"recovery_candidates": decisions},
        )

    def _mission_supervision(self) -> CommandResult:
        summary = self.mission_supervision.build_summary()
        return CommandResult(
            command="/mission-supervision",
            status="ok",
            output=(
                f"{summary.total_missions} mission(s): "
                f"{summary.attention_required_count} requiring attention."
            ),
            data={"summary": asdict(summary)},
        )

    def _mission_attention(self) -> CommandResult:
        items = [asdict(item) for item in self.mission_supervision.list_attention_items()]
        return CommandResult(
            command="/mission-attention",
            status="ok",
            output=f"{len(items)} mission attention item(s).",
            data={"attention_items": items},
        )

    def _mission_status(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-status",
                status="error",
                output="Usage: /mission-status <mission_id>",
            )
        state = self.mission_supervision.mission_status(mission_id)
        return CommandResult(
            command="/mission-status",
            status="ok",
            output=f"Mission {mission_id} severity: {state.severity}.",
            data={"state": asdict(state)},
        )

    def _mission_control(self) -> CommandResult:
        overview = self.mission_control.get_overview()
        return CommandResult(
            command="/mission-control",
            status="ok",
            output=(
                f"{overview.total_missions} mission(s), "
                f"{overview.attention_required_count} requiring attention."
            ),
            data={"overview": asdict(overview)},
        )

    def _mission_transition(
        self, command: str, argument_text: str, operation: str
    ) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <mission_id>"
            )
        mission = getattr(self.missions, operation)(mission_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"Mission {mission_id}: {mission.status}.",
            data=asdict(mission),
        )

    def _mission_progress(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-progress",
                status="error",
                output="Usage: /mission-progress <mission_id>",
            )
        mission = self.missions.get_mission(mission_id)
        return CommandResult(
            command="/mission-progress",
            status="ok",
            output=f"Mission {mission_id}: {mission.progress}%.",
            data=asdict(mission),
        )

    def _mission_dispatch(self, argument_text: str) -> CommandResult:
        parts = argument_text.split()
        if not parts:
            return CommandResult(
                command="/mission-dispatch",
                status="error",
                output="Usage: /mission-dispatch <mission_id> [max_concurrency]",
            )
        result = self.missions.dispatch_ready_tasks(
            parts[0], int(parts[1]) if len(parts) > 1 else None
        )
        return CommandResult(
            command="/mission-dispatch",
            status="ok",
            output=f"{len(result.dispatched)} attempt(s) dispatched.",
            data=asdict(result),
        )

    def _mission_plan_command(self, argument_text: str) -> CommandResult:
        mission_id, tasks = self._plan_arguments(argument_text)
        mission = self.missions.get_mission(mission_id)
        plan = self.missions.planner.create_plan(
            mission_id,
            mission.objective,
            tasks=tasks,
        )
        self.missions.attach_plan(mission_id, plan.plan_id)
        return CommandResult(
            command="/mission-plan",
            status="ok",
            output=f"Plan {plan.plan_id} created.",
            data=asdict(plan),
        )

    def _mission_plan_show(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if not parts:
            return CommandResult(
                command="/mission-plan-show",
                status="error",
                output="Usage: /mission-plan-show <mission_id> [plan_id]",
            )
        mission = self.missions.get_mission(parts[0])
        plan_id = parts[1] if len(parts) > 1 else mission.plan_id
        if not plan_id:
            raise ValidationError("Mission has no active plan.")
        plan = self.missions.planner.get_plan(parts[0], plan_id)
        return CommandResult(
            command="/mission-plan-show",
            status="ok",
            output=f"Plan {plan.plan_id} version {plan.version}.",
            data=asdict(plan),
        )

    def _mission_plan_validate(self, argument_text: str) -> CommandResult:
        from synapse.missions.models import MissionPlan, MissionTask

        mission_id, tasks = self._plan_arguments(argument_text)
        parsed = [MissionTask(mission_id=mission_id, **item) for item in tasks]
        result = self.missions.planner.validate_plan(MissionPlan(mission_id, parsed))
        return CommandResult(
            command="/mission-plan-validate",
            status="ok",
            output=f"Plan valid: {result.valid}.",
            data=asdict(result),
        )

    def _mission_plan_replace(self, argument_text: str) -> CommandResult:
        parts = argument_text.strip().split(maxsplit=3)
        if len(parts) != 4:
            return CommandResult(
                command="/mission-plan-replace",
                status="error",
                output="Usage: /mission-plan-replace <mission_id> <plan_id> <version> <tasks_json>",
            )
        tasks = json.loads(parts[3])
        if not isinstance(tasks, list):
            raise ValidationError("tasks_json must be a JSON list.")
        plan = self.missions.planner.replace_plan(parts[0], parts[1], int(parts[2]), tasks)
        self.missions.attach_plan(parts[0], plan.plan_id)
        return CommandResult(
            command="/mission-plan-replace",
            status="ok",
            output=f"Plan replaced by {plan.plan_id} version {plan.version}.",
            data=asdict(plan),
        )

    def _mission_plan_history(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-plan-history",
                status="error",
                output="Usage: /mission-plan-history <mission_id>",
            )
        plans = [asdict(item) for item in self.missions.planner.list_plans(mission_id)]
        return CommandResult(
            command="/mission-plan-history",
            status="ok",
            output=f"{len(plans)} plan version(s).",
            data={"plans": plans},
        )

    def _mission_graph_command(self, command: str, argument_text: str) -> CommandResult:
        from synapse.missions.dag import TaskGraph

        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <mission_id>"
            )
        graph = TaskGraph(self.missions.list_tasks(mission_id))
        data: dict[str, Any]
        if command == "/mission-ready-tasks":
            data = {"tasks": [asdict(item) for item in graph.ready_tasks()]}
        elif command == "/mission-blocked-tasks":
            data = {"tasks": [asdict(item) for item in graph.blocked_tasks()]}
        else:
            data = {
                "topological_order": graph.topological_order(),
                "dependencies": {
                    task_id: sorted(dependencies)
                    for task_id, dependencies in graph.dependencies.items()
                },
            }
        return CommandResult(
            command=command, status="ok", output=f"Graph query for mission {mission_id}.", data=data
        )

    @staticmethod
    def _plan_arguments(argument_text: str) -> tuple[str, list[dict[str, Any]]]:
        parts = argument_text.strip().split(maxsplit=1)
        if len(parts) != 2:
            raise ValidationError("Expected <mission_id> <tasks_json>.")
        tasks = json.loads(parts[1])
        if not isinstance(tasks, list):
            raise ValidationError("tasks_json must be a JSON list.")
        return parts[0], tasks

    def _mission_attempts(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id or not self.attempts:
            return CommandResult(
                command="/mission-attempts",
                status="error",
                output="Usage: /mission-attempts <mission_id>",
            )
        attempts = [asdict(item) for item in self.attempts.list(mission_id=mission_id)]
        return CommandResult(
            command="/mission-attempts",
            status="ok",
            output=f"{len(attempts)} attempt(s).",
            data={"attempts": attempts},
        )

    def _mission_trace_export(self, command: str, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        trace = getattr(self, "mission_trace", None)
        if not mission_id or not trace:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <mission_id>"
            )
        exported = trace.export(mission_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"{exported['summary']['total_events']} trace event(s).",
            data=exported,
        )

    def _swarm_status(self, argument_text: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm:
            return CommandResult(
                command="/swarm-status", status="error", output="Usage: /swarm-status <swarm_id>"
            )
        swarm = self.swarm.get(swarm_id)
        return CommandResult(
            command="/swarm-status",
            status="ok",
            output=f"Swarm {swarm_id}: {swarm.status}.",
            data=asdict(swarm),
        )

    def _swarm_start(self, argument_text: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm:
            return CommandResult(
                command="/swarm-start", status="error", output="Usage: /swarm-start <swarm_id>"
            )
        result = self.swarm.run(swarm_id)
        return CommandResult(
            command="/swarm-start",
            status="ok",
            output=f"Swarm {swarm_id}: {result['status']}.",
            data=result,
        )

    def _swarm_list(self) -> CommandResult:
        swarms = [asdict(item) for item in self.swarm.list()] if self.swarm else []
        return CommandResult(
            command="/swarm-list",
            status="ok",
            output=f"{len(swarms)} swarm(s).",
            data={"swarms": swarms},
        )

    def _swarm_create(self, argument_text: str) -> CommandResult:
        parts = shlex.split(argument_text)
        if len(parts) < 4 or not self.swarm:
            return CommandResult(
                command="/swarm-create",
                status="error",
                output="Usage: /swarm-create <mission_id> <strategy> <leader|-> <member,...>",
            )
        swarm = self.swarm.create(
            parts[0],
            parts[1],
            None if parts[2] == "-" else parts[2],
            [item for item in parts[3].split(",") if item],
        )
        return CommandResult(
            command="/swarm-create",
            status="ok",
            output=f"Swarm {swarm.swarm_id} created.",
            data=asdict(swarm),
        )

    def _swarm_transition(self, command: str, argument_text: str, operation: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <swarm_id>"
            )
        swarm = getattr(self.swarm, operation)(swarm_id)
        return CommandResult(
            command=command,
            status="ok",
            output=f"Swarm {swarm_id}: {swarm.status}.",
            data=asdict(swarm),
        )

    def _swarm_result(self, argument_text: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm:
            return CommandResult(
                command="/swarm-result", status="error", output="Usage: /swarm-result <swarm_id>"
            )
        result = self.swarm.get_result(swarm_id)
        return CommandResult(
            command="/swarm-result",
            status="ok",
            output=f"Result for swarm {swarm_id}.",
            data=result,
        )

    def _swarm_members(self, argument_text: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm:
            return CommandResult(
                command="/swarm-members", status="error", output="Usage: /swarm-members <swarm_id>"
            )
        swarm = self.swarm.get(swarm_id)
        return CommandResult(
            command="/swarm-members",
            status="ok",
            output=f"{len(swarm.member_agent_ids)} member(s).",
            data={
                "leader_agent_id": swarm.leader_agent_id,
                "member_agent_ids": swarm.member_agent_ids,
            },
        )

    def _swarm_trace(self, argument_text: str) -> CommandResult:
        swarm_id = argument_text.strip()
        if not swarm_id or not self.swarm or not self.mission_trace:
            return CommandResult(
                command="/swarm-trace", status="error", output="Usage: /swarm-trace <swarm_id>"
            )
        swarm = self.swarm.get(swarm_id)
        events = [
            asdict(item)
            for item in self.mission_trace.list(swarm.mission_id, limit=500)
            if item.swarm_id in {None, swarm_id}
        ]
        return CommandResult(
            command="/swarm-trace",
            status="ok",
            output=f"{len(events)} trace event(s).",
            data={"events": events},
        )

    def _scheduler_transition(
        self,
        command: str,
        context: PermissionContext,
        argument_text: str,
        operation: str,
    ) -> CommandResult:
        job_id = argument_text.strip()
        if not job_id:
            return CommandResult(
                command=command, status="error", output=f"Usage: {command} <job_id>"
            )
        job = getattr(self.scheduler, operation)(context, job_id)
        return CommandResult(
            command=command, status="ok", output=f"Job {job_id}: {job.status}.", data=asdict(job)
        )

    def _daemon_lock(self, command: str) -> CommandResult:
        status = self.scheduler.lock_status()
        return CommandResult(
            command=command,
            status="ok",
            output=f"Scheduler lock active: {status['locked']}.",
            data=status,
        )

    def _daemon_recover_lock(self) -> CommandResult:
        result = self.scheduler.recover_stale_lock()
        return CommandResult(
            command="/daemon-recover-lock",
            status="ok",
            output=f"Lock recovered: {result['recovered']}.",
            data=result,
        )

    def _mission_control_card(self, argument_text: str) -> CommandResult:
        mission_id = argument_text.strip()
        if not mission_id:
            return CommandResult(
                command="/mission-control-card",
                status="error",
                output="Usage: /mission-control-card <mission_id>",
            )
        card = self.mission_control.get_mission_card(mission_id)
        return CommandResult(
            command="/mission-control-card",
            status="ok",
            output=f"Mission {mission_id}: {card.health}, {card.progress_percent}% complete.",
            data={"card": asdict(card)},
        )

    def _mission_control_attention(self) -> CommandResult:
        panel = self.mission_control.get_attention_panel()
        return CommandResult(
            command="/mission-control-attention",
            status="ok",
            output=f"{panel.total_items} mission control attention item(s).",
            data={"attention_panel": asdict(panel)},
        )

    def _mission_control_work_queue(self, argument_text: str) -> CommandResult:
        agent_id = argument_text.strip() or None
        queue = self.mission_control.get_work_queue(agent_id)
        return CommandResult(
            command="/mission-control-work-queue",
            status="ok",
            output=f"{queue.total_items} mission control work item(s).",
            data={"work_queue": asdict(queue)},
        )
