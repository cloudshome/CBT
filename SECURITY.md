# SECURITY.md — Security Policy & Practices

## 1. Security Policy & Reporting Vulnerabilities

The Crypto Brain Terminal (CTB) team prioritizes security, data integrity, and capital preservation across all architectural components.

### 1.1 Reporting a Vulnerability
If you discover a security vulnerability in this repository, please do NOT create a public GitHub Issue. Instead, submit a confidential report to the primary maintainer:
- **Contact**: `cloudshome` (via GitHub Security Advisory or direct maintainer channel)
- **Response SLA**: Initial triage within 48 hours; patch proposal within 7 days.

---

## 2. Secrets & Environment Variable Management

### 2.1 Principle of Least Privilege
- **Never Commit Secrets**: Secrets such as `GEMINI_API_KEY`, exchange credentials, private certificates, or database credentials must never be committed to Git.
- **`.gitignore` Enforcement**: The repository `.gitignore` explicitly blocks `.env`, `*.db`, `*.key`, and credential stores.
- **Environment Variable Masking**: In GitHub Actions CI pipelines, all secrets are ingested exclusively via encrypted repository secrets and automatically masked in build logs.

### 2.2 Local & Production Configuration
- For local development, copy `.env.example` to `.env` and assign local values.
- In Dockerized deployments, inject secrets via Docker Compose environment variables or secrets management vaults.

---

## 3. Container & Network Security

### 3.1 Non-Root Container Execution
- In `Dockerfile.backend`, the container switches to the unprivileged `node` user (`USER node`) after build steps and permission assignment.
- Processes inside the backend container run with minimal Linux capabilities.

### 3.2 Network Isolation
- Docker services communicate over an isolated user-defined bridge network (`ctb-network`).
- The backend API service is accessible internally by the frontend Nginx reverse proxy via Docker DNS (`http://backend:3000`), preventing unauthorized external interface exposure when bound to internal subnets.

### 3.3 Minimal Base Images
- All containers utilize minimal `alpine` base distributions (`node:20-alpine`, `nginx:alpine`) to minimize attack surface, reduce package CVE vulnerabilities, and maintain rapid startup times.

---

## 4. Application-Level Security & Defenses

### 4.1 Denial-of-Service (DoS) & Rate Limiting
- Built-in rate limiting middleware (`src/middleware/rateLimit.ts`) enforces sliding-window request throttling (default: 60 requests per minute per IP address).
- Exceeded thresholds return `HTTP 429 Too Many Requests` along with standard `Retry-After` headers.

### 4.2 Strict Input Validation & Type Safety
- All REST endpoints employ rigorous input validation schemas (`src/utils/validation.ts`) verifying:
  - Uppercase alphanumeric symbol formats (e.g., `BTCUSDT`).
  - Whitelisted timeframes (`5m`, `15m`, `1h`, `4h`, `1d`).
  - Bounded numerical limits for pagination and historical query sizes.
- Unvalidated or malformed inputs are rejected immediately with `HTTP 400 Bad Request`.

### 4.3 Database Injection Prevention
- All database queries interact with SQLite through the **Prisma ORM**, which utilizes strictly parameterized queries and prepared statements, neutralizing SQL injection vectors.

### 4.4 Capital Preservation via Institutional Risk Gate
- The pre-execution Risk Gate (`src/middleware/riskGate.ts`) acts as a mandatory safety firewall.
- Trades risking more than **2.0%** of account equity or exceeding **3 open positions** are automatically rejected before reaching persistence or execution layers.

---

## 5. Continuous Security Audits & CI Scanning

- **Secret Scanning**: GitHub Secret Scanning actively monitors commits and pull requests for exposed keys.
- **Automated CI Test Suite**: Every PR triggers automated unit and integration tests covering rate limiting, input validation, and risk gate boundary enforcement.
- **Dependency Auditing**: Regular dependency reviews (`npm audit`) to address upstream package vulnerabilities.
