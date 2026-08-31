# Architecture Stabilization — Context Fusion Read Ports

Date: 2026-07-14. Backend status remains **NOT READY**.

Only Context Fusion concrete dependencies were inverted. API, Commands, Health,
Readiness, Tools, Providers, Storage, Agent Creator, DataDir maintenance and
unrelated cycles were not changed. The exact matrix, hashes, SCC and ten
controlled pre-change scenarios are in `context-fusion-dependencies-before.json`.

The former 518-line runtime had nine concrete functional-domain imports. Six
small read ports and six bootstrap adapters now form the boundary. The 601-line
runtime has zero concrete functional-domain imports; its growth is the explicit
bounded timeout/correlation runner and is not treated as the success metric.

Controlled snapshots preserve item order, priorities, content, confidence,
provenance, sensitivity, token estimates, budget, omissions, warnings and
normalized trace/time fields. Nonexistent conversation still raises `NotFound`;
other source exceptions still propagate; optional Memory absence remains
nonfatal. The new five-second technical bound prevents indefinite blocking and
copies correlation context.

API, Commands, Health and Readiness tree hashes are byte-identical. OpenAPI is
exactly 425 paths, 471 operations and 100 schemas with SHA-256
`bc0b2a3cab01aa9377bc80b50193089d288edd71901a9f650e3bd02ad48ea72f`.

| Measurement | Before | After |
| --- | ---: | ---: |
| Context Fusion SCC | 26 contexts / 79 edges | 1 / 0 |
| Remaining related SCC | 26 / 79 | 25 / 75 |
| Unrelated SCCs | 4/6 and 2/2 | unchanged |

Validation before the final global run: architecture 47/47 in 14.71 s; focused
Context Fusion/ports/Memory 27/27 in 11.44 s; final port isolation 14/14 in
0.28 s; reader integrations 196/196 in 115.63 s; acceptance 64/64 in 26.30 s.
Twenty real-runtime builds averaged 40.065 ms (36.290–55.291 ms). Final global,
pytest passed 1,040 tests plus 4 subtests in 528.93 s. Ruff and diff checks pass;
complete evidence is in `context-fusion-ports-after-metrics.json`.

Agent and World State remain non-sources. The 25/75 SCC, Tools, Providers,
Storage, Agent Creator and DataDir maintenance remain future work. No SDK,
frontend, commit, push or pull request was created.
