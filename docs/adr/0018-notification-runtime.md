# ADR 0018: Notification Runtime

Date: 2026-06-19

## Status

Accepted

## Context

Synapse needs a central notification source before desktop, mobile, voice, or avatar surfaces exist. Runtime modules should not create UI-specific alerts directly. Notifications must be local-first, persistent, observable, and provider-based.

## Decision

Create `synapse.notifications` with:

- `Notification` model
- provider interface
- `LocalNotificationProvider`
- `ConsoleNotificationProvider`
- `NotificationRuntime`

Notifications are persisted under `DATA_DIR/notifications`. The runtime observes EventBus events and creates notifications for approval, communication, scheduler, daemon, agent, tool, and worker events.

Commands:

- `/notifications`
- `/notifications unread`
- `/read-notification <id>`

API:

- `GET /notifications`
- `GET /notifications/unread`
- `GET /notifications/{id}`
- `POST /notifications/{id}/read`
- `DELETE /notifications/{id}`

## Consequences

Notification Runtime becomes the single source of local Synapse notifications. UI, mobile, voice, and avatar surfaces can later consume the same runtime records.

Known gaps:

- no push/mobile/desktop providers
- no notification cleanup execution yet
- no retention policy
- no deduplication or rate limiting
- no user-specific notification preferences
