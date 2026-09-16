"""Google Drive Authentication and Diagnostics Tool for CTB / SKY.

Configures and tests connection to the target Google Drive account
(default target: ypelectronics11@gmail.com).

Usage:
    python scripts/setup_gdrive_auth.py --status
    python scripts/setup_gdrive_auth.py --login
    python scripts/setup_gdrive_auth.py --test-upload
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

try:
    import dotenv
    dotenv.load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass


def _clean_folder_id(val: str | None) -> str | None:
    if not val:
        return None
    val = val.strip()
    if "folders/" in val:
        val = val.split("folders/")[-1].split("?")[0].split("/")[0]
    return val or None


SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
]

DEFAULT_TARGET_EMAIL = "ypelectronics11@gmail.com"


def check_status() -> None:
    """Checks the current Google Drive authentication status and prints diagnostics."""
    print("=" * 65)
    print("CTB / SKY GOOGLE DRIVE INTEGRATION DIAGNOSTICS")
    print("=" * 65)

    target_email = os.getenv("GDRIVE_USER_EMAIL", DEFAULT_TARGET_EMAIL)
    print(f"[*] Target User Account  : {target_email}")

    service_account_file = (
        os.getenv("GDRIVE_SERVICE_ACCOUNT_FILE")
        or "credentials/gdrive_service_account.json"
    )
    oauth_token_file = (
        os.getenv("GDRIVE_OAUTH_TOKEN_FILE")
        or "credentials/gdrive_token.json"
    )
    client_secret_file = (
        os.getenv("GDRIVE_CLIENT_SECRET_FILE")
        or "credentials/gdrive_client_secret.json"
    )
    root_folder_id = _clean_folder_id(os.getenv("GDRIVE_ROOT_FOLDER_ID")) or "(not set - will use root)"

    print(f"[*] Root Folder ID       : {root_folder_id}")
    print(f"[*] Service Account File : {service_account_file} -> {'EXISTS' if Path(service_account_file).exists() else 'NOT FOUND'}")
    print(f"[*] OAuth Token File     : {oauth_token_file} -> {'EXISTS' if Path(oauth_token_file).exists() else 'NOT FOUND'}")
    print(f"[*] OAuth Client Secrets : {client_secret_file} -> {'EXISTS' if Path(client_secret_file).exists() else 'NOT FOUND'}")

    from core.autonomous_research.storage.drive_backend import get_default_drive_backend

    backend = get_default_drive_backend()

    print("\n[-] Testing connectivity to backend...")
    if not getattr(backend, "is_live", False):
        print("\n[!] STATUS: LOCAL SIMULATED STORAGE ACTIVE")
        print("    No live Google credentials active. Files are safely archived in:")
        print("    -> data/gdrive_simulated_archive/SKY/")
        print("\n[?] HOW TO CONNECT LIVE 'ypelectronics11@gmail.com':")
        print("    OPTION A (Recommended for 24/7 background): Service Account")
        print("      1. Place your Google Cloud service account JSON at:")
        print(f"         {service_account_file}")
        print("      2. In Google Drive (ypelectronics11@gmail.com), create a folder (e.g. 'SKY_ARCHIVE')")
        print("      3. Share that folder with your service account email as 'Editor'.")
        print("      4. Add GDRIVE_ROOT_FOLDER_ID=<folder_id_from_url> and GDRIVE_USER_EMAIL=ypelectronics11@gmail.com to .env")
        print("\n    OPTION B: Direct OAuth2 Login (Browser authorization)")
        print("      1. Download OAuth 2.0 Client ID (Desktop App) JSON to:")
        print(f"         {client_secret_file}")
        print("      2. Run: python scripts/setup_gdrive_auth.py --login")
        return

    # If live backend is initialized
    try:
        user_info = backend.service.about().get(fields="user,storageQuota").execute()
        user = user_info.get("user", {})
        quota = user_info.get("storageQuota", {})

        email = user.get("emailAddress", "Unknown")
        name = user.get("displayName", "Unknown")
        used_gb = int(quota.get("usage", 0)) / (1024**3)
        total_gb = int(quota.get("limit", 0)) / (1024**3) if "limit" in quota else 0

        print("\n[+] LIVE GOOGLE DRIVE CONNECTED!")
        print(f"    Connected Email: {email}")
        print(f"    Display Name   : {name}")
        if total_gb > 0:
            print(f"    Storage Quota  : {used_gb:.2f} GB used of {total_gb:.2f} GB")
        else:
            print(f"    Storage Quota  : {used_gb:.2f} GB used (Unlimited/Workspace)")

        if email.lower() == target_email.lower():
            print(f"\n[OK] Connected account perfectly matches target: {target_email}")
        else:
            print(f"\n[!] Note: Connected as '{email}', target is '{target_email}'.")
    except Exception as exc:
        print(f"\n[!] Connection error: {exc}")


def run_oauth_login() -> None:
    """Executes OAuth 2.0 Desktop authorization flow to connect ypelectronics11@gmail.com."""
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("[!] Missing google_auth_oauthlib. Install it via: pip install google-auth-oauthlib")
        return

    client_secret_file = (
        os.getenv("GDRIVE_CLIENT_SECRET_FILE")
        or "credentials/gdrive_client_secret.json"
    )
    token_file = (
        os.getenv("GDRIVE_OAUTH_TOKEN_FILE")
        or "credentials/gdrive_token.json"
    )

    if not Path(client_secret_file).exists():
        print(f"[!] Error: Client secret file '{client_secret_file}' not found.")
        print("\nTo generate this file:")
        print("1. Go to Google Cloud Console: https://console.cloud.google.com/apis/credentials")
        print("2. Create Credentials -> OAuth client ID -> Application type: Desktop app.")
        print("3. Download JSON and save it as: credentials/gdrive_client_secret.json")
        print("4. Re-run: python scripts/setup_gdrive_auth.py --login")
        return

    Path(token_file).parent.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 65)
    print("OAUTH AUTHORIZATION GUIDE:")
    print("1. Your browser will open the Google Sign-in page.")
    print("2. Choose 'ypelectronics11@gmail.com'.")
    print("3. If you see 'Google hasn't verified this app':")
    print("   Click 'Advanced' (bottom left) -> Click 'Go to CTB Storage (unsafe)' -> 'Continue'.")
    print("=" * 65 + "\n")

    flow = InstalledAppFlow.from_client_secrets_file(client_secret_file, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_file, "w", encoding="utf-8") as token:
        token.write(creds.to_json())

    print(f"[+] Credentials saved successfully to: {token_file}")
    print("[*] Verifying new credentials...")
    check_status()


def test_upload() -> None:
    """Performs a test file upload to live Google Drive."""
    import tempfile
    import time

    from core.autonomous_research.storage.drive_backend import get_default_drive_backend

    backend = get_default_drive_backend()
    if not getattr(backend, "is_live", False):
        print("[!] Cannot run test upload: Live Google Drive is not connected.")
        check_status()
        return

    print("[*] Creating temporary probe file...")
    test_content = f"CTB Live Google Drive Probe\nTimestamp: {time.time()}\nTarget: {DEFAULT_TARGET_EMAIL}\n"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(test_content)
        temp_path = Path(f.name)

    try:
        print("[*] Uploading probe file to 'SKY/00_INBOX'...")
        meta = backend.upload_file(
            local_path=temp_path,
            drive_folder="SKY/00_INBOX",
            filename=f"probe_{int(time.time())}.txt",
        )
        print("[+] Upload Success!")
        print(f"    File Name : {meta.name}")
        print(f"    Drive ID  : {meta.drive_file_id}")
        print(f"    Drive Path: {meta.drive_path}")
        print(f"    Size      : {meta.file_size} bytes")
        print(f"    MD5       : {meta.md5_checksum}")
    except Exception as exc:
        print(f"[!] Upload test failed: {exc}")
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="CTB Google Drive Setup & Diagnostics")
    parser.add_argument("--status", action="store_true", help="Check current Google Drive connection status")
    parser.add_argument("--login", action="store_true", help="Run OAuth2 login flow for personal Google account")
    parser.add_argument("--test-upload", action="store_true", help="Perform a test file upload to live Google Drive")

    args = parser.parse_args()

    if args.login:
        run_oauth_login()
    elif args.test_upload:
        test_upload()
    else:
        check_status()


if __name__ == "__main__":
    main()
