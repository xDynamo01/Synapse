from synapse.skills.models import SkillAssignment, SkillResolutionRequest

from .skills_support import package as _package
from .skills_support import runtime as _runtime


def test_primary_assignment_resolves_and_loads_progressively(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "primary-review"))
    runtime.assign(SkillAssignment("orchestrator", "primary-review", "^1.0.0"))
    resolved = runtime.resolve(
        SkillResolutionRequest(
            "evidence primary-review",
            explicit_skill_ids=("primary-review",),
            agent_id="orchestrator",
            agent_kind="primary",
        )
    )
    loaded = runtime.load_assigned("orchestrator")
    assert resolved.ordering == ("primary-review",)
    assert loaded[0].instructions and loaded[0].references == {}
