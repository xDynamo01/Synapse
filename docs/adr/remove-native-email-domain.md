# Remove the Native Email Domain

Status: Accepted

Date: 2026-07-13

## Decision

O Synapse não mantém integração nativa de e-mail. Aplicativos de e-mail poderão
ser operados futuramente através de automação genérica de aplicações, sujeita a
policy, preview e confirmação.

Generic application automation is not implemented by this decision.

## Rationale

The native domain combined several incomplete approaches—provider stubs,
protocol adapters, provider-specific OAuth, internal drafts, and a bridge—without
a single production contract. Keeping it disabled would preserve dead public
surface, credentials, policy branches, and maintenance cost. The product
therefore removes the domain rather than deprecating or feature-flagging it.

## Removed Surface

- native runtimes, models, providers, adapters, and integration bridge assets;
- Gmail, Microsoft OAuth/Graph-related state, SMTP, and IMAP support;
- account, synchronization, cache, token, and bridge storage paths;
- internal drafts, outbound-send requests, domain events, permissions, policies,
  approval specializations, scheduler jobs, and notification projections;
- API schemas and routes, slash commands, tools, mocks, fixtures, tests, seeds,
  settings, secrets, health/readiness hooks, dependencies, and active domain docs.

## Preserved Components

The generic approval manager, audit and redaction facilities, generic attachment
contracts, tool execution, policy enforcement, notification contracts,
agent-to-agent communication, and external-action confirmation remain in their
domain-neutral namespaces. None depends on the removed domain.

## Post-removal regression matrix

| Removed component | Canonical replacement | Regression status |
| --- | --- | --- |
| Native providers, protocol adapters, account state, and internal drafts (A) | Removed without replacement | Exclusive-reference audit clean; OpenAPI clean |
| Provider-oriented `communication/*` workflows (D) | Conversation for messages; Delegation for work; Mission/Swarm for coordination; Event Stream for events | Canonical A-to-B delegation result returns through Conversation without either removed namespace |
| Mail-specific notification projections (A) | `LocalNotificationSink` backed by `NotificationRuntime` for user attention | Create, persist, inbox, get, acknowledge, dismiss, restart, AttentionItem correlation, redaction, and DND regressions green |
| Mail scheduler job and recurring type (A) | `SchedulerRuntime` generic one-shot, delayed, recurring, mission-dispatch, and agent-loop jobs | Pause/resume/cancel, restart, idempotency, daemon integration, and generic recurring regressions green |
| Mail tools and provider helpers (A) | `ToolRuntime`, discovery, execution router, and MCP bridge | Schema, permission, approval, preview, dry-run, execute, retry/audit paths, MCP, and unrelated internal tools green |
| Draft/send resource types and `send_request` action (A/B) | Generic `ResourceRef` and scoped file/approval/notification resources | Resource-scope and policy regressions green; no remaining consumer required restoration |
| Mail-specific attachments (A) | Conversation attachment contract plus domain-native Vision, Voice, Tool, and Mission references | Conversation attachment validation/persistence and Vision/Voice regressions green |
| Mail-specific risk and approval rules (A) | Effective Policy, `ApprovalManager`, `ApprovalResumeRuntime`, audit, and redaction | Critical/tool approval and policy regressions green; no desktop-automation permission added |

## Impact

Existing callers receive no compatibility endpoint, alias, tombstone, feature
flag, placeholder, or migration shim. Removed configuration and historical data
paths are no longer bootstrapped or loaded automatically. Credentials outside
`DATA_DIR` are not modified by this change.

## Future Strategy

A later, separate architectural decision may introduce provider-neutral desktop
application control. Operating a mail application through that capability would
use the same generic policy, preview, critical confirmation, and audit boundaries
as other external actions; it would not restore a native mail provider domain.

## Compatibility

No backward compatibility is required. Reintroduction requires a new ADR,
contracts, threat model, permissions, and tests; it cannot be inferred from this
repository's historical ADRs or validation reports.
