# RFC Runtime

An RFC is a human-editable specification before a relevant change. `RFC.md`
contains verifiable sections and `manifest.yaml` contains identity, revision,
status, scope, risk, reviewers, approvals, quality gates, eval references,
criteria, classification and checksum. Every content change creates a new
immutable revision snapshot; status transitions do not silently rewrite the
specified content revision.

States are `draft`, `under_review`, `changes_requested`, `approved`,
`implementing`, `implemented`, `superseded`, `rejected` and `withdrawn`.
Transitions are explicit. Structural validation does not imply approval.

Reviews identify role, actor type, decision and a structured section,
requirement, invariant, criterion, question or risk reference. Ephemeral agents
may comment or request changes but never approve permanently. Critical RFCs
require segregated reviewers and a human/owner/admin approval; an author cannot
approve their own critical revision.

RFCs are normally required for architectural, public contract, persistence,
lifecycle, policy, permission, destructive, removal, relevant Skill/Tool/
Provider and multi-agent flow changes. Typos, non-normative documentation,
additional tests and proven-equivalent internal repairs remain bureaucracy-free.
