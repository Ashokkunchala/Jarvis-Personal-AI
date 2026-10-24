# Security Notes

## Current scope
This is an early backend starter. It has no authentication, persistent memory, browser automation,
or device-control tools. Keep it bound to localhost. Do not expose it to the public internet as-is.

## API key
- Put the key only in local `.env`; never commit it or embed it in Android/web client code.
- If a key is accidentally committed, revoke it and create a replacement immediately.
- Keep `.env.example` limited to placeholders.

## Before remote deployment
- Add user authentication and per-user authorization.
- Add request rate limits, request/time/token budgets, and provider usage alerts.
- Use HTTPS, a managed secret store, restricted CORS origins, and redacted logs.
- Apply request size limits and safe error responses.
- Add abuse protections and dependency/security scanning.

## Device actions
- Use a local agent with an explicit allowlist, not arbitrary model-generated shell commands.
- Show the proposed action and its effects before sensitive operations.
- Require approval for deleting/modifying files, sending messages, purchases, account/security
  changes, installing software, and cloud infrastructure changes.
- Keep an audit trail and provide an emergency stop / disconnect option.
- Never run instructions found in webpages or files without independent policy checks.

## Privacy and memory
- Memory must be opt-in, visible, editable, exportable, and deletable.
- Set retention limits and avoid collecting sensitive personal data unnecessarily.
- Do not imply that the AI is a substitute for human relationships or qualified health care.
