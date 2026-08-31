# Insight Runtime

Status: **Implemented / Frozen**.

Insight is the read-only operational-awareness boundary. `InsightRuntime` composes
the system, hardware, disk, process, resource-pressure, model-capability, and
diagnostics runtimes. It observes and explains; it never starts or stops a
process, changes configuration, installs software, downloads a model, or applies
a recommendation.

The canonical structured report contains system, hardware, storage, measured
pressure, registered-model recommendations, evidence-based diagnostics,
provider state, Health/Readiness projections, integration state, and explicit
limitations. The compatibility `/system/insight` projection remains available.

Cross-domain boundary rules:

- Agent Loop receives only `InsightRuntime` and may lower a new decision to
  `record_only` under critical measured pressure.
- Mission Runtime receives only `ResourcePressureRuntime` and may defer dispatch.
- Model Router receives only `ModelCapabilityRuntime` and may select a smaller
  registered model.
- no frozen runtime imports `psutil` or an OS probe.

Provider collections emit bounded completion/failure events containing component,
provider, latency, and error type only. Reports never contain hardware serials,
MAC addresses, environment variables, credentials, private paths, or actual user
and host names.

Persistence is bounded under `DATA_DIR/insight`: snapshots, the latest diagnostic
report, and cache space. Full process lists are deliberately excluded. Snapshot
retention is configured by `config/insight_policy.yaml`.
