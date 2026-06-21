/**
 * Content script — injects the XHR/fetch interceptor into the OnTrack page
 * and forwards captured tokens to the extension storage + app server.
 */

// APP_URL is defined in config.js, loaded before this script via manifest.json

// Inject interceptor into page context
const script = document.createElement("script");
script.src = chrome.runtime.getURL("injected.js");
(document.head || document.documentElement).appendChild(script);
script.remove();

// Remember the username the moment it's captured, so a data push that fires
// before chrome.storage has settled still has an identity to attach.
let knownUsername = null;

// Listen for tokens captured by the interceptor
window.addEventListener("ontrack-auth-captured", (event) => {
  const { auth_token, username } = event.detail;
  if (!auth_token || !username) return;

  knownUsername = username;
  const base_url = window.location.origin;

  // Store in chrome.storage so popup can read it
  chrome.storage.local.set({ auth_token, username, base_url });

  // Route through background worker to avoid mixed-content blocking
  // (content script runs on HTTPS OnTrack; app server is HTTP localhost)
  chrome.runtime.sendMessage({ type: "refresh-token", auth_token, username })
    .catch(() => {});
});

// Listen for data captured by the interceptor and forward it to the app's
// /ingest (via background, same mixed-content reason as the token push).
window.addEventListener("ontrack-data-captured", (event) => {
  const { kind, payload } = event.detail || {};
  if (!kind) return;

  function send(username) {
    if (!username) return; // not linked yet — a later capture will carry identity
    chrome.runtime
      .sendMessage({ type: "ingest", username, kind, payload })
      .catch(() => {});
  }

  if (knownUsername) {
    send(knownUsername);
  } else {
    chrome.storage.local.get("username", ({ username }) => send(username));
  }
});
