/**
 * Runs in the OnTrack page context (not the extension sandbox).
 * Captures the rotated Auth-Token from RESPONSE headers — Doubtfire returns
 * a new token on every response, so reading request headers gives a stale value.
 */
(function () {
  let lastToken    = null;
  let lastUsername = null;

  function emit(token, username) {
    if (!token || !username) return;
    if (token === lastToken && username === lastUsername) return;
    lastToken    = token;
    lastUsername = username;
    window.dispatchEvent(new CustomEvent("ontrack-auth-captured", {
      detail: { auth_token: token, username: username }
    }));
  }

  // Track username from outgoing request headers (it never rotates)
  function extractUsername(headers) {
    if (!headers) return null;
    if (headers instanceof Headers) return headers.get("Username") || headers.get("username");
    return headers["Username"] || headers["username"] || null;
  }

  // ── Intercept XMLHttpRequest ──────────────────────────────────────────────
  const _setHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    if (!this._capturedHeaders) this._capturedHeaders = {};
    this._capturedHeaders[name.toLowerCase()] = value;
    return _setHeader.apply(this, arguments);
  };

  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.addEventListener("load", () => {
      // Prefer rotated token from response headers
      const respToken = this.getResponseHeader("Auth-Token")
        || this.getResponseHeader("auth-token")
        || this.getResponseHeader("x-auth-token");
      const h        = this._capturedHeaders || {};
      const username = h["username"] || lastUsername;
      if (respToken && username) {
        emit(respToken, username);
      } else {
        // Fallback: use request token (first page load before any response)
        emit(h["auth-token"], h["username"]);
      }
    });
    return _open.apply(this, arguments);
  };

  // ── Intercept fetch ───────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = function (input, init = {}) {
    const username = extractUsername(init.headers) || lastUsername;

    return _fetch.apply(this, arguments).then((response) => {
      try {
        const respToken = response.headers.get("Auth-Token")
          || response.headers.get("auth-token")
          || response.headers.get("x-auth-token");
        if (respToken && username) emit(respToken, username);
      } catch (_) {}
      return response;
    });
  };
})();
