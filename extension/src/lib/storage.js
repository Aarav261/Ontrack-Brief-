// Promise wrappers around chrome.storage.local's callback API, so callers can
// `await` reads/writes instead of nesting callbacks.

export function getLocal(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, resolve))
}

export function setLocal(items) {
  return new Promise((resolve) => chrome.storage.local.set(items, resolve))
}

export function removeLocal(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, resolve))
}
