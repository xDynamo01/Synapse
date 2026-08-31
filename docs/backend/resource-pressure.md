# Resource Pressure

Status: **Implemented / Frozen**.

`ResourcePressureRuntime` calculates normalized memory, VRAM, CPU, and disk
ratios from `HardwareRuntime` and `DiskRuntime` snapshots. The overall level is
the highest measured level; unavailable optional metrics remain `unknown`.

Default thresholds are 70% moderate, 85% high, and 95% critical. Valid overrides
live in `DATA_DIR/config/insight_policy.yaml`. High pressure is advisory. Critical
measured saturation is insufficient capacity and can:

- cap a new Agent Loop decision at `record_only`;
- defer an explicitly capacity-guarded Mission dispatch without mutating its
  plan or task state;
- produce evidence-backed diagnostics and load-reduction recommendations.

Every capacity decision includes the exact observed ratios. The runtime has no
side effects and does not reserve, release, throttle, or kill resources.
