# Perception + Multimodal + Vision Finalization

## Architecture and production cleanup

- canonical validated `PerceptionSignal` ingestion and durable observations;
- default Voice sink wired to Perception, while optional/failing sinks remain safe;
- explicit local screenshot and uploaded-image paths with bounded retention;
- provider-neutral vision, OCR, camera, and capture protocols;
- temporal multimodal fusion with conservative confidence and provenance;
- Context Fusion bridge based on observations;
- production visual mocks, fake camera, fake detections, and fake confidence removed.

## Inventory matrix

| Component | Responsibility before closure | Production/mock | Input | Output/persistence | Privacy and consumers | Debt closed |
| --- | --- | --- | --- | --- | --- | --- |
| Perception | JSONL signal transport | partial production | audio/vision helper calls | signals/batches | Context Fusion | canonical validation, observations, dedup, conflicts, expiry, cleanup |
| Vision | sessions plus fabricated frames/faces/body | production mock | mock camera call | simulated event only | multimodal sessions | real image validation, provider protocols, no fabricated evidence |
| Capture | absent | absent | none | none | none | explicit MSS screenshot, sources, policy, checksums, bounded raw lifecycle |
| Camera | auto-created mock camera | production mock | mock device | fabricated frame | Vision | optional injected provider, disabled by default, lifecycle/events |
| OCR | no contract | placeholder | none | none | none | optional provider/capability and policy-gated text persistence |
| Multimodal | session event bus | production | channel events | JSONL events | session consumers | temporal observation fusion, provenance, relevance, contradictions |
| Voice bridge | optional external sink | production | voice signals | sink call | Perception optional | default canonical Perception sink; failure remains isolated |
| Context bridge | raw/legacy signal grouping | production | Perception signals | context items | agent context | active structured observations with provenance/validity |

## API matrix

| Operation group | Runtime | Endpoint family | Test | State/classification |
| --- | --- | --- | --- | --- |
| ingest/query signals and observations | Perception | `/api/perception/*` | unit + privacy/restart E2E | implemented; public client |
| conflict and retention administration | Perception | `/api/perception/conflicts`, `/retention*` | unit + restart E2E | implemented; diagnostics/admin |
| providers, capabilities, health, sources | Vision/Capture | `/api/vision/providers`, `/sources` | unit + OpenAPI | implemented; diagnostics |
| uploaded image and screenshot analysis | Vision/Capture | `/api/vision/images/analyze`, `/screenshots` | image/screenshot E2E | implemented; public client |
| result, cancellation, raw deletion | Vision | `/api/vision/results/*`, `/analyses/*`, `/inputs/*` | unit/API | implemented; public/admin |
| camera lifecycle | Vision/CameraProvider | `/api/vision/cameras/*` | controlled provider unit | implemented; administrative/optional |
| fusion/query/context preview | Multimodal | `/api/multimodal/fusions*` | multimodal E2E | implemented; public client |

## Verification

- Required acceptance glob: `6 passed`.
- Focused domain/provider suite: `43 passed`.
- Final bridge/domain regression: `51 passed`.
- Global suite: `974 passed`, `4 subtests passed`, zero failures/skips.
- Ruff: `All checks passed!` repository-wide.
- Diff check: passed; only pre-existing LF/CRLF conversion warnings.
- OpenAPI: `409` paths, `458` operations, no duplicate operation ID, no mock operation.
- Production residue search: no `mock_vision`, `mock_camera`, `vision.mock`,
  mock frame analysis/capture method, fake OCR, simulated detection, or
  automatic/continuous capture implementation in the active domain.

Acceptance uses controlled providers injected exclusively in test code. No
frontend, World State, Agent Loop, Insight, Email, commit, push, PR, or GitHub
mutation was performed.
