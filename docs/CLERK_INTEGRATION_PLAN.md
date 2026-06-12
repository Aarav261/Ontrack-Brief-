# Clerk Integration Plan — OnTrack Brief

Status: **Draft / proposal**
Last updated: 2026-06-09
Owner: @Aarav261

---

## 1. Goal

Replace the current ad‑hoc identity model (a user *is* their OnTrack `username`, email collected
separately, API endpoints unauthenticated) with **Clerk** as the user‑management and authentication
system. After this work:

- Users sign in to the extension with Clerk (Google / email — social providers configurable in Clerk).
- The backend authenticates every protected request by verifying a Clerk session JWT.
- A user's email (the brief recipient) is the **verified email from Clerk**, not a free‑text field.
- The OnTrack rotating token is *linked to* a Clerk user, not the identity itself.

## 2. The one concept to keep straight: identity ≠ OnTrack credential

These are **orthogonal** and must stay separate in the design:

| Concern | What it proves / does | Owned by | Stored as |
| --- | --- | --- | --- |
| **App identity** (Clerk) | Who the user is, for *our* app | Clerk | `clerk_user_id` (+ verified email) |
| **OnTrack access** | Lets *our server* call OnTrack as the student | Us | encrypted `auth_token` (already done) |

Clerk does **not** remove the need to store the OnTrack token — the daily brief job runs at 08:00 while
the user is away, so the server must still hold an OnTrack credential. Clerk only replaces *how a user
identifies themselves to us* and *where the brief email comes from*. Don't let "I added Clerk" imply the
credential‑custody problem disappeared; it doesn't (see `core/crypto.py`, already in place).

## 3. Current state (what we're changing)

- **Frontend:** MV3 Chrome extension only (`extension/`, React + Vite). No separate web app.
  - Popup: `extension/src/App.jsx`, components under `extension/src/components/`.
  - API wrapper: `extension/src/lib/api.js` (no auth header today).
  - A content script on `ontrack.deakin.edu.au` scrapes the rotating `auth_token` into `chrome.storage.local`.
- **Backend:** Flask (`app.py` → `routes/main.py`), APScheduler jobs (`core/jobs.py`), DB layer (`core/db.py`).
  - Identity keyed on OnTrack `username`; `users.email` is `UNIQUE` and supplied by the user.
  - Endpoints `/register`, `/setup`, `/refresh-token`, `/api/snapshot`, `/unsubscribe/<email>` are
    **unauthenticated** (only `flask-limiter` rate limits).
- **Security baseline:** OnTrack token now encrypted at rest (`core/crypto.py`, `TOKEN_ENCRYPTION_KEY`).

## 4. Target architecture

