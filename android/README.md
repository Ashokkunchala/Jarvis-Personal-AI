# Native Android application

This is the first Kotlin + Jetpack Compose app shell. It has no always-on microphone, device-control, notification, or background-sync behavior yet. It currently validates the shape of a future HTTPS endpoint and token locally; it does not send or store the token.

## Build

Install Android Studio with Android SDK 35 and a compatible JDK (17 recommended), then open the `android/` directory as a project and let Gradle sync. From a terminal with Gradle/Android SDK configured:

```sh
cd android
gradle assembleDebug
```

The expected debug APK path after a successful build is `app/build/outputs/apk/debug/app-debug.apk`. This repository update has not been built on an Android SDK-equipped machine, so APK generation is not yet verified.

## Security and next work

- Cleartext traffic is disabled. Do not put an API token into an ordinary HTTP request over Wi-Fi.
- The token field is temporary and is not persisted. Implement Android Keystore-backed storage and per-device pairing before connecting.
- Android background execution and microphone use are restricted by the OS. Use explicit foreground-service permission and notification disclosures only for user-started voice sessions; use WorkManager for deferrable work.
- Request notification and microphone permissions at the moment the feature is enabled, not on first launch.
