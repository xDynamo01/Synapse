# Window Runtime

Status: **Implemented / Frozen**.

`WindowRuntime` lists and resolves windows through the active native provider.
The model contains a stable provider window ID, application ID, PID, bounded
title, state, foreground flag, monitor/workspace when supported, and current
bounds. Focus, minimize, restore, maximize, and close are provider operations
invoked only by an authorized Desktop plan.

Selectors are re-resolved after movement, resizing, workspace changes, and
element reordering. Focus and state changes are verified against a new window
snapshot. A closed or missing window aborts the sequence; execution never
continues against a stale handle.
