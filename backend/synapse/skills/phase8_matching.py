from __future__ import annotations

from synapse.skills.phase2_models import (
    SkillDependencyDeclaration,
    SkillVersion,
    SkillVersionConstraint,
)
from synapse.skills.phase8_errors import InvalidSkillDependencyDeclaration


def matches_declaration(
    declaration: SkillDependencyDeclaration,
    version: SkillVersion,
) -> bool:
    """Return a structural match without ranking or selecting a version."""
    if declaration.version is not None:
        return declaration.version == version
    if declaration.constraint is None:
        raise InvalidSkillDependencyDeclaration()
    return matches_constraint(declaration.constraint, version)


def matches_constraint(
    constraint: SkillVersionConstraint,
    version: SkillVersion,
) -> bool:
    if version.prerelease:
        return False
    if constraint.kind == "caret":
        lower = SkillVersion.parse(constraint.value.removeprefix("^"))
        if lower.major > 0:
            upper = SkillVersion(lower.major + 1, 0, 0)
        elif lower.minor > 0:
            upper = SkillVersion(0, lower.minor + 1, 0)
        else:
            upper = SkillVersion(0, 0, lower.patch + 1)
        return (
            version.compare_precedence(lower) >= 0
            and version.compare_precedence(upper) < 0
        )
    lower_text, upper_text = constraint.value.split(",", 1)
    lower_operator = ">=" if lower_text.startswith(">=") else ">"
    upper_operator = "<=" if upper_text.startswith("<=") else "<"
    lower = SkillVersion.parse(lower_text.removeprefix(lower_operator))
    upper = SkillVersion.parse(upper_text.removeprefix(upper_operator))
    lower_comparison = version.compare_precedence(lower)
    upper_comparison = version.compare_precedence(upper)
    return (
        lower_comparison >= 0
        if lower_operator == ">="
        else lower_comparison > 0
    ) and (
        upper_comparison <= 0
        if upper_operator == "<="
        else upper_comparison < 0
    )


def constraint_has_solution(constraint: SkillVersionConstraint) -> bool:
    if constraint.kind == "caret":
        return True
    lower_text, upper_text = constraint.value.split(",", 1)
    lower_operator = ">=" if lower_text.startswith(">=") else ">"
    upper_operator = "<=" if upper_text.startswith("<=") else "<"
    lower = SkillVersion.parse(lower_text.removeprefix(lower_operator))
    upper = SkillVersion.parse(upper_text.removeprefix(upper_operator))
    candidate = (
        lower
        if lower_operator == ">="
        else SkillVersion(lower.major, lower.minor, lower.patch + 1)
    )
    comparison = candidate.compare_precedence(upper)
    return comparison <= 0 if upper_operator == "<=" else comparison < 0
