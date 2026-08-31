from __future__ import annotations

from dataclasses import dataclass

from synapse.skills.phase2_models import (
    SkillDependencyDeclaration,
    SkillVersion,
)
from synapse.skills.phase8_matching import matches_declaration


@dataclass(frozen=True)
class DependencyConstraintIntersection:
    exact: SkillVersion | None
    lower: SkillVersion | None
    lower_inclusive: bool
    upper: SkillVersion | None
    upper_inclusive: bool

    def contains(self, version: SkillVersion) -> bool:
        if self.exact is not None:
            return self.exact == version
        if version.prerelease:
            return False
        if self.lower is not None:
            comparison = version.compare_precedence(self.lower)
            if comparison < 0 or (comparison == 0 and not self.lower_inclusive):
                return False
        if self.upper is not None:
            comparison = version.compare_precedence(self.upper)
            if comparison > 0 or (comparison == 0 and not self.upper_inclusive):
                return False
        return True


def intersect_dependency_declarations(
    declarations: tuple[SkillDependencyDeclaration, ...],
) -> DependencyConstraintIntersection | None:
    exacts = tuple(
        declaration.version
        for declaration in declarations
        if declaration.version is not None
    )
    if exacts:
        exact = exacts[0]
        if any(candidate != exact for candidate in exacts[1:]):
            return None
        if not all(matches_declaration(declaration, exact) for declaration in declarations):
            return None
        return DependencyConstraintIntersection(exact, None, True, None, True)

    lower: SkillVersion | None = None
    lower_inclusive = True
    upper: SkillVersion | None = None
    upper_inclusive = True
    for declaration in declarations:
        constraint = declaration.constraint
        if constraint is None:
            return None
        current_lower, current_lower_inclusive, current_upper, current_upper_inclusive = (
            _constraint_bounds(constraint.value)
        )
        if lower is None or current_lower.compare_precedence(lower) > 0:
            lower, lower_inclusive = current_lower, current_lower_inclusive
        elif current_lower.compare_precedence(lower) == 0:
            lower_inclusive = lower_inclusive and current_lower_inclusive
        if upper is None or current_upper.compare_precedence(upper) < 0:
            upper, upper_inclusive = current_upper, current_upper_inclusive
        elif current_upper.compare_precedence(upper) == 0:
            upper_inclusive = upper_inclusive and current_upper_inclusive
    if lower is None or upper is None:
        return None
    comparison = lower.compare_precedence(upper)
    if comparison > 0 or (
        comparison == 0 and not (lower_inclusive and upper_inclusive)
    ):
        return None
    return DependencyConstraintIntersection(
        None, lower, lower_inclusive, upper, upper_inclusive
    )


def _constraint_bounds(
    value: str,
) -> tuple[SkillVersion, bool, SkillVersion, bool]:
    if value.startswith("^"):
        lower = SkillVersion.parse(value.removeprefix("^"))
        if lower.major > 0:
            upper = SkillVersion(lower.major + 1, 0, 0)
        elif lower.minor > 0:
            upper = SkillVersion(0, lower.minor + 1, 0)
        else:
            upper = SkillVersion(0, 0, lower.patch + 1)
        return lower, True, upper, False
    lower_text, upper_text = value.split(",", 1)
    lower_inclusive = lower_text.startswith(">=")
    upper_inclusive = upper_text.startswith("<=")
    lower = SkillVersion.parse(
        lower_text.removeprefix(">=" if lower_inclusive else ">")
    )
    upper = SkillVersion.parse(
        upper_text.removeprefix("<=" if upper_inclusive else "<")
    )
    return lower, lower_inclusive, upper, upper_inclusive
