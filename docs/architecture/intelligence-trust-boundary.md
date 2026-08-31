# Intelligence Trust Boundary

The Intelligence Trust Boundary is the canonical control plane for content
egress. It records InformationAssets, evaluates destination-specific policy,
minimizes context, verifies supported redaction, binds scoped approvals,
creates manifests and appends immutable ledger records. It never performs the
transport itself.

Consumers import `intelligence_boundary.contracts` and neutral models.
Adapters and Storage bindings live in bootstrap. Model Router and Tool Runtime
call `EgressGatePort` before provider/handler execution; external MCP inherits
the Tool gate. Current Speech and Vision adapters are local and contain no
external transport.

The boundary controls what Synapse sends. It cannot technically guarantee how
an external provider stores, trains on, discloses or deletes content after
receipt. Provider claims, contractual assertions, verified facts and
user-configured assumptions therefore remain distinct provenance.

Known limitation: arbitrary upload or form submission mediated by Desktop
Automation inside a third-party UI cannot be comprehensively intercepted in
this phase. Health reports that path as unguarded instead of claiming complete
coverage.
