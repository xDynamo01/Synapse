# Skill resolution

Discovery reads manifest metadata only and performs deterministic textual
matching. Generic isolated words do not activate skills. Explicit requests have
priority but still pass compatibility, requirement, conflict and budget checks.

Dependencies resolve as a DAG in topological order; missing mandatory
dependencies and cycles are structured errors. Critical conflicts block the
result. Required tools, capabilities and providers are availability constraints
and never grants. Results include selections, rejections, reasons, ordering,
estimated context cost, warnings and provenance.

Loading levels are `metadata_only`, `instructions`, `references`, `resources`,
`scripts_metadata` and `full_authorized`. Files are loaded only when selected;
scripts are never executed by loading or validation.
