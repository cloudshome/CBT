# SKY Windows companion (P20)

This folder holds the **unsigned** packaging notes plus the real
`SkyCompanion/` .NET 8 project (P22.2).

**This repository does not ship a signed `.exe` or MSIX.** Compile on a
Windows host; code signing is a trusted-release step.

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
