/**
 * Runs on every OnTrack page load.
 * Silently fetches a fresh auth token and pushes it to the OnTrack Brief server.
 * No user interaction needed after initial setup.
 */

const APP_URL = "http://localhost:5001";  // Change to your deployed URL when hosted

function pushToken(token, username) {
  fetch(`${APP_URL}/refresh-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, auth_token: token }),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) {
        console.debug("[OnTrack Brief] Token refreshed for", username);
      } else {
        console.debug("[OnTrack Brief] Not subscribed:", d.error);
      }
    })
    .catch(() => {
      // App server not running — fail silently
    });
}

function refreshToken() {
  fetch("/api/auth/access-token", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ delete_auth_token: false }),
  })
    .then((r) => {
      if (!r.ok) return null;
      return r.json();
    })
    .then((d) => {
      if (!d) return;
      const token = d.auth_token || d.access_token || d.token;
      const user  = d.user || {};
      const username = user.username || user.email || "";
      if (token && username) {
        pushToken(token, username);
      }
    })
    .catch(() => {
      // Not logged in yet — fail silently, will retry on next page load
    });
}

// Small delay to let the page finish authenticating before we call the API
setTimeout(refreshToken, 2000);
