# SKY Android companion (P21)

This folder holds the **unsigned** packaging notes plus the real
`SkyCompanion/` Gradle/Kotlin project (P22.2).

**This repository does not ship a signed `.apk`.** Assemble on an Android
SDK host; signing is a trusted-release step.

## What the companion is

- A native Android shell (Kotlin) using the same `/api/v1` contract the PWA
  and the Windows companion use. Navigation, secure storage and
  notifications are native; the Hub stays the only DB, risk gate and paper
  runner.
- First-run pairing: scan or type the Hub's one-time code
  (`python main.py hub pair --platform android` or Account → pairing).
- Device token stored in the **Android Keystore**, never in app-accessible
  plaintext or logs.
- **HTTPS only**; a hardened WebView is allowlisted to the configured Hub
  host only — no arbitrary web navigation, file upload, or JavaScript bridge
  that exposes device secrets.
- **Biometric re-check** (`BiometricPrompt`) before operator mutations
  (paper approval, journal write, revoke device).
- **Online-only mutations**: an approval is never queued for replay offline.
  Offline = read-only cached shell with an honest "last updated" stamp.
- Push notifications **deep-link** to the exact signal / risk / paper /
  journal record.
- `live_exchange_execution` is always false.

Client contract module: `ops/android_companion.py` (`spec`, `validate-url`,
`status`, `pair_with_hub`, `biometric_policy`, `deep_link`,
`connection_snapshot`, `KeystoreTokenStore`).

## What it is not

- Not a second engine, database, or risk gate.
- Not a local paper runner.
- Not an exchange-order client.

## Build (when an Android host exists)

Pin an Android toolchain at implementation time (Gradle/AGP, a target SDK,
`minSdk`). Produce an unsigned APK plus SHA-256. Signing keys never live in
this repo. Play Store / AAB is a later release-channel option (P22).

Deep-link scheme reserved: `sky://record/<signal|risk|paper|journal|dashboard>[/<id>]`.
