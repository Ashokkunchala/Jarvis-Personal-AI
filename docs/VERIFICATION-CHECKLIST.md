# Project verification checklist

This checklist separates repository evidence from local/device acceptance. Keep it updated with workflow links and manual test evidence.

## Current verification snapshot

- [x] Main branch and repository structure inspected on 2026-10-26.
- [x] Android debug APK job passed on main workflow run 40298136690.
- [x] Root cause of the previous Python CI failure identified: pytest config enables coverage flags, but CI did not install `pytest-cov`.
- [x] CI installation updated to install `requirements-dev.txt` plus `pytest-cov`; no package build is required for this repository's flat multi-package layout.
- [ ] Latest Python tests and lint must pass in the current pull request workflow.
- [ ] Install on a clean Windows machine; verify local setup, startup, stop, and recovery.
- [ ] Verify Gemini calls with the owner's real key and check the account's current model/quota availability.
- [ ] Install the debug APK on a physical Android 14 device; verify HTTPS chat, speech input/output, and token persistence after process restart.
- [ ] Complete threat-model and security review before public deployment.
- [ ] Implement and verify a true end-to-end, low-latency full-duplex voice session. The current voice UI is transcript-first browser recognition plus local TTS; it is not full-duplex voice.

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
python -m pip install -r requirements-dev.txt pytest-cov
python -m pytest -q
```

The CI run installs the same test dependencies. Do not expose the local backend publicly during testing.
