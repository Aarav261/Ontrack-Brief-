/**
 * Runs in the OnTrack page context (not the extension sandbox).
 * Intercepts XHR and fetch requests to capture the real Auth-Token header
 * that OnTrack's Angular app uses — this is the long-lived token, not the
 * short-lived one from POST /api/auth/access-token.
 */
(function () {
  let lastToken = null;
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

  // ── Intercept XMLHttpRequest ──────────────────────────────────────────────
  const _setHeader = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (name, value) {
    if (!this._capturedHeaders) this._capturedHeaders = {};
    this._capturedHeaders[name.toLowerCase()] = value;
    return _setHeader.apply(this, arguments);
  };

  const _open = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    this.addEventListener("loadstart", () => {
      const h = this._capturedHeaders || {};
      emit(h["auth-token"], h["username"]);
    });
    return _open.apply(this, arguments);
  };

  // ── Intercept fetch ───────────────────────────────────────────────────────
  const _fetch = window.fetch;
  window.fetch = function (input, init = {}) {
    try {
      const headers = init.headers || {};
      const get = (key) =>
        headers instanceof Headers
          ? headers.get(key)
          : headers[key] || headers[key.toLowerCase()];
      emit(get("Auth-Token") || get("auth-token"),
           get("Username")   || get("username"));
    } catch (_) {}
    return _fetch.apply(this, arguments);
  };
})();
