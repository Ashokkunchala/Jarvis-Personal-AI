# Project verification checklist

This checklist separates repository evidence from local/device acceptance. Keep it updated with workflow links and manual test evidence.

## Current verification snapshot

- [x] Main branch and repository structure inspected on 2026-10-26.
- [x] Original main run 40298136690 built the Android debug APK successfully.
- [x] CI test dependency mismatch fixed: development requirements now include pytest-asyncio and pytest-cov.
- [x] Linux laptop-control unit tests now mock OS-specific volume, clipboard and system-status calls instead of depending on runner hardware.
- [x] API security-header middleware is installed; automated API tests and the front-end voice-controls assertions passed in test job 121521090541 / workflow run 40307768473 (commit d284183).
- [x] Clean-room build on 2026-11-10: a fresh Python 3.13 virtual environment installed from `requirements-dev.txt`, `pip check` reported no broken requirements, and all 135 tests passed with 67% coverage. Ruff is clean after the `voice_tools.py` fixes; the idempotent Alembic baseline (`0001_initial`) upgrades and downgrades a fresh SQLite database.
- [x] Local verification on 2026-10-31 after SQLite history/plans and API body-size limits: 127 Python tests passed; Ruff, `compileall`, `git diff --check`, and Node syntax checks for both browser voice scripts passed. Coverage was 63% overall; this is not a claim of complete branch coverage. Tests cover telemetry redaction/retention/persistence, saved-plan authentication/validation/migration/reopen/status/cancel/delete/export/reminders/history, browser controls, and 1 MiB request rejection in both HTTP apps including chunked bodies and security headers. Two warnings remain: Starlette's `httpx` deprecation notice and pytest's inability to write its cache directory.
- [ ] Android build could not be run locally on 2026-10-31: `java`, `gradle`, and `adb` are not available on PATH; rely on the current-branch CI Android job when available, then verify on a physical device.
- [ ] Confirm full CI (Python, lint and Android build) for the current branch and working-tree changes.
- [ ] Install on a clean Windows machine; verify local setup, startup, stop, and recovery.
- [ ] Verify Gemini calls with the owner's real key and check the account's current model/quota availability.
- [ ] Install the latest debug APK on a physical Android 14 device; verify HTTPS chat, master-token pairing, encrypted device-token persistence, revoke/forget behavior, speech input/output, and token persistence after process restart.
- [ ] Verify Android Live Voice microphone permission, one-time ticket connection, audio input/output, interruption, and cleanup on device.
- [ ] Complete threat-model and security review before public deployment.
- [ ] Verify a true end-to-end, low-latency full-duplex voice session on supported hardware. Browser Live Voice is implemented, but provider availability, microphone, playback, interruption, and Android device behavior still need live testing.

## Required release gates

1. All Python tests and lint checks pass in GitHub Actions.
2. Android debug APK builds; physical-device tests are separately recorded.
3. Missing/invalid tokens fail closed for every protected endpoint.
4. Risky laptop/Android actions require explicit approval and have a cancellation path.
5. No real secrets, prompts, screenshots, or personal data appear in commits or logs.
6. Deployment stays local-only until per-device credentials, revocation, rate limits, HTTPS, origin restrictions, monitoring, and backup/restore are in place.
7. Voice access remains user initiated and clearly visible; no hidden recording or claims of unrestricted background listening.
8. Update `CHANGELOG.md` and the feature matrix with evidence before marking a capability complete.

## Safe local verification

Windows PowerShell:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The CI run installs the same test dependencies. Do not expose the local backend publicly during testing.
