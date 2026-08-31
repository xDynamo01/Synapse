from synapse.skills.models import SkillAssignment, SkillScope

from .skills_support import package as _package
from .skills_support import runtime as _runtime


def test_project_scope_precedence_uses_shared_package_without_copy(tmp_path):
    runtime = _runtime(tmp_path)
    source = _package(tmp_path, "project-review")
    runtime.install(source)
    runtime.assign(
        SkillAssignment(
            "researcher",
            "project-review",
            "^1.0.0",
            SkillScope.PROJECT,
            metadata={"project_id": "synapse"},
        )
    )
    assert runtime.load_assigned("researcher", project_id="other") == ()
    assert runtime.load_assigned("researcher", project_id="synapse")[0].skill_id == "project-review"
    assert not (tmp_path / "agents" / "researcher" / "skills" / "project-review").exists()
