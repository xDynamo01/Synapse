# Sandbox Operational Admission Policy — Slice 1 audit

## Decision

**COMPLETE / APPROVED**

The user authorized the recommended security-governed Sandbox policy module after the
Final Backend Readiness Campaign identified the missing operational policy as the sole
required-binding blocker. A conservative fail-closed policy can be implemented without
changing the frozen Sandbox contract.

## Scope

- Profile: `security-review`.
- Inspected the admission-policy contract, admission facts, local Sandbox composition,
  Windows driver composition/network capability facts and focused tests.
- No process, network mechanism, secret provider, host feature or persistent runtime was
  activated.
- No source, contract, test baseline or security configuration was changed.

## Authority and ownership

Sandbox owns admission semantics and immutable policy artifacts. Bootstrap may own the
single concrete local policy instance used for composition. The policy decides admission
only: it does not create approvals, authorization, effective grants, materialization or
executability.

## Authorized fail-closed baseline

| Policy field | Value |
| --- | --- |
| format | frozen `sandbox-admission-policy-v1` |
| version | `sandbox-admission-policy:local-windows-v1` |
| all eight fact dimensions | required and `COMPLETE` |
| freshness | required for policy and approval facts |
| mismatch/stale/unavailable/incomplete | frozen closed outcomes |
| approval fact | required |
| external capability grants | required |
| external resource grants | required |
| isolation support | required and proven |
| minimum/allowed profile | `sandbox-profile:windows-job-contained-v1` |
| allowed capabilities | exact `python` only |
| wildcard capabilities | prohibited |

This baseline admits nothing from missing, stale, incomplete, mismatched or unsupported
facts. Admission still does not imply authorization or execution.

## Host limitations preserved

Windows V1 exposes L1 Job Object containment when all authority/fencing/process
dependencies are configured. L2 restricted identity is unavailable. Disabled,
loopback-only and allowlisted network profiles are not enforceable without an external
network mechanism; Job Objects do not isolate networking. Therefore later composition
must not claim real execution or permit process creation from policy presence alone.

## Next

Slice 2 implements only the deterministic bootstrap policy factory and focused tests. It
does not compose or activate the Sandbox runtime.
