# Information classification

Canonical levels, from least to most restrictive, are `public`, `internal`,
`confidential`, `restricted` and `secret`. Ownership is separate and uses
user, project, workspace, organization, temporary-agent, temporary-mission,
provider-derived or consent-shared identities.

Categories are validated namespaced strings such as `project.rfc`,
`source_code.private`, `memory.user`, `tool.input`, `media.audio` and
`provider.output`; file extension alone never assigns a category. Records
without historical metadata use a conservative internal/unknown marker until
administrative review.

Derived assets inherit the most restrictive source classification. A
downgrade requires justification, a scoped approval, verified redaction and a
ledger record. Transformation alone never silently lowers classification.
