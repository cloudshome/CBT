"""
GitHub Branch Protection Enforcer for SKY Platform.
Configures mandatory preflight status checks, prevents force-pushes,
and enforces linear history on the `main` branch.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys


def setup_branch_protection(repo: str = "cloudshome/CBT", branch: str = "main") -> None:
    print(f"[*] Configuring Branch Protection for repository: {repo} (branch: {branch})")

    protection_payload = {
        "required_status_checks": {
            "strict": True,
            "contexts": [
                "All 7 Preflight Quality Gates",
            ],
        },
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
    }

    gh_cli = shutil.which("gh")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    env = dict(os.environ)
    if token:
        env["GITHUB_TOKEN"] = token

    if gh_cli:
        print("[*] Detected GitHub CLI (gh). Attempting automated branch protection update...")
        try:
            cmd = [
                gh_cli,
                "api",
                "--method",
                "PUT",
                f"repos/{repo}/branches/{branch}/protection",
                "--input",
                "-",
            ]
            res = subprocess.run(
                cmd,
                input=json.dumps(protection_payload),
                text=True,
                capture_output=True,
                env=env,
            )
            if res.returncode == 0:
                print(
                    f"[PASS] Successfully configured branch protection on {repo}:{branch} via gh CLI!"
                )
                return
            else:
                print(f"[!] gh CLI API call returned code {res.returncode}: {res.stderr.strip()}")
        except (subprocess.SubprocessError, OSError) as e:
            print(f"[!] Automated configuration via gh CLI failed: {e}")

    # Fallback instructions if token/gh not authenticated
    print("\n" + "=" * 70)
    print("MANUAL / GH-CLI BRANCH PROTECTION CONFIGURATION INSTRUCTIONS")
    print("=" * 70)
    print("Run the following command using an authenticated GitHub CLI session:\n")
    json_str = json.dumps(protection_payload, indent=2)
    print(f"gh api --method PUT repos/{repo}/branches/{branch}/protection --input - << 'EOF'")
    print(json_str)
    print("EOF\n")
    print("-" * 70)
    print("OR configure manually via GitHub Web UI:")
    print(f"1. Go to: https://github.com/{repo}/settings/branches")
    print("2. Click 'Add classic branch protection rule' (or edit rule for 'main')")
    print("3. Branch name pattern: main")
    print("4. Check: 'Require status checks to pass before merging'")
    print("   - Check: 'Require branches to be up to date before merging'")
    print("   - Required check: 'All 7 Preflight Quality Gates'")
    print("5. Check: 'Require linear history'")
    print("6. Check: 'Do not allow bypassing the above settings' (Enforce for admins)")
    print("7. Uncheck: 'Allow force pushes' & 'Allow deletions'")
    print("8. Click 'Save changes'")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    repo_name = sys.argv[1] if len(sys.argv) > 1 else "cloudshome/CBT"
    branch_name = sys.argv[2] if len(sys.argv) > 2 else "main"
    setup_branch_protection(repo_name, branch_name)
