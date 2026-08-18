# SKY release and incident operations (P22.1)

This is the release contract for the Ubuntu Hub and its Windows/Android
companions. P22.1 makes outputs inspectable and supportable; it does **not**
claim that this source checkout contains a signed `.deb`, `.exe`, or `.apk`.

## 1. Trust boundary

- Pull-request CI receives **no signing credentials**. It tests contracts,
  builds the unsigned Debian artifact, emits SHA-256 metadata and an SPDX SBOM,
  and runs a dependency vulnerability audit.
- Debian, Windows, and Android signing keys exist only in an isolated release
  environment with audited human access. Never place a key, certificate,
  password, base64 keystore, or signing command line in Git, job logs, support
  bundles, or GitHub artifacts.
- `ops.release.signing_readiness()` reports secret *names* and booleans only.
  It never reads or prints values.
- A release manifest may say `signed: true` only after a platform verifier has
  produced a detached verifier record. Metadata generation alone is not
  signing.

## 2. Version and channels

SKY has two channels:

- **beta** — supported preview. Database migrations must be backward-compatible
  with the latest stable backup. Native clients may be beta while the Hub is
  stable if `/api/v1/version` reports them compatible.
- **stable** — promoted only after clean-target installation, backup, upgrade,
  restart, restore and rollback evidence is attached to the release review.

No silent major migration is allowed. Release notes state the app version,
`/api/v1` range, migration/rollback impact, known issues, and the supported
postpone window. Operators opt in to updates; companions must not silently
replace the Hub or change channels.

## 3. Build, inspect, sign, promote

1. Check out the exact annotated tag and verify the commit review.
2. A repository admin reviews `ci/release.workflow.yml` and copies it to
   `.github/workflows/release.yml` (Arena's GitHub App cannot write workflow
   files). Let that workflow build unsigned outputs. It is an untrusted build
   environment and never signs.
3. Download artifacts and verify `SHA256SUMS`, `release.json`,
   `sky.spdx.json`, `dependencies.json`, tests, and vulnerability findings.
4. On isolated native build hosts, compile
   `packaging/windows/SkyCompanion` (dotnet) and
   `packaging/android/SkyCompanion` (Gradle). P20/P21 remain the client
   **contracts**; P22.2 added the project trees. This checkout still does
   not ship installers.
5. Sign using platform-native tooling:
   - Debian: sign repository `Release` metadata (`InRelease` plus detached
     `Release.gpg`); do not embed a private key in the `.deb`.
   - Windows: Authenticode-sign MSIX/EXE and verify signature, timestamp and
     publisher on a clean Windows 11 target.
   - Android: sign APK/AAB with the release keystore and verify with
     `apksigner verify --verbose --print-certs` on a clean supported device.
6. Recompute SHA-256 after signing. Add detached verifier records, SBOM,
   dependency/license inventory and release notes. Signing changes bytes.
7. Test clean install, pairing, authorized paper mutation, uninstall, backup,
   upgrade and rollback. Verify `live_exchange_execution=false` throughout.
8. Promote beta metadata to stable only after a second human reviews the
   evidence. Keep the previous stable artifacts and repository metadata
   available for the documented support window.

Generate local metadata around built artifacts:

```bash
python packaging/build_release.py --channel beta \
  --artifact dist/sky-hub_2.38.0-1_all.deb --output dist/release
```

## 4. Diagnostics and privacy

```bash
python main.py hub diagnostics --archive /private/path/sky-support.tar.gz --json
```

The archive is mode `0600` and contains one inspectable
`diagnostics.json`. It excludes the SQLite database, Parquet market store,
environment, raw logs and secrets. **Open and inspect it before sharing.** A
support engineer should ask for this bundle first, never for `.env`, device
tokens, a database, signing material, or exchange credentials.

## 5. Incident paths

### Hub offline

1. Check host power/network and `sky status`; do not expose port 8050.
2. Run `sky doctor`, then inspect `sky logs --unit sky-dashboard.service`.
3. Restart only the failed unit. Keep the Hub loopback-bound behind TLS.
4. If an upgrade caused the outage, stop workers and follow **Rollback**.

### Stale data

1. Treat every companion as read-only; never replay an offline approval.
2. Check the System page/data age, host clock, calendar and source health.
3. Preserve evidence and logs. Do not fill, interpolate or substitute demo
   candles for real evidence.

### Database locked or corrupt

1. Stop dashboard, scan and paper writers. Copy the files privately; do not
   upload the database to support.
2. For a lock, identify the writer before killing anything. Never delete WAL
   files from a live database.
3. For corruption, preserve the original, verify the latest backup checksum,
   restore to a new path, run doctor, then restart one writer at a time.

### Disk full

1. Stop writers. Do not delete the database or newest backup.
2. Move old, checksum-verified backups or market-store partitions to private
   storage. Never make them world-readable.
3. Run doctor and take a new SQLite-safe backup before resuming.

### Certificate expired

1. Keep the Hub on loopback; do not bypass HTTPS or enable remote plaintext.
2. Renew the proxy certificate and verify hostname, chain and system clock.
3. Companions remain read-only until normal TLS validation succeeds.

### Failed migration

1. Stop all writers and retain the failed version's logs and support bundle.
2. Do not repeatedly rerun a partially applied migration.
3. Restore the pre-upgrade backup to a new path and follow **Rollback**.

### Lost phone

1. From another authenticated owner session, revoke the Android device token.
2. Rotate any notification credentials that may have appeared on the device.
3. Do not weaken biometric or TLS policy to recover access. Pair a replacement
   with a fresh one-time code after account review.

### Rollback

1. Stop dashboard, scan and paper services; take a final private snapshot of
   the failed state.
2. Verify the previous stable artifact, checksum and signature against the
   retained stable metadata.
3. Restore the pre-upgrade SQLite-safe backup if and only if release notes say
   the migration is not backward-compatible. Never copy a live DB file.
4. Install the prior version, start the dashboard alone, run `sky doctor`,
   inspect app/API versions and data age, then start scan and paper workers.
5. Keep clients within the published `/api/v1` compatibility range. Record the
   incident and do not re-promote until the root cause has a regression test.

## 6. P22.3 drill evidence

```bash
python main.py release drills --json
python main.py release check --drill ubuntu-clean-vm --evidence /path/to/ubuntu-clean-vm.json
```

A drill is **OPEN** until an operator JSON file supplies every required field
from `ops/release_drills.py`. Claims that “this sandbox signed” or that Linux
CI installed Windows/Android are rejected. `live_exchange_execution` must stay
false. P22 is complete only when every drill file in an evidence directory
passes — never because the catalog exists.

## 7. Current honest limitations

- No signing key is available to this repository, by design.
- P22.2 added native project trees. Linux CI static-lints them; it still
  cannot compile, Authenticode-sign, or `apksigner`-verify. Physical
  Windows/Android install, notification, biometric, upgrade and rollback
  drills remain open.
- A clean physical Windows/Android install, notification and biometric drill
  cannot be claimed from Linux CI.
- Packaging never proves trading edge and never opens micro-live graduation.
