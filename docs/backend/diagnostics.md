# Insight Diagnostics

Status: **Implemented / Frozen**.

`DiagnosticsRuntime` creates findings only from collected evidence. Current
objective rules cover high/critical resource pressure, excessive measured swap,
unusually high aggregate Synapse-process memory, and absence of registered
models. Each finding has a stable code, severity, summary, evidence list, and an
optional recommendation.

Diagnostics report limitations independently from findings. Missing optional
hardware is not diagnosed as failure. The canonical insight diagnostic view is
`GET /insight/diagnostics`; the pre-existing `GET /diagnostics` remains the
platform Health diagnostic and was not duplicated. The latest insight diagnostic
snapshot is bounded at `DATA_DIR/insight/diagnostics/latest.yaml`.
