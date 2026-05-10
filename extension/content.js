/**
 * Content script — injects the XHR/fetch interceptor into the OnTrack page
 * and forwards captured tokens to the extension storage + app server.
 */

const APP_URL = "http://localhost:5001";  // Change to deployed URL when hosted

// Inject interceptor into page context
const script = document.createElement("script");
script.src = chrome.runtime.getURL("injected.js");
(document.head || document.documentElement).appendChild(script);
script.remove();

// Listen for tokens captured by the interceptor
window.addEventListener("ontrack-auth-captured", (event) => {
  const { auth_token, username } = event.detail;
  if (!auth_token || !username) return;

  const base_url = window.location.origin;

  // Store in chrome.storage so popup can read it
  chrome.storage.local.set({ auth_token, username, base_url });

  // Route through background worker to avoid mixed-content blocking
  // (content script runs on HTTPS OnTrack; app server is HTTP localhost)
  chrome.runtime.sendMessage({ type: "refresh-token", auth_token, username })
    .catch(() => {});
});
