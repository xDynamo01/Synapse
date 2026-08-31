# Insight + System Runtime Finalization

Date: 2026-07-13

## Scope and architecture

The read-only Insight + System Runtime domain is implemented with seven separate
runtimes and isolated Windows, Linux, and macOS providers. Production contains no
mock provider and no direct hardware access outside `synapse.system_insight.providers`.
Agent Loop, Mission Runtime, and Model Router consume only their documented public
Insight ports.

## Safety and privacy

- no process control, configuration mutation, installation, download, or driver action;
- no serial, MAC, environment, credential, token, command-line, executable-path,
  private-path, host-name, or user-name output;
- bounded process output and snapshot retention; full processes are not persisted;
- optional GPU, driver, sensor, battery, and model resources do not block readiness.

## Acceptance evidence

The mandatory acceptance suite covers CPU-only, AMD ROCm, NVIDIA CUDA, no model,
multiple provider state, recommendation changes after a VRAM drop, Agent Loop
autonomy reduction, Mission deferral, and Model Router fallback to a smaller
registered model.

Validation results:

- mandatory acceptance: 8 tests covering all 9 required scenarios, green;
- focused provider/domain/integration regression: 153 passed in 245.17 s;
- global: 938 passed plus 4 subtests in 700.81 s;
- OpenAPI: 414 paths and 460 operations, with no duplicate path/method or
  `operationId`;
- Ruff: repository-wide green;
- `git diff --check`: green, with pre-existing LF-to-CRLF warnings only.

No frontend/Electron work, commit, push, pull request, or later domain is part of
this finalization.
