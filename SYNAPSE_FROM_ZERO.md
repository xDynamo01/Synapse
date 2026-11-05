# DEV-0001 — Build and run Synapse from zero

Status: `TARGET_0_3 / NOT YET CLEAN-ROOM VALIDATED`

This is the controlled skeleton for the complete reproduction manual. A command
is marked validated only after an independent clean-environment execution records
an `EVD` document.

## 1. Supported baseline

- Windows edition/build:
- CPU/RAM/GPU/disk minimums:
- Python distribution and exact version:
- Node/npm versions:
- Git/Git LFS requirements:
- Optional model/provider prerequisites:

## 2. Obtain and verify source

- Clone the repository and select the intended release/tag.
- Verify revision, signatures/checksums where available, submodules and LFS.
- Confirm the worktree is clean before configuration.

## 3. Local configuration and secrets

- Copy only documented examples.
- Describe every variable without recording real credentials.
- Store provider credentials through the approved local secret mechanism.

## 4. Backend environment

- Create the Python environment.
- Install locked dependencies.
- Initialize local directories and non-private bootstrap data.
- Run static, architecture and unit gates.

## 5. Frontend environment

- Install the locked Node dependencies.
- Build main/preload/renderer artifacts.
- Run unit and Electron smoke tests.

## 6. Providers, models, database and tools

- Configure each supported provider separately.
- Distinguish discovered, available, selected and operational models.
- Initialize/migrate databases from a documented empty state.
- Register MCP/tools/skills through approved composition roots.

## 7. Integrated startup

- Start services in dependency order.
- Verify backend/frontend handshake and health contributors.
- Exercise one real end-to-end chat/tool flow with receipts.

## 8. Windows packaging

- Produce backend sidecar and desktop package from the clean clone.
- Record artifact hashes and dependency inventory.
- Install/launch the final artifact, not only development output.

## 9. Operational validation

- Restart/recovery and persisted-state checks.
- Provider/tool failure and degraded-mode checks.
- Permission denial, secret redaction and cancellation.
- Resource pressure and single-model residency where applicable.

## 10. Backup, restore and troubleshooting

- Separate Git-restored files from private/local state.
- Document backup format, integrity check and restore drill.
- Provide symptom -> evidence -> diagnosis -> resolution procedures.

## Clean-room validation record

- Revision:
- Environment:
- Validator:
- Evidence IDs:
- Result: `NOT RUN`
- Known blockers:
