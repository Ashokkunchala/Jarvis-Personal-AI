# Continuous Improvement

JARVIS should improve through a controlled engineering loop, not by silently rewriting production code.

## Feedback loop
1. The user explicitly reports a problem or approves a suggested improvement.
2. JARVIS turns the feedback into a specific issue with acceptance criteria.
3. Code changes happen in a separate development branch.
4. Unit tests, integration tests, security checks, and cost checks run.
5. The user reviews the diff and approves sensitive or behavior-changing updates.
6. A tested release is documented in the changelog and can be rolled back.

## What can improve automatically later
- Identify repeated unanswered questions or errors, with opt-in analytics.
- Suggest documentation, prompt, and test improvements.
- Open a draft pull request rather than directly rewriting the main branch.
- Check dependencies and tests on a schedule.
- Compare model versions against a curated regression test set before recommending an update.

## What must not happen silently
- Upload private conversations or personal memory to train a model.
- change permissions, access controls, or safety rules.
- install software, run arbitrary shell commands, send messages, spend money, or alter cloud infrastructure.
- publish personal data or deploy untested code.

## Quality gates for every change
- Reproducible tests pass.
- No secrets or private user data in diffs/logs.
- Permissions remain least-privilege.
- User-facing documentation and changelog are updated.
- Model/API usage impact is understood.
- Rollback instructions exist for production changes.
