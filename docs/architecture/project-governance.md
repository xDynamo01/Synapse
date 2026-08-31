# Project Governance

Project/RFC classification, allowed provider profiles, external-processing and
training-use fields are consumed as constraints by the Intelligence Trust
Boundary. RFCs and evidence inherit project/source sensitivity and may narrow,
never widen, superior policy. Implementation bindings preserve the constraint
references across Mission, Skill and ephemeral-agent execution.

Project Governance is the canonical technical identity and context authority
for a managed project. A `ProjectManifest` owns project lifecycle, safe opaque
or relative root reference, policy references, provider constraints, Skills and
Memory scope, classification, ownership, revision and checksum.

`ProjectRegistry` registers, reads, updates, pauses/reactivates through explicit
status changes and archives projects. It neither executes code nor opens Git.
Public contracts never expose an absolute path. Bootstrap resolves
`root_reference` below the authorized project root.

Human-editable documents live below `<project>/.synapse/`. Operational indexes
use Storage Primitives with atomic writes, locks, revision checks, migrations
and recovery. Project context contains bounded metadata summaries and
provenance; it never loads the complete project or assembles a prompt.

Project status is `active`, `paused`, `archived`, `unavailable` or
`misconfigured`. Unavailable governance degrades project coding workflows but
does not stop unrelated backend activity. Git, IDE, frontend, SDK and Coding
Session Runtime are not dependencies.
