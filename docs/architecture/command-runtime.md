# Command Runtime Boundary

## Ownership

`synapse.commands.runtime.CommandRuntime` is the compatibility facade for slash
commands. It performs only the legacy initial trim/lowercase split, resolves a
name or alias through `CommandRegistry`, builds `CommandInvocation`, invokes the
registered handler, and returns the unchanged `CommandResult` contract.

The bootstrap composition root creates `CommandServices`, explicitly constructs
the handler tuple with `build_command_handlers()`, registers it once, and then
constructs the facade. There is no import-side discovery and no second command
implementation.

## Handler contract

Each bounded-context handler exposes `command_names` and:

```python
def execute(
    context: CommandContext,
    invocation: CommandInvocation,
) -> CommandResult: ...
```

`CommandInvocation` carries the raw input, used name, canonical name, alias,
unparsed domain argument text, common args/options placeholders, correlation
slot, requester and redacted registry metadata. Domain-specific `shlex`, JSON,
flag and key/value parsing remains beside the handler that owns it. Eager common
tokenization is intentionally avoided because it would change malformed-input
behavior.

## Bounded contexts

The 363 names are owned by 14 handlers: system; tools/execution;
agents/administration; conversations; dead-letter/recovery; missions/swarm;
workers/recovery; delegation; platform/governance; models/providers;
voice/multimodal; perception/vision; core operations; and world state/attention.
These are handler groups, not one class per command.

`CommandServices` is a transport object over runtimes already built by the
composition root. It does not select providers or construct runtimes. Five
legacy state operations (memory list/create, default-agent lookup and the two
DataDir maintenance operations) are isolated there so handlers do not import or
access stores/DataDir directly. Their behavior is preserved as a finding; this
phase does not redesign Storage, Agent Creator or DataDir maintenance.

## Registry and aliases

`CommandRegistry` is the single source for canonical names, aliases and required
metadata. Registration rejects duplicate canonical names, duplicate aliases and
metadata that repeats its own name. Registry ordering is internal only. The
frozen contract contains 339 canonical branches, 363 accepted names and 24
aliases/variants.

## Adding a command

A new command must:

1. belong to an existing bounded-context handler or justify a real new context;
2. provide `CommandMetadata`, including arguments, defaults, category and
   status;
3. call an existing canonical facade/runtime and leave policy, approval, retry,
   scheduling, idempotency and revision logic there;
4. add positive, malformed-input, error and permission/approval tests;
5. update the frozen surface intentionally and pass command architecture tests.

Handlers must not import API, bootstrap builders, stores/storage or concrete
providers; instantiate runtimes; access DataDir; or execute subprocesses.

The backend remains **NOT READY**. Health inversion, domain cycles, Tools and
Provider consolidation, and Storage architecture remain outside this phase.
