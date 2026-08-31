import pytest

from synapse.skills.errors import SkillConflict
from synapse.skills.models import SkillResolutionRequest

from .skills_support import package as _package
from .skills_support import runtime as _runtime


def test_dependency_order_and_critical_conflict_are_explainable(tmp_path):
    runtime = _runtime(tmp_path)
    runtime.install(_package(tmp_path, "dependency"))
    runtime.install(_package(tmp_path, "consumer", dependencies="[{skill_id: dependency}]"))
    assert runtime.resolve(
        SkillResolutionRequest("consumer", explicit_skill_ids=("consumer",))
    ).ordering == ("dependency", "consumer")
    runtime.install(
        _package(tmp_path, "blocker", conflicts="[{skill_id: consumer, severity: critical}]")
    )
    with pytest.raises(SkillConflict) as caught:
        runtime.resolve(
            SkillResolutionRequest("blocked", explicit_skill_ids=("consumer", "blocker"))
        )
    assert caught.value.code == "skill_conflict"
