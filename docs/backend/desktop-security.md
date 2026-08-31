# Desktop Automation Security

Status: **Implemented / Frozen**.

Desktop actions use the existing `EffectivePolicyRuntime`, `ApprovalManager`,
`AgentAuditRuntime`, `EventBus`, and redaction layer. Policy remains deny by
default. ApprovalManager is consulted for every plan; policy requirements and
high/critical risk create a normal approval request containing only plan ID,
action kinds, and count.

Risk rules prohibit password, credential, secret, MFA, and biometric input.
Lifecycle/global-input actions are high risk. Critical dialogs, administrative
operations, and destructive metadata are critical and cannot run without an
approved request. The domain provides no filesystem formatting, privilege
elevation, MFA confirmation, biometric confirmation, or hidden credential path.

Audit/events contain IDs, action kind, provider, attempts, status, error type,
and verification state. They exclude text values, clipboard content, OCR text,
screenshots, full executable paths, environment variables, tokens, and
credentials.
