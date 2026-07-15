// APP_URL is defined in config.js, loaded via importScripts below
importScripts("config.js");

const ONTRACK_URL = "https://ontrack.deakin.edu.au";

chrome.runtime.onInstalled.addListener(() => {
});

// Read the durable refresh_token cookie (HttpOnly — only chrome.cookies can see
// it, not document.cookie) and push it so the server can mint fresh auth_tokens
// on demand. This is what keeps briefs working after overnight idle.
async function pushRefreshToken(username) {
  try {
    const cookie = await chrome.cookies.get({
      url: `${ONTRACK_URL}/api/auth`,
      name: "refresh_token",
    });
    if (!cookie || !cookie.value) return;
    // Stash it where the popup can read it (the cookie is HttpOnly, so the popup
    // can't read it directly) — App.jsx passes it to /link-ontrack so a brand-new
    // user's row is created WITH a refresh_token, instead of waiting for a later
    // /refresh-credential push that 404s until the row exists.
    chrome.storage.local.set({ refresh_token: cookie.value });
    await fetch(`${APP_URL}/refresh-credential`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, refresh_token: cookie.value }),
    });
  } catch {
    /* cookie unavailable or server unreachable — the rotating-token push still works */
  }
}

// Re-login is the one thing that ROTATES the refresh_token: OnTrack issues a new
// one and invalidates the old, so any copy we already stored is instantly dead.
// Watch the cookie directly (event-driven — wakes the service worker on its own,
// no open popup needed) so the moment it changes we push the new value. The
// server's /refresh-credential then un-pauses any briefs that were paused on the
// now-stale token. This is what makes a re-login self-heal with zero user action.
chrome.cookies.onChanged.addListener(({ cookie, removed }) => {
  if (removed) return;
  if (cookie.name !== "refresh_token") return;
  if (!cookie.domain.includes("ontrack.deakin.edu.au")) return;
  chrome.storage.local.get("username").then(({ username }) => {
    // username never changes across a re-login, so the stored one is still valid.
    if (username) pushRefreshToken(username);
  });
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "refresh-token") return false;

  // Push the durable refresh_token alongside the rotating auth_token.
  pushRefreshToken(msg.username);

  fetch(`${APP_URL}/refresh-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_token: msg.auth_token, username: msg.username }),
  })
    .then((r) => r.json())
    .then((d) => {
      sendResponse({ ok: true });
    })
    .catch(() => sendResponse({ ok: false }));

  return true; // keep message channel open for async response
});

// Dedup identical captures: OnTrack's SPA re-fetches the same project/unit data
// on every navigation, so without this the extension re-POSTs unchanged payloads
// and a single browsing session can trip the server's /ingest rate limit. Keyed
// by kind + the captured identifier; value is a hash of the payload so a real
// data change still pushes. Lives in the (ephemeral) service-worker scope — a
// worker restart just allows one harmless re-send.
const lastIngestHash = new Map();

function ingestDedupKey(kind, payload) {
  const p = payload || {};
  if (kind === "project_tasks") return `project_tasks:${p.project_id}`;
  if (kind === "feedback") return `feedback:${p.project_id}:${p.task_def_id}`;
  return kind; // "projects" — one per session
}

// Small, fast, collision-tolerant string hash (djb2). Exact equality isn't
// required — a missed dedup only costs one extra POST.
function hashPayload(payload) {
  const s = JSON.stringify(payload);
  let h = 5381;
  for (let i = 0; i < s.length; i++) h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  return `${s.length}:${h}`;
}

// Forward captured OnTrack data to /ingest. Separate listener so the token path
// above stays untouched; both run on every message and ignore kinds not theirs.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "ingest") return false;

  const dedupKey = ingestDedupKey(msg.kind, msg.payload);
  const hash = hashPayload(msg.payload);
  if (lastIngestHash.get(dedupKey) === hash) {
    sendResponse({ ok: true, deduped: true });
    return true;
  }
  // Do NOT cache the hash until the server confirms receipt — premature caching
  // would cause a failed push to be silently deduped away on the next retry.

  fetch(`${APP_URL}/ingest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: msg.username,
      kind: msg.kind,
      payload: msg.payload,
    }),
  })
    .then((r) => r.json())
    .then((d) => {
      // Only cache once the server actually stored it — a `skipped` response
      // (e.g. rejected as an inactive project) must not be treated as sent, or
      // this dedup would permanently suppress a push that never landed.
      if (!d || !d.skipped) lastIngestHash.set(dedupKey, hash);
      sendResponse({ ok: true });
    })
    .catch(() => {
      // Hash was never set, so the next identical capture will retry naturally.
      sendResponse({ ok: false });
    });

  return true; // async response
});
