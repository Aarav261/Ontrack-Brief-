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

  // ── Data capture ──────────────────────────────────────────────────────────
  // Read the RESPONSE BODIES of OnTrack's data endpoints and forward them to the
  // extension, which POSTs them to the app's /ingest. This is what lets the brief
  // run off stored data instead of calling OnTrack — see DETERMINISTIC_BRIEF_PLAN.
  let lastStudentId = null;
  const tasksByUnit = {}; // unit_id → { project_id, tasks }   (from /api/projects/{id})
  const defsByUnit  = {}; // unit_id → task_definitions          (from /api/units/{id})

  function pathOf(rawUrl) {
    try { return new URL(rawUrl, location.origin).pathname; } catch { return ""; }
  }

  // Cheap gate so we only JSON-parse the handful of endpoints we care about.
  function isDataUrl(rawUrl) {
    const p = pathOf(rawUrl);
    return (
      p === "/api/projects" ||
      /^\/api\/projects\/\d+$/.test(p) ||
      /^\/api\/units\/\d+$/.test(p) ||
      /\/api\/projects\/\d+\/task_def_id\/\d+\/comments$/.test(p)
    );
  }

  function emitData(kind, payload) {
    window.dispatchEvent(
      new CustomEvent("ontrack-data-captured", { detail: { kind, payload } })
    );
  }

  // project_tasks must carry BOTH the tasks (for real statuses) and the unit's
  // task_definitions (to synthesise not-yet-started tasks). They arrive in two
  // responses, so pair them by unit_id and only emit once both are in hand —
  // otherwise a definitions-only push would overwrite a submitted task's status.
  function maybeEmitProjectTasks(unitId) {
    const t = tasksByUnit[unitId];
    const d = defsByUnit[unitId];
    if (t && d) {
      emitData("project_tasks", {
        project_id: t.project_id,
        tasks: t.tasks,
        task_definitions: d,
      });
    }
  }

  function handleData(rawUrl, data) {
    const p = pathOf(rawUrl);
    let m;

    if (p === "/api/projects" && Array.isArray(data)) {
      if (data.length && data[0].user && data[0].user.id) {
        lastStudentId = data[0].user.id; // needed to skip the student's own comments
      }
      emitData("projects", data);
    } else if ((m = p.match(/^\/api\/projects\/(\d+)$/))) {
      const unitId = data.unit_id || (data.unit && data.unit.id);
      if (unitId == null) return;
      tasksByUnit[unitId] = { project_id: Number(m[1]), tasks: data.tasks || [] };
      maybeEmitProjectTasks(unitId);
    } else if ((m = p.match(/^\/api\/units\/(\d+)$/))) {
      defsByUnit[Number(m[1])] = data.task_definitions || [];
      maybeEmitProjectTasks(Number(m[1]));
    } else if ((m = p.match(/\/api\/projects\/(\d+)\/task_def_id\/(\d+)\/comments$/))) {
      emitData("feedback", {
        project_id: Number(m[1]),
        task_def_id: Number(m[2]),
        comments: data,
        student_id: lastStudentId,
      });
    }
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
    this._url = url;
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

      // Capture the response body for the data endpoints we care about.
      try {
        if (isDataUrl(this._url)) handleData(this._url, JSON.parse(this.responseText));
      } catch { /* non-JSON / unreadable body — ignore */ }
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
      } catch { /* response without readable headers — ignore */ }

      // Clone before reading so the page still receives its own body.
      try {
        const url = typeof input === "string" ? input : (input && input.url);
        if (url && isDataUrl(url)) {
          response.clone().json().then((d) => handleData(url, d)).catch(() => {});
        }
      } catch { /* unreadable body — ignore */ }
      return response;
    });
  };
})();
