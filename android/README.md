# Native Android application

The native Kotlin + Jetpack Compose app currently supports:
- HTTPS health check to a user-configured backend.
- Android Keystore AES-GCM encrypted bearer-token storage with a clear-token control.
- Android Keystore AES-GCM encrypted backend URL storage for opt-in background reminder polling.
- Initial authenticated Gemini chat over HTTPS.
- Explicit microphone permission request and tap-to-speak speech recognition (the transcript is shown for review before sending).
- User-started full-duplex Gemini Live audio over the authenticated, short-lived-ticket WebSocket bridge, with visible start, interrupt, and stop controls. The microphone session runs only while the app is visible.
- Spoken assistant replies using Android's installed text-to-speech voice.
- Language selection cycling through adaptive/auto, Indian English, and Telugu.
- Quick shortcuts to Android device, Wi-Fi, Bluetooth, and JARVIS app-permission settings; supported voice transcripts can be reviewed and explicitly confirmed before opening a system screen.
- Authenticated reminder creation and reminder-list refresh through the backend.
- Reminder completion and daily/weekly/monthly recurrence through the backend.
- Opt-in WorkManager reminder polling with Android notification permission. Delivery is best-effort and may be delayed by at least 15 minutes or by unavailable network.
- Master-token-backed device pairing. The master token is sent only over HTTPS and never stored; the issued device token, backend URL, and device ID are encrypted with Android Keystore.
- Confirmed device revocation from the app using the master token. Local “Forget device token” clears this phone only; it does not revoke the backend credential.
- Cleartext HTTP disabled; there is no always-on microphone or guaranteed auto-start after reboot.

The current Android changes still need a CI build and physical-device tests. Memory editing, workout tracking, and background data sync are not implemented in the Android app yet.

## Build

Install Android Studio with Android SDK 35 and JDK 17, then open the `android/` directory as a project and let Gradle sync. GitHub Actions builds the debug APK with Gradle 8.9 and uploads it as the `jarvis-android-debug-apk` workflow artifact.

To build locally, use Android Studio's Build menu or from a terminal with Gradle and Android SDK configured:

```sh
cd android
gradle assembleDebug
```

The expected APK path after a successful build is `app/build/outputs/apk/debug/app-debug.apk`. A CI build does not prove that the app has been installed on your phone or that your backend is reachable from it. Android 14 restricts starting microphone foreground services from boot; launch JARVIS yourself and tap Speak to start microphone use. The Windows one-file installer does not install the Android APK.

## Connect your phone safely

1. Start the enhanced backend with `jarvis serve` on a machine reachable by the phone over a private network or a secured HTTPS host. Its device-management endpoints are part of this CLI backend.
2. The app accepts only an `https://` endpoint. `http://127.0.0.1:8000` on the phone points to the phone itself, not your laptop.
3. For a per-device credential, enter a descriptive device name and the backend's master `JARVIS_API_TOKEN` in the pairing section, then tap **Pair device**. The master token is used for this request and cleared from the form; the issued per-device token is encrypted with Android Keystore. Manual token entry remains available for backends without the device-management endpoints.
4. Tap **Connect securely**, select your reply language, then type a message and tap **Send**.
5. Tap **Speak to JARVIS** for one-utterance speech recognition; the transcript is displayed for review before sending. Speech recognition may rely on the Android speech service and its availability/network behavior.
6. Tap **Start Live Voice** for full-duplex audio. The app asks for microphone permission when you start; use **Interrupt JARVIS** or **Stop Live Voice** to control the session. Live audio is sent to the configured Gemini service.
7. To receive due reminders, tap **Enable Android notifications** and grant notification permission. WorkManager checks about every 15 minutes when network access is available; this is not an exact alarm.
8. For spoken chat replies, the app uses the phone's installed TTS voice. Telugu voice quality depends on installed system language data.
9. To revoke this paired device, re-enter the backend master token, tap **Revoke paired device**, and confirm. **Forget device token** clears local credentials only; it does not revoke the backend token.

## Security and limitations

- Cleartext traffic is disabled. Never send the bearer token over plain HTTP.
- Pairing uses the shared master token to issue a per-device bearer token. Protect the master token and use it only over HTTPS. The app can revoke its paired token after an explicit confirmation; local “Forget device token” does not revoke it. Token rotation, device-flow verification, and production authorization remain required before cloud deployment.
- Android background execution is restricted. No hidden or always-on listening is implemented; future background routines should use WorkManager or properly disclosed foreground services only where appropriate.
- The backend must remain local/private until authentication, TLS, rate limiting, and production security are completed.
