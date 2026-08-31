# Project Governance + RFC finalization

Date: **2026-07-15**

## Result

Project Governance + RFC Runtime is implemented as a bounded context outside
the global SCC. It provides canonical projects, RFC packages and revisions,
structured review, finite clarification, change classification, RFC Gate,
Implementation Plans, ADR metadata, Evidence, acceptance criteria, quality
gate references, observability, restart and controlled delivery surfaces.

## Architecture and integrations

Consumers import contracts/models only. Bootstrap owns Storage, document and
Tool adapters. Context/Primary consume budgeted summaries; Skills consumes
project/RFC metadata; Missions validate immutable bindings; Swarm propagates
bindings to ephemeral specifications. Ephemeral approval is prohibited.

The graph advances intentionally from 70/252 to 71 bounded contexts / 257
governed edges. The single global SCC remains exactly 13 contexts / 35 internal
edges and the exact Python-module graph remains acyclic.

## Controlled surfaces

The API adds 19 paths / 24 operations, producing 479 paths / 532 unique
operation IDs / 121 schemas. Commands adds 22 canonical names, producing 394
canonical commands / 418 registered names. Health adds one optional real
contributor, producing 34 components. No force approval, direct implemented,
gate bypass or arbitrary project file writer exists.

## Validation

- functional Project/RFC and acceptance suite: 15 passed;
- required acceptance scenarios: 8 passed;
- architecture suite: 103 passed;
- global pytest: 1,177 passed / 2 skipped in 821.28 s;
- Ruff: green;
- `git diff --check`: green; working-copy LF/CRLF warnings only;
- OpenAPI canonical SHA-256:
  `4b47a98d640026e1b0facb915138863cae339365ee3b9abe54b3b9be4044bf2e`.

## Explicit exclusions

No Skills Self-Evolution, unrestricted RFC generation, automatic critical
approval, code editing, Repository/Git Runtime, Coding Session Runtime, Private
Evals Runtime, Intelligence Vault, SDK, frontend or Electron work was added.
No commit, push or pull request was created. The backend remains **NOT READY**.
