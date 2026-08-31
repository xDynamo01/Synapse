# Egress manifests and ledger

An EgressManifest binds the decision, requester, project/RFC/mission/task,
provider, destination, processing boundary, purpose, asset references,
classifications, categories, transformations, approval, payload checksum,
size/token estimate, expiry, revision and checksum. It stores no secret and no
full payload.

The ledger is append-only/semantically immutable. Attempts, previews and
results are separate records; completed operations are idempotent and
corrections require related new records. It answers what category and
classification left, for which destination and purpose, under which approval,
and what result reference returned, without retaining the transmitted body.

Storage Primitives provide atomic writes, locks, revisions, migration and
recovery. Generic cleanup does not own ledger retention.
