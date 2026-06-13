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
    await fetch(`${APP_URL}/refresh-credential`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, refresh_token: cookie.value }),
    });
  } catch {
    /* cookie unavailable or server unreachable — the rotating-token push still works */
  }
}

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
