# Foundation Hardening

DATA_DIR resolution rejects traversal and symlink escapes. Structured YAML/JSON
writes use a same-directory temporary file plus atomic replace and always clean
temporary artifacts. YAML uses safe loading. Corrupt configuration is reported
by diagnostics; raw parser errors are mapped at API/command boundaries.

Foundation diagnostics validate writability, configuration parsing, and escaped
symlinks without returning absolute paths. Temporary cleanup is age-bounded and
idempotent. Telemetry redaction prevents secrets and sensitive content from
entering operational logs. Existing migration, scheduler lock, shutdown, and
provider subprocess tests remain the authoritative specialized checks.

Real limitations: filesystem permission enforcement is OS-dependent; atomic
replace durability depends on the host filesystem; secret storage and local API
authentication remain deployment concerns and are not simulated as ready.