```
┌──── Landing page @ on-tracker.com (Vite+React SPA) ────┐
│  <ClerkProvider>  <SignIn/> <SignUp/>  /unsubscribe    │
│  Interactive auth happens HERE (Google / email)        │
└───────────────────────────┬────────────────────────────┘
                            │ session synced via Clerk syncHost
                            ▼
┌─────────────────────────── Chrome Extension (MV3) ───────────────────────────┐
│  Popup (React)                          Content script @ ontrack.deakin.edu.au │
│  ┌───────────────────────────┐          ┌────────────────────────────────────┐│
│  │ @clerk/chrome-extension   │          │ scrapes rotating OnTrack auth_token ││
│  │  syncHost → on-tracker.com │          └───────────────┬────────────────────┘│
│  │  <UserButton/> getToken() │                          │ (no Clerk ctx here)  │
│  └────────────┬──────────────┘                          ▼                      │
│               │ Authorization: Bearer <clerk_jwt>   background service worker  │
│               │                                     holds Clerk token, signs   │
│               ▼                                     POST /link-ontrack         │
└───────────────┼─────────────────────────────────────────┬────────────────────┘
                │                                          │
                ▼                                          ▼
┌──────────────────────────────── Flask backend ──────────────────────────────┐
│  @require_clerk_auth  →  verify JWT via Clerk JWKS  →  g.clerk_user_id        │
│  /api/snapshot  /settings  /link-ontrack  /unsubscribe                        │
│  /webhooks/clerk  ← Svix-signed user.created / user.deleted                   │
│  users(clerk_user_id PK-ish, email, base_url, username, auth_token[enc], …)   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 5. Decisions & assumptions

These are the defaults this plan assumes. Flagged ⚠️ where you may want to decide otherwise.

1. **Token verification method:** verify Clerk session JWTs in Flask using Clerk's JWKS endpoint
   (networkless verification with cached keys via `PyJWT` + `PyJWKClient`), rather than calling Clerk's
   API per request. Lower latency, no extra dependency on Clerk uptime for reads.
   - Alternative: official `clerk-backend-api` Python SDK (`authenticate_request`). Slightly heavier but
     handles clock skew, networkless mode, and rotation for you. ⚠️ Pick one — plan covers JWKS path,
     notes SDK swap.
2. **Identity key:** `clerk_user_id` (Clerk's `sub`) becomes the canonical user key. `email` stays for the
   brief recipient but is sourced from Clerk and no longer user‑editable.
3. **OnTrack linking flow:** sign in with Clerk *first*, then link OnTrack by visiting OnTrack so the
   content script captures the token and pushes it **with the Clerk JWT attached**.
4. **Webhooks:** use Clerk → Svix webhooks for `user.deleted` (cleanup) and optionally `user.created`.
   ⚠️ Requires a public HTTPS URL for the backend (already deployed on Azure per manifest host perms).
5. **Single Clerk instance** with Google enabled (and email as fallback). MFA optional, off by default.
6. **Companion landing page hosts sign-in.** A minimal Vite + React SPA at `on-tracker.com` is the
   canonical Clerk auth surface. The extension does **not** run interactive auth itself — it uses Clerk's
   `syncHost` to read the session established on the web domain. This sidesteps the project's biggest risk
   (full `@clerk/chrome-extension` auth inside the MV3 popup/service worker — see §13). The page is
   intentionally small: marketing/install, the Clerk `<SignIn/>`/`<SignUp/>` route, and an unsubscribe
   landing. It is **not** a dashboard — brief settings (hour, weeks) stay in the extension popup.

## 6. Backend changes (Flask)

### 6.1 Dependencies
- Add to `requirements.txt`: `PyJWT[crypto]~=2.8` (JWKS path) **or** `clerk-backend-api` (SDK path).
- Add env vars (see §9).

### 6.2 New module: `core/clerk_auth.py`
- `verify_session_token(token: str) -> dict` — validates a Clerk JWT against the instance JWKS
  (`https://<frontend-api>/.well-known/jwks.json`), checks `exp`/`nbf`/`azp`/issuer, returns claims.
- Cache the JWKS client (keys rotate rarely; refresh on `kid` miss).
- `require_clerk_auth` Flask decorator: reads `Authorization: Bearer <jwt>`, verifies, stashes
  `g.clerk_user_id = claims["sub"]` and `g.clerk_email = <primary email claim>`; returns `401` on failure.
  - Configure the Clerk JWT template to include the primary email, or look it up via webhook‑synced data.

### 6.3 Schema migration: `core/db.py`
Add identity columns to `users` and make `clerk_user_id` the lookup key (keep existing migration pattern —
idempotent `ADD COLUMN` for both SQLite and Postgres branches):

```
clerk_user_id   TEXT UNIQUE        -- Clerk `sub`; canonical identity
-- email stays, now sourced from Clerk; relax/keep UNIQUE per dedup needs
```

New/changed DB functions:
- `get_user_by_clerk_id(clerk_user_id)` — primary lookup going forward.
- `upsert_user(...)` — accept `clerk_user_id`; conflict target becomes `clerk_user_id` (not `email`).
  ⚠️ Changing the conflict target is a behavioural change — see migration (§8).
- Keep `get_user_by_username` during transition for the content‑script path until linking is fully Clerk‑gated.

### 6.4 Route changes: `routes/main.py`
- Apply `@require_clerk_auth` to: `/api/snapshot`, `/setup`, `/unsubscribe`, and a new `/link-ontrack`.
- **`/register` → folded into `/link-ontrack`:** identity now comes from the verified JWT, not the body.
  Body carries only OnTrack `base_url`, `username`, `auth_token`; email comes from Clerk claims.
- **`/refresh-token` / `/link-ontrack`:** require the Clerk JWT; resolve the row by `g.clerk_user_id`,
  store the (encrypted) OnTrack token against that user. Drop trust in body‑supplied `username` as identity.
- **`/api/snapshot`:** look up the user by `g.clerk_user_id` instead of body `username`; the body no longer
  needs to carry `auth_token` (server already holds it). Keep the stale‑snapshot fallback.
- **`/unsubscribe`:** key off `g.clerk_user_id`, not an email in the URL (prevents enumerating/unsubscribing
  others). Keep an email‑link unsubscribe variant only if email footer links require it — if so, sign it.

