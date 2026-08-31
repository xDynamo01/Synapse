# Application Control

Status: **Implemented / Frozen**.

Desktop Automation is a generic execution layer over applications, windows,
accessible elements, input fallbacks, visual evidence, and verified actions. It
contains no application-specific adapter, selector, command, endpoint, or policy.

`ApplicationRuntime` lists running application instances from the platform
provider. Its public projection contains PID, sanitized executable basename,
state, foreground state, and window count; private executable paths and process
arguments are not collected. Application launch accepts only a command or
application name, never a private path.

Every mutation belongs to a persisted `AutomationPlan`. Plans are previewable and
support dry-run. Execution evaluates existing Policy, risk, Approval, Audit, and
redaction ports before the first side effect, then verifies every action before
advancing. A plan never records typed text, clipboard content, raw OCR, screen
captures, accessibility trees, credentials, or private paths.
