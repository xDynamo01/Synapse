# Self-change governance and scoped deterministic eval evidence

Date: 2026-11-22. Platform: Windows workstation. Source tree:
`F:\Projetos\Synapse`, working changes preserved, no commit made.

Charter: `docs/specs/2026-11-06-synapse-0.3-decision-charter.md`.
Scope/obligations/limitations: `docs/guides/local-self-change-and-evals.md`.
Binding decisions: MI-002/003/005/006/007, ME-003/005, SE-002/004/005/006,
PL-001/003/004/006, QA-001/002/003. No claimed charter deviation.

## Executed

`cargo test -p synapse-core --lib self_change::tests -- --test-threads=1`:
**PASS 8/8** (35 unrelated tests filtered in that run).

Covered: independent human code-review gate before separate concrete approval;
publication/rollback of disposable fixture; exact conversation/project/mission/
Swarm/OS-principal binding; role/approval forging; base drift; revocation;
prepared journal surviving interrupted result transaction; partial recovery
requiring fresh consent; replacement inode refused; secret-free diagnostic
events; protected root/ancestor refusal; complete Unicode review pagination.
Positive consent is a private test seam. No product source was self-modified.

`cargo build -p synapse-core --bin synapse-backend`: **PASS** for the artifact
used by the deterministic eval run. This occurred during integration work;
it does not itself certify the later aggregate source artifact.

`py -3.14 tools/readiness/run_evals.py --binary target/debug/synapse-backend.exe --output docs/evidence/backend/2026-11-22-readiness-evals-v1.json`:
**PASS 16/16**, five classes, zero false positives/negatives and zero forbidden
canary disclosures. Machine-readable dataset/binary hashes, labels, decisions,
denominators and measured per-case CLI latency are in the linked JSON report.
No model/provider was used. Binary stability was checked across the entire run.

`py -3.14 -m py_compile tools/readiness/run_evals.py`: **PASS**.

## Remaining integration and acceptance

The parent integration owns the central Core command/dispatch, schema migration
and registration/mission-effect guard hooks. The new
`backend/core/tests/self_change_cli.rs` contains three actual production-CLI
negative/scoping tests, including generic mission approval rejection, canary-free
metadata/events and protected source registration denial. Run these after the
parent hooks are complete; their final result must be added by integration.

Independent source review and the final combined artifact regressions are still
separate acceptance gates. Native modal UX and actual human confirmation were
not automatically exercised. Process/transaction interruption is not evidence
of physical power interruption or a workstation reboot.

These scoped tests do not close all nine readiness groups: full consumer/ACL/
retention/backup security, multi-user authenticated server access, real-model
semantic evals, diverse real project tasks, multi-file/binary self-updates and
installed-package/platform acceptance remain outside these receipts.