### 6.5 New route: `/webhooks/clerk` (`routes/webhooks.py`)
- Verify Svix signature (`svix` package) using `CLERK_WEBHOOK_SECRET`.
- Handle `user.deleted` → `remove_user(clerk_user_id)` + unschedule brief job (`scheduler.remove_job`).
- Optionally `user.updated` → sync email changes onto the row.

### 6.6 Jobs: `core/jobs.py`
- Brief job already iterates DB users — minimal change. Ensure the recipient email is the Clerk‑sourced
  `user["email"]`. Job IDs can stay `brief_{user_id}` (internal PK) or move to `brief_{clerk_user_id}`.

## 7. Frontend changes

There are now **two** frontends: the landing page (where the user signs in) and the extension (which
syncs that session). The landing page owns interactive auth; the extension is a consumer.

### 7.0 Landing page (new) — `web/` (Vite + React SPA, deployed at `on-tracker.com`)
- `<ClerkProvider publishableKey={VITE_CLERK_PUBLISHABLE_KEY}>` wrapping the app.
- Routes: `/` (marketing + "Add to Chrome"), `/sign-in` + `/sign-up` (Clerk components),
  `/unsubscribe` (landing for email-footer links; calls the backend unsubscribe endpoint).
- This is the **`syncHost` target** the extension points at. Add the extension's origin to Clerk's
  allowed origins so the session can sync.
- Deploy as static build (Railway static service / Vercel / Netlify). Add the domain to the Clerk instance.

### 7.1 Extension dependencies & setup
- Add `@clerk/chrome-extension` to `extension/`.
- Wrap the popup in `<ClerkProvider>` with the **publishable key** (`VITE_CLERK_PUBLISHABLE_KEY`) and
  **`syncHost: "https://on-tracker.com"`** so the popup reads the session signed in on the web page,
  plus the `chrome.storage` token cache the SDK requires for MV3.
- If no session is present, the popup shows a "Sign in at on-tracker.com" CTA that opens the landing
  page in a tab rather than rendering `<SignIn/>` inline.

### 7.2 `manifest.json`
- Add a stable extension **`key`** (so the extension ID is fixed — Clerk allow‑lists it).
- Add Clerk Frontend API to `host_permissions` (e.g. `https://<slug>.clerk.accounts.dev/*` and prod domain).
- Keep `storage`; the SDK persists the Clerk session in `chrome.storage`.

### 7.3 UI
- Replace the email‑entry `SignupFlow.jsx`. The popup no longer renders `<SignIn/>` inline — when
  signed out it shows a CTA that opens `on-tracker.com/sign-in` (auth happens on the web page, syncs back
  via `syncHost`). Add `<UserButton/>` to `Header.jsx` for the signed‑in state.
- New gating in `App.jsx`'s `view` state machine:
  `signed-out → "Sign in at on-tracker.com" CTA` · `signed-in but no OnTrack token → "open OnTrack to
  link"` · `linked → snapshot`.
- `Settings.jsx`: email is now read‑only (from Clerk); keep brief hour / weeks controls.

### 7.4 Authenticated API calls — `extension/src/lib/api.js`
- Before each call, get a fresh JWT via the SDK's `getToken()` and send `Authorization: Bearer <jwt>`.
- Drop `username`/`auth_token` from request bodies where the server now derives identity from the JWT.

### 7.5 The content‑script problem (most important)
The content script on `ontrack.deakin.edu.au` is **outside** the popup's Clerk context, so it can't call
`getToken()` directly. Flow:
1. Content script scrapes the OnTrack token (unchanged) and `sendMessage`s it to the **background service
   worker**.
2. The background worker — which *can* host the Clerk SDK / read the cached session — attaches the Clerk
   JWT and POSTs `/link-ontrack`.
3. If no Clerk session exists yet, stash the scraped token in `chrome.storage` and surface "sign in to link"
   in the popup; flush on next sign‑in.

⚠️ This is the riskiest piece — validate Clerk's background/service‑worker support for MV3 early with a spike.

## 8. Migration of existing users

Existing rows are keyed by `email`/`username` with **no** `clerk_user_id`.

1. Ship schema with `clerk_user_id` nullable; keep `username` lookups working (dual‑path).
2. On first authenticated request, **link by email**: if a row exists with the Clerk‑verified email and a
   null `clerk_user_id`, attach the `clerk_user_id` to it (claim the legacy row). Otherwise create a new row.
3. After a deprecation window, make `clerk_user_id` required and remove the `username`‑as‑identity paths.
4. Communicate to existing users that they must sign in once to keep receiving briefs (briefs for unlinked
   rows can continue during the window, then pause).

## 9. Configuration / env vars

