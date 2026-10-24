# Native Android application

This is the first Kotlin + Jetpack Compose app shell. It has no always-on microphone, device-control, notification, or background-sync behavior yet. The setup screen checks the HTTPS backend health endpoint and stores the token encrypted with an Android Keystore AES-GCM key after the health check succeeds. It can call the chat endpoint over HTTPS using the encrypted token; personal-data API screens and device pairing/revocation are not implemented.

## Build

Install Android Studio with Android SDK 35 and a compatible JDK (17 recommended), then open the `android/` directory as a project and let Gradle sync. From a terminal with Gradle/Android SDK configured:

```sh
cd android
gradle assembleDebug
```

The expected debug APK path after a successful build is `app/build/outputs/apk/debug/app-debug.apk`. GitHub Actions successfully built the debug APK for the current Android source revision. A physical-device install and live backend test are still pending.

## Security and next work

- Cleartext traffic is disabled. Do not put an API token into an ordinary HTTP request over Wi-Fi.
- The token is encrypted using an Android Keystore key and can be cleared from the setup screen. It is not yet used for API calls; implement per-device pairing/revocation before connecting sensitive endpoints.
- Android background execution and microphone use are restricted by the OS. Use explicit foreground-service permission and notification disclosures only for user-started voice sessions; use WorkManager for deferrable work.
- Request notification and microphone permissions at the moment the feature is enabled, not on first launch.
