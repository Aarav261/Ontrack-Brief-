# Security Policy

OnTrack(er) handles authentication tokens and student data, so we take security
seriously. Thank you for helping keep it and its users safe.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues,
discussions, or pull requests.**

Instead, report privately using one of:

- **GitHub Security Advisories** — preferred: open a draft advisory at
  [Security → Report a vulnerability](https://github.com/Aarav261/Ontracker/security/advisories/new).
- **Direct contact** — message the maintainer ([@Aarav261](https://github.com/Aarav261)) on GitHub.

Please include:
- A description of the vulnerability and its impact.
- Steps to reproduce (proof-of-concept if possible).
- Affected component (backend API, web app, extension) and version/commit.

## What to expect

- We aim to acknowledge your report within **72 hours**.
- We'll keep you updated as we investigate and work on a fix.
- We'll credit you in the advisory once it's resolved, unless you prefer to
  remain anonymous.

## Scope

Particularly sensitive areas:
- OnTrack token capture, storage, and encryption (`core/crypto.py`, `core/ontrack/`).
- Clerk session verification (`core/clerk_auth.py`).
- Any endpoint in `routes/main.py` handling credentials or user data.

## Please avoid

- Accessing, modifying, or exfiltrating data that isn't yours.
- Denial-of-service testing against production (`on-tracker.com`).
- Social engineering of users or maintainers.

Responsible testing against your **own** local instance is encouraged.
