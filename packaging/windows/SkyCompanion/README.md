# SkyCompanion (Windows, P22.2)

SDK-style **.NET 8 WinForms + WebView2** project. This is a real project tree,
not a recipe-only folder.

## Honest status

- Compiles on a **Windows 11** host with the .NET 8 SDK and WebView2 runtime.
- This Linux checkout does **not** run MSBuild and does **not** produce a
  signed `.exe` / MSIX.
- Device tokens go to Windows Credential Manager (`SKY/HubDeviceToken`).
- `live_exchange_execution` is hard-coded `false`. There is no order API.

```text
dotnet restore
dotnet build -c Release
```

Signing (Authenticode) is a trusted-release step. Never commit a PFX.
