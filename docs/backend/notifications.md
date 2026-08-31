# Agent Loop Notifications

The new domain uses a neutral `NotificationSink.notify(Notification)` port.
The contract contains ID, type, title, summary, severity, optional actions and
entity references, expiry, correlation ID, and redacted metadata.

`LocalNotificationSink` adapts this contract to the frozen
`NotificationRuntime`. Its default behavior is durable inbox persistence; it
does not simulate a toast, desktop window, speech, or any frontend behavior.
Future clients consume the existing notification API and the safe agent event
stream.

DND defers non-critical notifications and suggestions. Critical attention is
preserved and approval-gated. The hourly notification budget and cooldown are
configured in `config/proactive_behavior.yaml`.
