# UI Automation Runtime

Status: **Implemented / Frozen**.

UI Automation uses semantic selectors: AutomationId, role, control type, name,
description, value, window identity, and optional ancestry. It never identifies
a target by list index, fixed pixel, theme, color, locale, resolution, or scale.
Window and element bounds are current evidence used only by the final input
fallback.

The accessible tree models Invoke, Value, Selection, Expand/Collapse, Toggle,
Range, Scroll, Text, Grid/Table, List, Tree, Document, menus, tabs, toolbars,
status bars, dialogs, and windows when the OS exposes them. Tree responses are
bounded. Element values are replaced in public responses by length and SHA-256;
the raw value is used transiently only for verification.

Provider priority is native accessibility, OCR, Vision, then input. If an
accessible match exists, OCR and Vision are not called. A semantic action failure
may move to a configured fallback only when the plan permits it.
