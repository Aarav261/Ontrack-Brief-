/**
 * Background service worker — intercepts OnTrack API requests and reads
 * the real Auth-Token and Username headers the web app sends.
 * This captures the exact same credentials the OnTrack web app uses,
 * which are long-lived and managed by OnTrack's own session.
 */

const APP_URL = "http://localhost:5001";  // Change to deployed URL when hosted

const seen = { token: null, username: null };

chrome.webRequest.onSendHeaders.addListener(
  (details) => {
    let token = null;
    let username = null;

    for (const header of details.requestHeaders || []) {
      const name = header.name.toLowerCase();
      if (name === "auth-token")  token    = header.value;
      if (name === "username")    username = header.value;
    }

    if (!token || !username) return;
    // Only push if something changed — avoid hammering the server
    if (token === seen.token && username === seen.username) return;

    seen.token    = token;
    seen.username = username;

    // Store in chrome.storage so popup.js can read them
    chrome.storage.local.set({
      auth_token: token,
      username:   username,
      base_url:   new URL(details.url).origin,
    });

    fetch(`${APP_URL}/refresh-token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, auth_token: token }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) console.debug("[OnTrack Brief] Token refreshed for", username);
      })
      .catch(() => {
        // App server not running — fail silently
      });
  },
  { urls: ["https://ontrack.deakin.edu.au/api/*"] },
  ["requestHeaders"]
);
