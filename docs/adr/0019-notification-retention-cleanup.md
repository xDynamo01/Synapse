# ADR 0019: Notification Retention and Cleanup

Date: 2026-06-19

## Status

Accepted

## Context

Notification Runtime persists every notification locally. In homelab or daemon mode, the notification directory can grow indefinitely unless retention is part of the runtime foundation.

## Decision

Add `config/notification_policy.yaml` and `NotificationRuntime.cleanup_notifications()`.

Policy fields:

- `retention_days`
- `max_total_notifications`
- `preserve_unread`
- `preserve_critical`

Cleanup emits:

- `notification.cleanup_started`
- `notification.cleanup_completed`
- `notification.cleanup_failed`

Cleanup is exposed through:

- command `/notifications cleanup`
- API `POST /notifications/cleanup`
- scheduler job type `notification_cleanup`
- daemon execution through scheduler cycles

## Consequences

Notification cleanup remains local-first and runtime-owned. Unread and critical notifications are preserved by default. External providers, native push, and UI notification handling remain out of scope.

Known gaps:

- no automatic cleanup schedule is configured by default
- no deduplication or rate limiting
- no user-specific routing or retention preferences
- no external notification providers
