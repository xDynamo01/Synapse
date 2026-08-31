from synapse.skills.models import SkillAssignment

from .skills_support import package as _package
from .skills_support import runtime as _runtime


def test_restart_preserves_package_and_assignment_without_duplication(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "restart-skill"))
    assignment = runtime.assign(SkillAssignment("researcher", "restart-skill", "^1.0.0"))
    restarted = _runtime(tmp_path)
    assert restarted.versions("restart-skill") == ("1.0.0",)
    assert (
        restarted.assignment_summaries("researcher")[0]["assignment_id"] == assignment.assignment_id
    )
