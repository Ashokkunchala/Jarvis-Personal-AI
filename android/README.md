# Native Android application

The native Kotlin + Jetpack Compose app currently supports:
- HTTPS health check to a user-configured backend.
- Android Keystore AES-GCM encrypted bearer-token storage with a clear-token control.
- Initial authenticated Gemini chat over HTTPS.
- Explicit microphone permission request and tap-to-speak speech recognition (the transcript is shown for review before sending).
- Spoken assistant replies using Android's installed text-to-speech voice.
- Language selection cycling through adaptive/auto, Indian English, and Telugu.
- Quick shortcuts to Android device, Wi-Fi, Bluetooth, and JARVIS app-permission settings; supported voice transcripts can be reviewed and explicitly confirmed before opening a system screen.
- Authenticated reminder creation and reminder-list refresh through the backend.
- Cleartext HTTP disabled; there is no always-on microphone.

Memory management screens, reminder notifications/recurrence, workout tracking, device pairing/revocation, and background sync are not implemented in the Android app yet.

## Build

Install Android Studio with Android SDK 35 and JDK 17, then open the `android/` directory as a project and let Gradle sync. GitHub Actions builds the debug APK with Gradle 8.9 and uploads it as the `jarvis-android-debug-apk` workflow artifact.

To build locally, use Android Studio's Build menu or from a terminal with Gradle and Android SDK configured:

```sh
cd android
gradle assembleDebug
```

The expected APK path after a successful build is `app/build/outputs/apk/debug/app-debug.apk`. A CI build does not prove that the app has been installed on your phone or that your backend is reachable from it.

## Connect your phone safely

1. Run the backend on a machine reachable by the phone over a private network or a secured HTTPS host.
2. The app accepts only an `https://` endpoint. `http://127.0.0.1:8000` on the phone points to the phone itself, not your laptop.
3. Configure the same `JARVIS_API_TOKEN` on the backend and enter it in the app. The app encrypts the token using Android Keystore.
4. Tap **Connect securely**, select your reply language, then tap **Speak to JARVIS** or type a message and tap **Send**.
5. Microphone permission is requested only when you tap Speak. The transcript is displayed for review before sending. Speech recognition may rely on the Android speech service and its availability/network behavior.
6. For spoken replies, the app uses the phone's installed TTS voice. Telugu voice quality depends on installed system language data.

## Security and limitations

- Cleartext traffic is disabled. Never send the bearer token over plain HTTP.
- This is a shared-token prototype, not per-device pairing. Rotate the token if it is exposed. Per-device revocation and authorization remain required before cloud deployment.
- Android background execution is restricted. No hidden or always-on listening is implemented; future background routines should use WorkManager or properly disclosed foreground services only where appropriate.
- The backend must remain local/private until authentication, TLS, rate limiting, and production security are completed.
