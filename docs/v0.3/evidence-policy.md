# TEST-0001 — Synapse 0.3 evidence policy

## Capability states

| State | Minimum evidence |
|---|---|
| `IMPLEMENTED` | Production code exists, is reachable by a named interface and passes static/local checks. |
| `INTEGRATED` | Real producer, registration/composition root and real consumer are connected through the declared contract. |
| `TESTED` | A reproducible automated or manual test exercised the stated behavior with an observed result. |
| `VALIDATED` | The intended environment, realistic configuration/data and relevant failure/recovery paths were independently checked. |
| `OPERATIONAL` | A supported runtime demonstrated the end-to-end behavior, observability and recovery required for actual use. |

States are cumulative only when every lower layer has evidence. Code presence,
mocks, static analysis, plausible model text and unit tests cannot independently
prove integration or operational readiness.

## Execution results

- `PASS`: executed now and met the stated expected result.
- `FAIL`: executed now and did not meet it.
- `BLOCKED`: execution could not proceed because a named prerequisite or authority
  was unavailable.
- `NOT RUN`: no execution occurred. This is never represented as success.

Historical results are labelled `inherited` and never replace a fresh run required
by the current mission.

## Evidence record

Every real test uses `docs/templates/test-evidence-template.md` and records ID,
requirement, revision, environment, prerequisites, sanitized data/configuration,
exact procedure and commands, expected result, observed result, artifacts,
limitations and execution date.

## Engineering Gate

Applied to each change according to `.agent/QUALITY_GATES.md`:

1. diff and scope review;
2. targeted tests for changed behavior;
3. bounded-context and architecture tests when boundaries are involved;
4. Ruff/Mypy/build/lint as applicable;
5. regression tests proportional to downstream reach;
6. current documentation and reproducible evidence.

Passing this gate proves engineering consistency at the tested layers. It does not
prove that external providers, models, devices or packaged runtimes work.

## Operational Gate

A capability may be `OPERATIONAL` only when all applicable checks pass:

1. the actual packaged or supported entrypoint starts in the intended environment;
2. real registration/composition and real consumers are used;
3. real provider/tool receipts demonstrate requested effects;
4. persisted state survives restart and recovery where required;
5. permissions, denial and redaction paths behave as declared;
6. failure, timeout, cancellation and degraded-mode paths are observed;
7. logs/events/metrics identify the execution without exposing secrets;
8. an independent verifier repeats the procedure from the documented baseline.

## Independent validation protocol

The implementer supplies requirements, revision and procedure. A verifier starts
from a clean clone or explicitly inventoried environment, supplies no unpublished
state, executes the procedure, compares observations to predeclared expectations
and records discrepancies. The verifier does not edit the implementation while
performing the validation.
