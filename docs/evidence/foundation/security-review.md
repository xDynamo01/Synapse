# Foundation security architecture evidence

## Scope and status

Gate 00 Task 5, reviewed 2026-11-09 against source baseline
`009fe94f71b711af3a4cb688d9da6b8cbdfae538`. Inputs are the approved architecture,
ADRs 0001–0003 and the binding
`docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
Outputs: [foundation threat model](../../security/foundation-threat-model.md),
[authority invariants](../../security/authority-invariants.md) and the
PowerShell document validator. Result: documentation **TESTED / PASS** after
the checks below. No product enforcement is VALIDATED or OPERATIONAL here.

## Review method

Consumed the completed independent repository architecture review at revision
009fe94 (106 tracked files), including effective-resource rows, resolved R1–R9
questions and open Q1–Q8 questions. Rechecked material consumer/source anchors
for runtime provisioning/probes, host writer, transport listeners/auth/parser/
journal and child ownership, persistence paths/staging/restore/readback, and
approved product authority/security requirements. Local offline source reading
only; no security scan, service launch, adversarial runtime probe, external
request or production credential use. Source facts and future requirements are
separate; threat hypotheses are not vulnerability findings.

Important limits confirmed:

- gRPC is numeric plaintext loopback with one public synthetic principal and
  effect-free hold; HTTP/WS remains comparison with distinct auth/parser timing.
  No packaged renderer/main or client issuance proof follows from the spike.
  `experiments/transport/server/grpc_server.py:17-58`,
  `experiments/transport/server/http_server.py:8-68`,
  `experiments/transport/server/lifecycle.py:47-107`.
- Journal `--journal` and report `-OutputPath` are caller paths under the
  developer's OS account, not enforced application roots. Harnesses reap owned
  processes; hooks and ignored paths do not enforce tool containment.
  `experiments/transport/server/main.py:14-24`,
  `tools/foundation/collect-host-capabilities.ps1:8-17`,
  `tools/foundation/collect-host-capabilities.ps1:137-145`,
  `experiments/transport/tests/server-harness.ts:25-97`.
- SQLite backup staging/no-clobber/schema/integrity plus test readback are real
  fixture mechanisms. They do not establish cryptographic provenance, owner
  restore authority, platform ACLs, encryption or product key lifecycle.
  `experiments/persistence/storage.py:73-145`,
  `experiments/persistence/tests/test_backup_restore.py:11-57`,
  `docs/adr/0003-foundation-persistence.md:37-81`.

## Validation

Run from repository root with PowerShell 7.6 or later:

```powershell
pwsh -NoProfile -File tools/foundation/test-security-docs.ps1
```

TDD RED: validator existed while all three documents were absent. Exit **1**
listed each missing document and its required sections. GREEN: with the
documents authored, exit **0** validates substantive required sections, exactly
one complete row per nine threat hypotheses, five mandatory extensions, four
residual risks and ten authority invariants, explicit risk-acceptance status,
binding-charter paths and local citation existence/ranges.

The same command also exercises ten mutations entirely in memory: missing
document; empty assets; missing replay scenario; invariant missing enforcement
owner; duplicated owner-approval invariant; missing remote extension; missing
explicit risk acceptance; absent citation source; out-of-range citation; missing
binding charter. Each must produce its specific diagnostic. No source document
is modified by the negative tests. The validator reads local files only.

The check is a document contract gate: it cannot establish semantic correctness
of prose, security of implementation or actual operational controls. Citations
were also manually checked against source consumers; line-range validation
alone is not claim validation. Exact RED/GREEN command receipts, self-review
and commit are recorded in the local Task 5 execution report. Consuming slices
still require independent QA and real composition/negative evidence.

## Residual risks

R-01–R-04 and Q1–Q8 in the model remain **NOT ACCEPTED** and are assigned to
Plan 01/mission authority, persistence/credentials, tool/model/Skill/browser/voice
and remote/migration/release owners. In particular, no expansion of authority
or data egress is accepted here. Any such acceptance must be explicit from the
authenticated human owner and cannot silently amend the charter. Product
capabilities remain BLOCKED at their named prerequisite, including personal
data before at-rest/key design and sensitive boundaries before E-01–E-05 formal
extensions. Windows fixture evidence does not qualify packaging, remote access,
physical Linux/macOS, power interruption or production-scale recovery.

## Decision Charter Compliance

**Charter:** `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
**Binding decisions:** CR-001, CR-004, MI-002–MI-007, SE-001–SE-006,
PL-001–PL-004, QA-001–QA-003.

| Decision | Implementation obligation | Test/evidence owner |
|---|---|---|
| CR-001, CR-004 | New document baseline, synthetic/non-secret evidence only | Source/patch self-review and release hygiene |
| MI-002–MI-007; SE-001–SE-006 | Authority invariants, threats/owners/residuals and later formal models | Ten invariant rows and nine scenario rows; downstream slice tests |
| PL-001–PL-004 | Core/client separation, remote gate and truthful platform scope | Trust boundaries B-08/09/16 and residual R-04; Plan 01/platform |
| QA-001–QA-003 | RED/GREEN, negative cases, exact source and limited claim | Validator command and local Task 5 report; independent controller review |

**Reviewed but not applicable:** CR-002/CR-003 archival/branch mechanics,
PX-001–PX-006, VO-001–VO-006, ME-001–ME-005, SK-001–SK-004, MM-001/MM-002,
SW-001–SW-004 and PL-005 do not receive runtime implementation in this evidence
task; applicable privacy/context/Skill/audio obligations remain in the model
and invariants. **Proposed deviations:** None.
