# Security Policy

## Supported Versions

Only the latest release on `main` is actively maintained and receives
security fixes.

| Version | Supported          |
|---------|--------------------|
| latest  | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

**Please do NOT open a public GitHub issue for security vulnerabilities.**

### Preferred method — GitHub Private Vulnerability Reporting

Use GitHub's built-in private reporting:
1. Go to the **Security** tab of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the template with as much detail as possible.

### Alternative — Email

If GitHub private reporting is unavailable, email the maintainers at:

```
security@example.com
```

Encrypt sensitive details using the project's public PGP key (if provided
in the repository).

---

## What to Include in a Report

- A clear description of the vulnerability.
- The component or file affected (e.g., `app/tools/http_request.py`).
- Steps to reproduce or a minimal proof-of-concept.
- Potential impact assessment (data exposure, RCE, privilege escalation, etc.).
- Your suggested fix or mitigation, if you have one.

---

## Response SLA

| Milestone                        | Target      |
|----------------------------------|-------------|
| Acknowledgement of report        | 48 hours    |
| Initial triage and severity score| 5 business days |
| Fix or mitigation shipped        | 30 days (critical), 90 days (others) |
| Public disclosure                 | After patch is released |

We follow a **coordinated disclosure** model. We will notify you before any
public announcement and credit you in the release notes unless you prefer
to remain anonymous.

---

## Security Design Principles

This project is built with the following security controls:

- **No secrets in code**: all credentials are provided via environment
  variables or Azure Key Vault references. See `.env.example`.
- **Input validation**: all user input and tool arguments are validated
  with Pydantic and a content-safety hook before processing.
- **Tool safety layer**: the `http_request` tool enforces a domain
  allowlist, method whitelist, rate limiting, and execution timeouts.
- **Dependency scanning**: Dependabot is configured to auto-raise PRs for
  outdated or vulnerable dependencies (see `.github/dependabot.yml`).
- **Least privilege**: the Docker container runs as a non-root user.
  Azure resources use managed identities — no stored credentials.

---

## Out of Scope

The following are **not** considered security vulnerabilities for this project:

- Reports from automated scanners without a reproducible exploit.
- Issues in dependencies that have already been patched upstream.
- Social engineering of project contributors.
- Physical security attacks.
- Denial-of-service via excessive API usage (covered by rate limiting).

---

## Safe Harbour

We consider security research conducted in good faith, following this policy,
to be authorised. We will not take legal action against researchers who:

- Report vulnerabilities privately and give us reasonable time to fix them.
- Do not access, modify, or delete data beyond what is necessary to
  demonstrate the vulnerability.
- Do not disrupt production services.

Thank you for helping keep this project and its users safe.
