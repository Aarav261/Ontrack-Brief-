// Tiny fetch wrapper — the "HttpClient" pattern without the dependency.
//
// Centralises the base URL, JSON in/out, a request timeout, and uniform errors:
// like axios, it REJECTS on a non-2xx response, attaching `.status` and the
// parsed `.data` to the thrown Error so callers can branch on them. A genuine
// network failure / timeout rejects without `.data`.
//
// Not used by background.js — that's a service worker loaded via importScripts
// and can't import this module; it keeps native fetch.

const DEFAULT_TIMEOUT_MS = 10000

export async function api(
  path,
  { method = 'GET', body, timeout = DEFAULT_TIMEOUT_MS } = {}
) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  try {
    const res = await fetch(`${window.APP_URL}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })

    // Tolerate empty / non-JSON bodies (e.g. the /unsubscribe HTML page).
    const data = await res.json().catch(() => ({}))

    if (!res.ok) {
      throw Object.assign(new Error(data.error || `HTTP ${res.status}`), {
        status: res.status,
        data,
      })
    }

    return data
  } finally {
    clearTimeout(timer)
  }
}
