# SkyCompanion (Android, P22.2)

Gradle / Kotlin application. This is a real project tree, not a recipe-only
folder.

## Honest status

- Assembles on a host with Android SDK 34 + JDK 17.
- This Linux checkout does **not** run Gradle and does **not** produce a
  signed APK / AAB.
- Device tokens go to the Android Keystore alias `sky_hub_device_token`.
- Operator mutations require `BiometricPrompt`. Offline mutations are refused.
- `usesCleartextTraffic=false`. `live_exchange_execution` is hard-coded false.

```text
./gradlew :app:lintDebug :app:testDebugUnitTest
./gradlew :app:assembleDebug
```

Release signing is a trusted-host step. Never commit a `.jks` or passwords.
