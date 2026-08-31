# Sandbox Operational Admission Policy — Slice 2 audit

## Decision

**COMPLETE / APPROVED**

Bootstrap now owns one deterministic factory for the authorized local Windows admission
policy. The frozen Sandbox contract was not changed and no runtime was composed or
activated by this slice.

## Behavior

The factory requires all eight fact dimensions to be complete, fresh policy/approval
facts, exact approval correspondence, external capability/resource grants and proven
isolation support. It allows only `python`, prohibits wildcards and accepts only
`sandbox-profile:windows-job-contained-v1`. Closed outcome precedence remains frozen.

## Current gates

- focused policy/facts selection: **41 passed**;
- Ruff on changed policy/test files: **passed**;
- Mypy on the policy factory: **passed**;
- diff integrity: **passed**;
- architecture/global gates: deferred to the module final slice.

## Next

Slice 3 adds an inert deferred global runtime slot using this policy and no execution
ports.
