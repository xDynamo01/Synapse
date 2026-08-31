# Verification Runtime

Status: **Implemented / Frozen**.

Every `AutomationAction` has a `VerificationSpec`. Supported evidence includes
application running state, window existence/foreground/state, accessible element
existence/focus/value/selection/expand/toggle state, clipboard digest, and an
explicit provider result. Verification always re-queries a public runtime; it
does not trust the action return alone unless the plan explicitly requests that
provider-result check.

Failure stops the sequence. Retry is limited to focus/state, value assignment,
bounded input, and clipboard operations. Lifecycle launch/close and arbitrary
Invoke are not repeated blindly. Verification output redacts accessible text
values while retaining length and digest evidence.
