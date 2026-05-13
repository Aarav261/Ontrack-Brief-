// APP_URL is defined in config.js, loaded via importScripts below
importScripts("config.js");

chrome.runtime.onInstalled.addListener(() => {
  console.debug("[OnTrack Brief] Extension installed/updated.");
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type !== "refresh-token") return false;

  fetch(`${APP_URL}/refresh-token`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ auth_token: msg.auth_token, username: msg.username }),
  })
    .then((r) => r.json())
    .then((d) => {
      if (d.ok) console.debug("[OnTrack Brief] Token refreshed for", msg.username);
      sendResponse({ ok: true });
    })
    .catch(() => sendResponse({ ok: false }));

  return true; // keep message channel open for async response
});
