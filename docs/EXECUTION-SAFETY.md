# Local execution safety

The shared `ToolRegistry.execute` path now uses a persistent SQLite safety store.
The brain, CLI and TUI calls that use this registry inherit the checks. This is
not an operating-system sandbox and does not cover code that bypasses the registry.

## What it enforces

- MEDIUM and HIGH tools always need the existing trusted confirmation callback.
  Global `auto_approve` cannot bypass that check, nor an explicit confirmation flag.
- An approval is bound to the tool name, a canonical hash of its exact arguments,
  and a fresh invocation ID. It expires 120 seconds after the prompt starts.
- Approved records are atomically consumed once. Replays, expired approvals,
  different arguments and different invocation IDs fail closed.
- Execution arguments are copied before waiting. A UI callback cannot change the
  arguments after the user reviews them. Only the literal boolean `True` approves.
- A persistent emergency stop blocks new LOW, MEDIUM and HIGH registry actions.
  It is checked before the prompt and again after confirmation. SAFE reads remain
  available. An unavailable safety store blocks execution instead of bypassing it.
- The new audit table records timestamps, tool names and fixed outcomes, never
  argument values, outputs or exception text. This does not change legacy logging
  elsewhere in the application.

## Operator controls

Run these locally from the installed project environment:

```console
python -m jarvis.security status
python -m jarvis.security stop
python -m jarvis.security audit
python -m jarvis.security resume
```

`resume` is deliberately not a model-callable tool. It is an operator recovery
command. The database defaults to `~/.jarvis/security.db`; set
`JARVIS_SECURITY_DB` to use another local path. New database files are created
with owner-only permissions on POSIX; Windows inherits the user's directory ACLs.
Keep that directory private and writable only by the operating user.

## Limits

The stop gates dispatch, not already-running processes. It cannot undo or kill
an action already started, and it is not a process-isolation or malware defense.
Tools must be correctly classified by risk. Local programs with the same user's
file access can modify the database; this is not remote multi-user authorization.
Approvals bind to an invocation, not a separately authenticated remote actor or
device. Remote role/device authorization and versioned approval APIs are future
work. Existing UI "always allow" callbacks must not be mistaken for a new remote
permission system. No cloud credentials, paid services or deployment are needed.

## Verification

`tests/test_execution_security.py` covers single use, tool/argument/invocation
binding, approval expiry, concurrent replay, rejection, missing decisions,
emergency stop before and during approval, argument substitution, global bypass,
MEDIUM tools missing a flag, malformed truthy approvals, unavailable storage,
redacted audit and audit failure after a completed action. Existing registry,
brain, orchestrator and file-preview regression tests also run unchanged.
