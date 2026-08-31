# Desktop Runtime

Status: **Implemented / Frozen**.

`DesktopRuntime` is the orchestration root and does not implement an OS action.
It composes `ApplicationRuntime`, `WindowRuntime`, `UIAutomationRuntime`,
`InputRuntime`, `ScreenRuntime`, `ClipboardRuntime`, `VerificationRuntime`, the
planner, risk analysis, and governance adapter.

Execution order is fixed:

1. create and persist a sanitized semantic plan;
2. produce provider order, expected state, policy decision, and risk preview;
3. return without side effects for dry-run;
4. enforce Policy and consult ApprovalManager;
5. locate the current target again immediately before the action;
6. prefer the native accessibility provider;
7. use OCR, Vision, and element-relative input only as explicit fallbacks;
8. verify current state after every action;
9. retry only idempotent/retry-safe operations;
10. abort and apply only technically available compensations after failure.

Cancellation is durable and checked between steps. Recovery restarts a failed,
rolled-back plan from its first step; transient text must still exist in the same
runtime process. A restart safely refuses a plan whose transient payload no
longer exists.
