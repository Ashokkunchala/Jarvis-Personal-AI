# JARVIS for Android

Native Kotlin + Jetpack Compose app with the cinematic command-centre look: deep
navy panels, cyan accents and the glowing AI Core orb. It talks to your own
JARVIS backend over HTTPS on your private network.

## What the app does

- Cinematic command centre: animated AI Core orb (offline / idle / listening /
  working states), dark navy panels, cyan status lights.
- Secure connect: HTTPS health check to a user-configured backend; cleartext
  HTTP is disabled.
- Device pairing: the backend master token is sent once (never stored) to issue
  a per-device token; the issued token, backend URL and device ID are encrypted
  with Android Keystore AES-GCM. Paired devices can be revoked after an explicit
  confirmation; "Forget device token" clears this phone only.
- Chat with short conversation history: text input plus tap-to-speak speech
  recognition (transcript shown for review before sending) and spoken replies
  through the phone's installed text-to-speech voice.
- Personality modes: Assistant, Friend, Teacher, Storyteller and Doctor chips
  send the mode with each chat request, matching the web command centre. Doctor
  mode gives general health information only and is not medical advice.
- Quick actions: one-tap prompt chips (system status, story, song, AWS lesson,
  today's reminders) that fill the message box for review before sending.
- Activity & approvals feed: polls the backend's bounded runtime event feed and
  shows what JARVIS is doing. Confirmations for sensitive or irreversible
  actions stay on your laptop; the phone feed is read-only on purpose.
- Live Voice: user-started full-duplex Gemini Live audio over the
  authenticated, short-lived-ticket WebSocket bridge, with visible start,
  interrupt and stop controls. The microphone runs only while the app is visible.
- Reminders: create, list, complete and recurring reminders through the
  backend; opt-in WorkManager reminder polling with Android notifications
  (best-effort, may be delayed at least 15 minutes; not an alarm service).
- Explicit memories: save, review and delete only the facts you choose.
- Phone controls: quick links to Android device, Wi-Fi, Bluetooth and JARVIS
  app-permission settings; supported voice transcripts open the matching system
  screen only after you tap "Run recognized phone command".
- Language: reply language cycles through adaptive/auto, Indian English and
  Telugu.

No hardcoded secrets, no analytics, no third-party tracking, no cloud spend.

## Build the APK

Everything needed is in this directory: the Gradle wrapper (`gradlew`,
`gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`,
`gradle/wrapper/gradle-wrapper.properties`) and pinned dependency versions in
`app/build.gradle.kts`. You do not need to install Gradle yourself.

Requirements:

- JDK 17 (Android Studio bundles one, or install any OpenJDK 17).
- Android SDK with Platform 35 and Build-Tools 35.0.0. The easiest way to get
  both is Android Studio (Settings > SDK Manager). Tell Gradle where the SDK is
  with the `ANDROID_HOME` environment variable or a `local.properties` file
  containing `sdk.dir=/path/to/Android/Sdk` (never commit `local.properties`).

Option 1 - Android Studio (recommended):

1. Install Android Studio, then open this `android/` directory as a project.
2. Let Gradle sync finish (it downloads Gradle 8.9 and the dependencies once).
3. Build > Build App Bundle(s)/APK(s) > Build APK(s). The APK lands at
   `app/build/outputs/apk/debug/app-debug.apk`.
4. With your phone connected by USB with USB debugging on, use Run to install
   it directly.

Option 2 - command line:

```sh
cd android
./gradlew assembleDebug        # Windows: gradlew.bat assembleDebug
```

The APK is written to `app/build/outputs/apk/debug/app-debug.apk`. Copy it to
your phone and tap it to install (allow installs from this source when
Android asks), or install over USB with `adb install app/build/outputs/apk/debug/app-debug.apk`.

GitHub Actions also builds the debug APK on every push to this branch (the
`android-build` job in `.github/workflows/tests.yml`) and uploads it as the
`jarvis-android-debug-apk` artifact. A CI build proves the code compiles; it
does not prove the app runs on your phone or that your backend is reachable.

## Connect your phone safely

1. Start the backend with `jarvis serve` on a machine reachable by the phone
   over a private network or a secured HTTPS host.
2. The app accepts only an `https://` endpoint. `http://127.0.0.1:8000` on the
   phone points to the phone itself, not your laptop. For plain-HTTP testing on
   a LAN, put a local HTTPS proxy in front of the backend - never send the
   bearer token over plain HTTP.
3. For a per-device credential, enter a descriptive device name and the
   backend's master `JARVIS_API_TOKEN` in the pairing section, then tap
   **Pair device**. The issued per-device token is encrypted with Android
   Keystore. Manual token entry remains available for backends without the
   device-management endpoints.
4. Tap **Connect securely**, pick a personality mode, then type or speak.
5. Tap **Speak to JARVIS** for one-utterance speech recognition; the transcript
   is displayed for review before sending. Speech recognition may rely on the
   Android speech service and its availability/network behavior.
6. Tap **Start Live Voice** for full-duplex audio. Live audio is sent to the
   configured Gemini service.
7. To receive due reminders, tap **Enable Android notifications** and grant
   notification permission. WorkManager checks about every 15 minutes when
   network access is available; this is not an exact alarm.
8. To revoke this paired device, re-enter the backend master token, tap
   **Revoke paired device**, and confirm. **Forget device token** clears local
   credentials only; it does not revoke the backend credential.

## Honest limitations

- The debug APK here is built from source on your machine or CI; there is no
  signed release build yet.
- Android 14 restricts starting microphone foreground services from boot;
  launch JARVIS yourself and tap Speak or Start Live Voice to use the
  microphone. There is no always-on listening.
- Telugu voice quality depends on the system language data installed on the
  phone.
- Pairing uses the shared master token to issue a per-device token. Token
  rotation, device-flow verification and production authorization remain
  required before any cloud deployment; keep the backend local/private until
  then.
- Memory editing, workout tracking and background data sync are not implemented
  in the Android app yet; approvals themselves stay on the laptop by design.
