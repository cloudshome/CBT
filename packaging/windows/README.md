# SKY Windows companion (P20)

This folder is the **unsigned** packaging recipe for a WebView2 shell
that talks to an Ubuntu SKY Hub over `/api/v1`.

**This repository does not ship a signed `.exe` or MSIX.** Code signing
and a public checksum channel are P22. Do not claim an installer exists
until a release artifact is produced on a Windows build host.

## What the companion is

- A Start-menu / tray app that opens the same workstation the PWA uses.
- First-run pairing: scan or type the Hub's one-time code
  (`python main.py hub pair` or Account → pairing).
- Device token stored in **Windows Credential Manager**, never in a
  world-readable file.
- HTTPS only (loopback HTTP allowed for development).
- Mutations use `Idempotency-Key`. Offline = read-only banner.
- `live_exchange_execution` is always false.

## What it is not

- Not a second engine, database, or risk gate.
- Not a local paper runner.
- Not an exchange-order client.

## Build (when a Windows host exists)

Pin a WebView2 packaging tool at implementation time. Produce an
unsigned MSIX/exe plus SHA-256. Signing keys never live in this repo.