| Var | Where | Purpose |
| --- | --- | --- |
| `VITE_CLERK_PUBLISHABLE_KEY` | extension + web build | Clerk frontend SDK (same key both surfaces) |
| `CLERK_SECRET_KEY` | backend | only if using `clerk-backend-api` SDK path |
| `CLERK_JWT_ISSUER` / frontend API URL | backend | JWKS + issuer validation |
| `CLERK_WEBHOOK_SECRET` | backend | verify Svix webhook signatures |
| `TOKEN_ENCRYPTION_KEY` | backend | (already added) encrypt OnTrack token at rest |

Add a `.env.example` documenting all of the above alongside `SECRET_KEY` / `DATABASE_URL`.

## 10. Security considerations

- **Verify, don't trust:** every protected route must derive identity from the verified JWT (`g.clerk_user_id`),
  never from a body field. This closes today's gap where any caller can pass any `username`.
- **CORS:** `app.py` currently sets `origins: "*"`. Tighten to the extension origin
  (`chrome-extension://<id>`) and the Clerk domains once the extension ID is stable.
- **Webhook auth:** reject unsigned/invalid Svix payloads; never act on webhook data without signature check.
- **Least data:** request only identity scopes; do **not** store Clerk session tokens server‑side.
- **OnTrack token:** stays encrypted at rest; unaffected by Clerk but now only reachable by the owning
  Clerk user.
- **Token template:** if embedding email in the JWT, keep the template minimal; treat the JWT as short‑lived.

## 11. Testing

- Unit: `verify_session_token` (valid, expired, wrong issuer, bad signature, unknown `kid`).
- Unit: `require_clerk_auth` decorator (401 paths, `g` population).
- Unit: webhook signature verify (valid/invalid), `user.deleted` cleanup.
- Integration: `/api/snapshot` and `/link-ontrack` with a mock/real Clerk JWT; legacy‑email migration path.
- Manual: full extension flow — sign in → open OnTrack → token linked → snapshot → daily brief fires.

## 12. Phased rollout

- **Phase 0 — Spike (de‑risk):** stand up the landing page with Clerk `<SignIn/>`, then prove the
  extension popup can read that session via `syncHost` and attach a JWT to one protected route. Output: a
  throwaway branch that signs in *on the web page* and makes one authenticated call from the extension.
- **Phase 1 — Backend auth:** `core/clerk_auth.py`, schema `clerk_user_id`, JWKS verification, protect
  `/api/snapshot` behind auth while keeping a legacy fallback. No UI change yet.
- **Phase 2 — Landing page + extension auth:** build the `web/` SPA (marketing, Clerk sign‑in, unsubscribe);
  wire the extension's `syncHost`, signed‑in gating, JWT on API calls, and the content‑script → background
  linking flow.
- **Phase 3 — Webhooks + migration:** `/webhooks/clerk`, email‑based claiming of legacy rows, comms.
- **Phase 4 — Cleanup:** remove `username`‑as‑identity paths, tighten CORS, make `clerk_user_id` required.

## 13. Risks & open questions

- ⚠️ **Clerk in MV3 + service worker** is the biggest unknown. The landing‑page + `syncHost` approach
  (§5.6) is chosen specifically to reduce this: interactive auth runs on the web page, the extension only
  reads the synced session. Still validate the `syncHost` read path in Phase 0 before committing.
- ⚠️ **Conflict‑target change** in `upsert_user` (email → clerk_user_id) touches every write path; needs the
  dual‑path migration to avoid breaking existing users.
- ⚠️ **Cost/complexity:** Clerk is a hosted dependency with its own pricing/limits; for a single‑user or
  small tool this is heavier than the Authlib‑OIDC option discussed earlier. Confirm the scale justifies it.
- ❓ Do email‑footer unsubscribe links need to work without a signed‑in session? If yes, keep a signed
  email‑token unsubscribe path.
- ❓ JWKS verification vs. official SDK — pick one before Phase 1.
- ❓ Should the OnTrack `username` still be displayed/stored, or fully replaced by Clerk profile?

## 14. Rough effort

| Phase | Estimate |
| --- | --- |
| 0 — Spike | 0.5–1 day |
| 1 — Backend auth | 1–2 days |
| 2 — Landing page + extension auth | 3–4 days (landing page ~1 day; content‑script flow is the long pole) |
| 3 — Webhooks + migration | 1–2 days |
| 4 — Cleanup | 0.5–1 day |

---

*This is a plan, not an implementation. Recommended next step: Phase 0 spike to confirm
`@clerk/chrome-extension` works in this MV3 setup before any backend or schema changes.*
