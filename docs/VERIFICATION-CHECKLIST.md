# Project verification checklist

This checklist separates repository evidence from local/device acceptance. Keep it updated with links to the workflow run and manual test evidence.

## Current verification snapshot

- [x] Main branch and repository structure inspected on 2026-10-26.
- [x] Android debug APK job passed on workflow run 40298136690.
- [ ] Python tests passed: run 40298136690 failed before collecting tests because pytest configuration requests coverage flags but CI did not install `pytest-cov`.
- [ ] Run the Python test suite after correcting the CI dependency.
- [ ] Install on a clean Windows 11 machine; verify local setup, startup, shutdown, and uninstall.
- [ ] Verify Gemini API calls with a real key and document model/quota requirements.
- [ ] Install the debug APK on a physical Android 14 device; verify HTTPS chat, speech input/output, and token persistence after process restart.
- [ ] Complete threat-model and security review before any public deployment.

## Required release gates

1. All Python tests pass in GitHub Actions.
2. Android debug APK builds; physical-device tests are separately recorded.
3. Missing/invalid tokens fail closed for every protected endpoint.
4. Risky laptop/Android actions require explicit approval and have a cancellation path.
5. No real secrets, prompts, screenshots, or personal data appear in commits or logs.
6. Deployment stays local-only until per-device credentials, revocation, rate limits, HTTPS, origin restrictions, monitoring, and backup/restore are in place.
7. Update `CHANGELOG.md` and the feature matrix with evidence before marking a capability complete.

## Safe local verification

Windows PowerShell:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The CI run must install the same development extras as the local verification command. Do not expose the local backend publicly during testing.
