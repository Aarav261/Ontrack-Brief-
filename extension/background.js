/**
 * Background service worker.
 * Token capture is handled by content.js + injected.js.
 * This worker just stays registered so the popup can wake it if needed.
 */

chrome.runtime.onInstalled.addListener(() => {
  console.debug("[OnTrack Brief] Extension installed/updated.");
});
