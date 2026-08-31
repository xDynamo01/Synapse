from datetime import UTC, datetime, timedelta

from .skills_support import package as _package
from .skills_support import runtime as _runtime


def test_ephemeral_skill_lease_is_bounded_and_cleaned(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "leased-review", tools="[read_file, write_file]"))
    leases = runtime.grant_for_ephemeral(
        "ephemeral:e2e",
        ("leased-review",),
        mission_id="mission-e2e",
        task_id="task-e2e",
        expires_at=(datetime.now(UTC) + timedelta(minutes=2)).isoformat(),
        context_budget=500,
        allowed_tools=("read_file",),
        correlation_id="corr-e2e",
    )
    assert leases[0]["tool_scope"] == ("read_file",)
    assert runtime.cleanup_leases("ephemeral:e2e") == 1
