# Intelligence Trust Boundary finalization

Date: **2026-07-15**

## Result

The canonical Intelligence Trust Boundary is implemented outside the global
SCC. It includes InformationAssets, classification/ownership/categories,
processing purposes and boundaries, trust profiles, deterministic policy,
minimization, verified redaction plans, manifests, scoped approvals, derived
provenance, training-use restrictions, an immutable ledger and four operating
profiles.

Model Router and Tool Runtime call the gate before transport. External MCP is
declared `external_mcp` and passes through Tool Runtime. Production API and
Commands no longer call LM Studio chat directly. Current Speech/Vision
adapters are local-only and architecture guardrails reject network transport
there. Project/RFC and Skill/Mission/ephemeral contracts preserve more
restrictive egress constraints; ephemeral approval is denied.

## Metrics

| Measure | Before | After |
| --- | ---: | ---: |
| Bounded contexts | 71 | 72 |
| Governed edges | 257 | 261 |
| Global SCC | 13 / 35 | 13 / 35 |
| Exact-module SCCs | 0 | 0 |
| Canonical gated path families | 0 | model + tool/MCP |
| Seeded explicitly local trust profiles | 0 | 4 |
| Known unguarded path families | 3 | 1 |
| Commands (canonical / registered names) | 394 / 418 | 410 / 434 |
| Health components | 34 | 35 |
| OpenAPI paths / operations / schemas | 479 / 532 / 121 | 494 / 550 / 128 |

Runtime counts for assets, decisions, manifests, minimizations, blocked bytes,
approvals and ledger records are exposed by Health/API and intentionally vary
with workload. No claim of full protection is made while the UI-mediated
Desktop Automation upload path remains unguarded.

## Validation

- functional runtime plus eight required acceptance scenarios: 20 passed;
- architecture suite: 113 passed;
- boundary functional/API/Commands plus acceptance suite: 21 passed;
- LM Studio/MCP focused regression: 21 passed;
- Providers/Models/Tools/MCP/Voice/Vision/Speech regression: 190 passed;
- Skills/Project/Missions/Agents regression: 123 passed;
- global pytest: 1,208 passed / 2 skipped in 851.42 s;
- Ruff: green;
- `git diff --check`: green; working-copy LF/CRLF warnings only;
- OpenAPI operation IDs: 550 unique of 550.
- OpenAPI canonical SHA-256:
  `ffa17fa6583a3ca055f17157556192655973fb6981ed9b55446df56e3f04fa13`.

## Limits and exclusions

The boundary controls Synapse egress, not a third party after receipt. It does
not inspect third-party traffic, promise provider retention/training behavior,
intercept every UI upload, implement DLP/DRM/VPN/firewall/custom encryption,
or store secrets in manifests. Private Evals, Skills Self-Evolution, training,
Repository/Git Runtime, SDK, frontend and Electron were not implemented.

No commit, push or pull request was created. Backend remains **NOT READY**.
