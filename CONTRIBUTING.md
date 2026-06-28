# Contributing to OnTrack(er)

Thanks for your interest in contributing! OnTrack(er) sends students a prioritised
weekday morning email brief of their [OnTrack](https://github.com/doubtfire-lms/doubtfire-web)
tasks, with a companion Chrome extension. This guide explains how to get set up and
submit changes.

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).

---

## Ways to contribute

- **Report a bug** — open a [bug report](https://github.com/Aarav261/Ontracker/issues/new?template=bug_report.md).
- **Suggest a feature** — open a [feature request](https://github.com/Aarav261/Ontracker/issues/new?template=feature_request.md).
- **Submit code** — fix a bug, add a feature, improve docs. See the workflow below.
- **Report a security issue** — please **do not** open a public issue; see [SECURITY.md](SECURITY.md).

If you're planning a non-trivial change, please open an issue first to discuss it so
we don't duplicate effort.

---

## Project layout

| Area | Path | Stack |
|------|------|-------|
| Backend (API + scheduler) | `app.py`, `core/`, `routes/` | Flask · APScheduler · SQLAlchemy |
| Web app (sign-in host) | `web/` | React 18 + Vite |
| Chrome extension (MV3) | `extension/` | React 18 + Vite |
| Tests | `tests/` | pytest |

---

## Local development setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker (for the backend + Postgres), or SQLite for a lighter setup

### 1. Clone and configure
```bash
git clone https://github.com/Aarav261/Ontracker.git
cd Ontracker
cp .env.example .env.dev   # then fill in the values
```
See [`.env.example`](.env.example) for every variable. You'll need your own
Clerk, Resend, and (optionally) Postgres credentials — none are provided.

### 2. Backend
```bash
# With Docker (backend + Postgres, reads .env.dev)
docker compose up -d --build

# Or run directly against SQLite
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

### 3. Web app
```bash
cd web && npm install && npm run dev    # http://localhost:5173
```

### 4. Extension
```bash
cd extension && npm install && npm run build    # dev build -> extension/dist
```
Load `extension/dist` via **chrome://extensions → Load unpacked**.

---

## Code style & checks

Run these locally before opening a PR — CI runs the same checks.

```bash
# Python: lint (ruff) — enforced in CI
ruff check .

# Python tests
pip install pytest
pytest

# Extension: lint
cd extension && npm run lint
```

- Python: line length 100, target py311. Config in [`ruff.toml`](ruff.toml).
- `ruff format .` is available if you'd like autoformatting, but it isn't enforced —
  match the style of the surrounding code and keep changes focused.

---

## Pull request workflow

1. **Fork** the repo and create a branch off `main`:
   `git checkout -b fix/short-description`
2. Make your change, with tests where it makes sense.
3. Ensure `ruff check .`, `pytest`, and `npm run lint` (in `extension/`) all pass.
4. Commit with a clear message and open a PR against `main`, filling in the
   PR template.
5. A maintainer will review. Please be responsive to feedback.

Keep PRs small and single-purpose where possible — they're far easier to review
and merge.

---

## Commit messages

Use clear, imperative subject lines, optionally with a type prefix you'll see in
the history, e.g.:

```
feat(extension): capture rotated token from response headers
fix(brief): don't skip users with no captured tasks on cold start
docs: clarify local setup in CONTRIBUTING
```

---

## Questions

Open a [discussion or issue](https://github.com/Aarav261/Ontracker/issues) — happy
to help you get started.
