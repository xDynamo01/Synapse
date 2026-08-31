# ADR 0116: Remove Agent Templates

Status: accepted

## Context

Synapse briefly introduced a catalog of prefabricated agent definitions. That
direction conflicts with the product's central requirement: the user controls
every agent's identity, personality, role, model, memory, tools, permissions,
delegation authority, and lifecycle.

The product has not been released, so retaining compatibility endpoints,
deprecation responses, seed catalogs, or dormant domain code would add
complexity without protecting a public contract.

## Decision

Synapse does not offer prefabricated agents. Every agent is created explicitly
by the user or by an authorized operation through the same
`AgentProvisioningRuntime` contract.

The former template runtime, models, seeds, routes, commands, events, tests,
health/readiness fields, and exclusive documentation are removed completely.
There is no deprecated compatibility surface.

Provisioning remains and owns:

- normalized custom configuration;
- preview and dry-run;
- risk-based approval bound to a configuration hash;
- staging, atomic replacement, and rollback;
- registry and identity validation;
- structured errors, events, and audit;
- create, update, validate, activate, deactivate, archive, restore, and delete.

## Consequences

- The client must expose explicit agent authoring rather than a catalog.
- Automated agent creation uses the same contract and authority checks as user
  creation.
- Approval is derived from requested capabilities, tools, permissions,
  autonomy, and delegation, never from an origin label.
- Changing normalized configuration invalidates the previous approval binding.
- Archive remains reversible; permanent deletion has separate confirmation and
  dependency checks.

## Non-goals

- no marketplace or hidden starter agents;
- no inheritance or override graph;
- no compatibility response for removed endpoints;
- no unrestricted model-driven agent creation.
