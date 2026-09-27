# SKY Platform — Branch Protection & Governance Policy

## Overview
To protect the institutional quantitative models, M18 certification invariants, and capital sizing safety perimeters, direct pushes to `main` and merging unverified code are strictly governed.

---

## Mandated Rules for `main`

1. **Mandatory Passing Status Checks**:
   - Every Pull Request targeting `main` must pass the GitHub Actions CI workflow:
     - `All 7 Preflight Quality Gates`
   - Gate 1: Database Schema Integrity
   - Gate 2: M18 Institutional Certification Integrity
   - Gate 3: Python Linter & Formatter (Ruff)
   - Gate 4: TypeScript Linter (ESLint)
   - Gate 5: Pytest Quantitative Suite (630+ tests)
   - Gate 6: Jest Desk & Backend Suite (22 test suites)
   - Gate 7: Frontend Vite Production Build

2. **Branch Up-to-Date Requirement**:
   - Pull requests must be rebased or merged with the latest HEAD of `main` before merging (`strict: true`).

3. **Enforce Admins**:
   - Administrators and repository owners are bound by the same CI status check requirements. No individual can bypass the 7 preflight gates.

4. **Linear History**:
   - Squash-and-merge or rebase-and-merge is required to prevent tangled merge commits.

5. **No Force Pushes / No Deletions**:
   - History rewrite is strictly forbidden on `main`.

---

## Automated Configuration
To automatically apply these rules, run:
```bash
python scripts/setup_branch_protection.py cloudshome/CBT main
```
Or via GitHub CLI:
```bash
gh api --method PUT repos/cloudshome/CBT/branches/main/protection --input - << 'EOF'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "All 7 Preflight Quality Gates"
    ]
  },
  "enforce_admins": true,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false
}
EOF
```
