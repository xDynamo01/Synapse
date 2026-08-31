# Egress policy and gate

Policy results are `allowed`, `allowed_minimized`, `allowed_redacted`,
`allowed_summary_only`, `approval_required`, `local_only` or `denied`. Deny
always has precedence over provider availability or a lower-level allow.

The deterministic decision considers classification, categories, ownership,
purpose, destination boundary, trust profile, asset/project/RFC constraints,
training-use policy, transformations and approval scope. Secret is external
deny by default; restricted is local-only by default; confidential external
processing in Hybrid Guarded requires minimization, redaction and scoped
approval.

The gate rechecks manifest freshness, payload/provider/destination/purpose,
asset set, trust and approval. Any change invalidates the authorization.
Fallback to another provider must therefore produce a new decision and
manifest.
