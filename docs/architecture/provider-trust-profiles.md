# Provider trust profiles

`ProviderTrustProfile` projects Provider Taxonomy identity into the trust
boundary without taking over provider execution. It declares an explicit
processing boundary, supported/blocked classifications and categories,
retention/training claims, tenant/organization controls, redaction needs,
verification provenance, expiry, revision and checksum.

An endpoint on localhost is not automatically local. Local Ollama and LM
Studio profiles are seeded only by the composition root as declared deployment
profiles. External providers require an active, non-expired profile; provider
configuration alone is never an allow decision.

Claims are not guarantees. The profile's verification level differentiates
provider claim, contractual assertion, verified technical fact and
user-configured assumption.
