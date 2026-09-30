# scripts/generate_test_cert.ps1
# Generates a strictly isolated development-only Code Signing Certificate
param(
    [string]$CertPath = "certs/dev_codesign.pfx",
    [string]$Password = "DevTestPassword123!"
)

$ErrorActionPreference = "Stop"

$subject = "CN=Crypto Brain Terminal Development, OU=Development Only - Not For Production, O=CBT Dev"

# Check if cert already exists in CurrentUser\My
$existing = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue | Where-Object { $_.Subject -like "*Crypto Brain Terminal Development*" } | Select-Object -First 1

if ($existing) {
    Write-Host "[CERT ENGINE] Found existing dev code signing certificate: $($existing.Thumbprint)"
    $cert = $existing
} else {
    Write-Host "[CERT ENGINE] Generating new self-signed development code signing certificate..."
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $subject `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -HashAlgorithm SHA256 `
        -NotAfter (Get-Date).AddYears(1)
    Write-Host "[CERT ENGINE] Certificate generated with Thumbprint: $($cert.Thumbprint)"
}

# Ensure destination directory exists
$dir = Split-Path -Path $CertPath -Parent
if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

# Export to PFX if requested
if ($CertPath) {
    $secPass = ConvertTo-SecureString -String $Password -AsPlainText -Force
    Export-PfxCertificate -Cert $cert -FilePath $CertPath -Password $secPass | Out-Null
    Write-Host "[CERT ENGINE] Exported dev PFX to: $CertPath"
}

Write-Host "[CERT ENGINE] Thumbprint: $($cert.Thumbprint)"
