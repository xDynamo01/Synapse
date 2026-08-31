# Desktop Automation + Application Control Finalization

Date: 2026-07-13

## Scope

The generic Desktop Automation domain is implemented with separate application,
window, UI automation, input, screen, clipboard, verification, planning, risk,
and orchestration runtimes. Windows, Linux, macOS, OCR, Vision, and input
providers are isolated. Production contains no application-specific behavior,
mock provider, placeholder success, fixed-coordinate selector, or OCR-first path.

## Safety evidence

- Policy is deny-by-default and ApprovalManager is consulted before side effects.
- Authentication secrets are prohibited; all other entered text is transient.
- Preview and dry-run are available for every plan.
- Verification is mandatory after every action; unsafe actions are not retried.
- Rollback is reported and attempted only for supported compensations.
- Full captures, accessibility trees, OCR text, clipboard content, and typed text
  are not persisted by the domain.
- Agent Loop delegates only reversible desktop plans; Mission delegates through
  the Desktop public port.

## Test matrix

The mandatory 20-scenario acceptance suite covers application/window/element
discovery, a complete sequence, focus/provider failure, OCR/Vision fallback,
approval denial, cancellation, clipboard restoration, disappearing targets,
retry, recovery, positive/negative verification, Mission, and Agent Loop.

Provider/API/security tests cover all three native provider parsers, tree shape,
movement/resizing/index changes, dry-run, transient payloads, generic API and
commands, and optional Health/Readiness behavior. Final focused/global, Ruff,
OpenAPI, diff, and forbidden-coupling results are recorded in the backend freeze
baseline after execution.

Final results:

- mandatory acceptance: 20 passed;
- exclusive domain/provider/API/security: 34 passed;
- focused domain plus frozen integrations: 107 passed in 63.51 s;
- global: 972 passed plus 4 subtests in 506.61 s;
- real Windows smoke: 15 windows discovered, accessible tree collected, and
  clipboard readability confirmed without printing content;
- OpenAPI: 425 paths and 471 operations, with no duplicate path/method or
  `operationId`;
- Ruff: repository-wide green;
- `git diff --check`: green, with existing LF-to-CRLF warnings only;
- coupling audit: zero forbidden application names, production mocks,
  placeholders, fixed coordinates, or frontend/Electron changes.
