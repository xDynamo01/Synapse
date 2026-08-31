# Proactive Behavior

Proactive behavior is opt-in and deny-by-default. The seed configuration uses
`observe`, so a fresh runtime records eligible attention but performs no
proactive side effect.

Modes are:

- `off`: ignore proactive work;
- `observe`: state, attention, decisions, and traces only;
- `suggest`: notification/suggestion only;
- `assist`: execution dispositions require approval;
- `autonomous_limited`: only explicitly allowlisted, governed, reversible,
  risk-bounded work within all operational budgets.

`config/proactive_behavior.yaml` controls allowed dispositions, maximum actions
per hour, per-item cooldown, quiet hours, notification budget, mission
concurrency, and tool risk ceiling. User DND and absence further reduce the
ceiling. No `autonomous_unlimited` mode exists.

The disposition selector consults frozen Platform Governance. Missing or
failed governance never authorizes execution. Critical and irreversible work
requires approval; external communication remains subject to its frozen domain
policy. Observer and suggest modes cannot execute tools.
