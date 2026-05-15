// APP_URL is defined in config.js, loaded before this script via popup.html

const statusEl        = document.getElementById("status");
const statusText      = document.getElementById("status-text");
const statusDot       = statusEl.querySelector(".dot");
const subscribeBtn    = document.getElementById("subscribe-btn");
const emailInput      = document.getElementById("email");
const hourSelect      = document.getElementById("hour");
const recentlyDaysEl  = document.getElementById("recently-days");
const maxTodoEl       = document.getElementById("max-todo");
const msgEl           = document.getElementById("msg");
const unsubRow        = document.getElementById("unsubscribe-row");
const unsubLink       = document.getElementById("unsubscribe-link");
const snapshotSection = document.getElementById("snapshot-section");
const noAuthSection   = document.getElementById("no-auth-section");
const signupSection   = document.getElementById("signup-section");
const signupEmail     = document.getElementById("signup-email");
const signupBtn       = document.getElementById("signup-btn");
const signupMsg       = document.getElementById("signup-msg");
const skipSignup      = document.getElementById("skip-signup");
const stripLoading    = document.getElementById("strip-loading");
const stripRow        = document.getElementById("strip-row");
const stripTooltip    = document.getElementById("strip-tooltip");
const statUrgent      = document.getElementById("stat-urgent");
const statSoon        = document.getElementById("stat-soon");
const statTotal       = document.getElementById("stat-total");
const taskList        = document.getElementById("task-list");
const taskListSub     = document.getElementById("task-list-sub");
const footerSync      = document.getElementById("footer-sync");
const footerUser      = document.getElementById("footer-user");
const refreshBtn      = document.getElementById("refresh-btn");
const settingsBtn     = document.getElementById("settings-btn");
const tabMain         = document.getElementById("tab-main");
const tabSettings     = document.getElementById("tab-settings");
const stripWeeksEl    = document.getElementById("strip-weeks");

// ── State Machine ─────────────────────────────────────────────────

function updateView(data) {
  const hasToken = data.auth_token && data.username;
  const isSubscribed = !!data.subscribed_email;
  const skippedSignup = !!data.signup_skipped;

  noAuthSection.style.display = "none";
  signupSection.style.display = "none";
  snapshotSection.style.display = "none";

  if (!hasToken) {
    noAuthSection.style.display = "block";
    setStatus("warning", "Open OnTrack — your tasks will appear automatically");
  } else if (!isSubscribed && !skippedSignup) {
    signupSection.style.display = "block";
    setStatus("ok", `Logged in as ${data.username}`);
    footerUser.textContent = data.username;
  } else {
    snapshotSection.style.display = "block";
    setStatus("ok", `Logged in as ${data.username}`);
    footerUser.textContent = data.username;
    const weeks = parseInt(data.strip_weeks || "1", 10);
    loadSnapshot(data.auth_token, data.username, data.base_url, false, weeks * 7);
  }
}

// ── Tab switching ─────────────────────────────────────────────────
function switchTab(tab) {
  const onSettings = tab === "settings";
  tabMain.classList.toggle("active", !onSettings);
  tabSettings.classList.toggle("active", onSettings);
  settingsBtn.classList.toggle("active", onSettings);
}

settingsBtn.addEventListener("click", () => {
  const isSettings = tabSettings.classList.contains("active");
  switchTab(isSettings ? "main" : "settings");
});

stripWeeksEl.addEventListener("change", () => {
  const weeks = parseInt(stripWeeksEl.value, 10);
  chrome.storage.local.set({ strip_weeks: String(weeks) });
  if (_snapshotAuth) {
    chrome.storage.local.remove(SNAPSHOT_KEY, () => {
      loadSnapshot(_snapshotAuth.authToken, _snapshotAuth.username, _snapshotAuth.baseUrl, true, weeks * 7);
    });
  }
});

const SNAPSHOT_KEY    = "snapshot_cache";
const SNAPSHOT_TTL_MS = 30 * 60 * 1000;

const GRADE_SHORT = {
  "P (Pass)": "P", "C (Credit)": "C",
  "D (Distinction)": "D", "HD (High Distinction)": "HD",
};

const GRADE_COLOR = {
  "P (Pass)":             "#784212",
  "C (Credit)":           "#0e6655",
  "D (Distinction)":      "#1a5276",
  "HD (High Distinction)":"#6c3483",
};

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];

function formatDueDate(iso) {
  if (!iso) return "";
  const parts = iso.split("-");
  return `${parseInt(parts[2])} ${MONTHS[parseInt(parts[1]) - 1]}`;
}

function setStatus(type, text) {
  statusEl.className      = `status-pill ${type}`;
  statusDot.className     = `dot ${type}`;
  statusText.textContent  = text;
  statusEl.style.display  = type === "ok" ? "none" : "";
}

function showMsg(type, text) {
  msgEl.className   = `msg ${type}`;
  msgEl.textContent = text;
}

// ── Tooltip ───────────────────────────────────────────────────────

function showTooltip(e, day) {
  stripTooltip.innerHTML = day.tasks.map((t) =>
    `<span class="tt-task">` +
    `<span class="tt-unit">${t.unit}</span>` +
    `<span class="tt-name">${t.name}</span>` +
    `<span class="tt-grade">${GRADE_SHORT[t.grade] || t.grade}</span>` +
    `</span>`
  ).join("");
  stripTooltip.classList.add("visible");
  stripTooltip.removeAttribute("aria-hidden");

  requestAnimationFrame(() => {
    const col     = e.currentTarget;
    const section = stripRow.parentElement;
    const colRect = col.getBoundingClientRect();
    const secRect = section.getBoundingClientRect();
    const tipW    = stripTooltip.offsetWidth;
    const tipH    = stripTooltip.offsetHeight;
    const MARGIN  = 6, GAP = 6;

    let left = colRect.left - secRect.left + colRect.width / 2 - tipW / 2;
    left = Math.max(MARGIN, Math.min(left, secRect.width - tipW - MARGIN));
    const top = colRect.top - secRect.top - tipH - GAP;

    stripTooltip.style.left   = left + "px";
    stripTooltip.style.top    = top + "px";
    stripTooltip.style.bottom = "auto";
  });
}

function hideTooltip() {
  stripTooltip.classList.remove("visible");
  stripTooltip.setAttribute("aria-hidden", "true");
}

// ── Strip ─────────────────────────────────────────────────────────

function dotClass(offset, count) {
  if (count === 0) return "";
  return offset <= 3 ? "red" : "orange";
}

function renderStrip(days) {
  stripRow.innerHTML = "";
  stripRow.classList.toggle("two-week", days.length > 7);
  days.forEach((day) => {
    const count = day.tasks.length;
    const cls   = dotClass(day.offset, count);
    const col   = document.createElement("div");
    col.className = "strip-col" +
      (day.offset === 0 ? " today" : "") +
      (count > 0 ? " has-tasks" : "");
    const dateNum = day.date.slice(8);  // "DD" from "YYYY-MM-DD"
    col.innerHTML =
      `<span class="strip-day">${day.label}</span>` +
      `<span class="strip-date">${dateNum}</span>` +
      `<span class="strip-dot${cls ? " " + cls : ""}">${count > 0 ? count : ""}</span>`;
    if (count > 0) {
      col.addEventListener("mouseenter", (e) => showTooltip(e, day));
      col.addEventListener("mouseleave", hideTooltip);
    }
    stripRow.appendChild(col);
  });
  stripLoading.style.display = "none";
  stripRow.style.display     = days.length > 7 ? "grid" : "flex";
}

// ── Task list ─────────────────────────────────────────────────────

function dueLabel(offset) {
  if (offset === 0) return "due today";
  if (offset === 1) return "tomorrow";
  return `${offset}d left`;
}

function renderTasks(days) {
  const all = [];
  days.forEach((day) => {
    day.tasks.forEach((t) => all.push({ ...t, offset: day.offset }));
  });
  all.sort((a, b) => a.offset - b.offset);

  const urgent = all.filter((t) => t.offset <= 3).length;
  const soon   = all.filter((t) => t.offset >= 4).length;
  statUrgent.textContent = urgent;
  statSoon.textContent   = soon;
  statTotal.textContent  = all.length;
  taskListSub.textContent = all.length > 0 ? `${all.length} task${all.length !== 1 ? "s" : ""} due` : "";

  if (all.length === 0) {
    taskList.innerHTML = `<div class="task-empty">Nothing due in the next 7 days 🎉</div>`;
    return;
  }

  taskList.innerHTML = "";
  all.forEach((t) => {
    const cls      = t.offset <= 3 ? "red" : "orange";
    const barColor = t.offset <= 3 ? "#cb4335" : "#d68910";
    const barWidth = Math.max(8, 100 - t.offset * 13);
    const grade    = GRADE_SHORT[t.grade] || t.grade;
    const color    = GRADE_COLOR[t.grade] || "#555";

    const item = document.createElement("div");
    item.className = "task-item";
    item.innerHTML =
      `<div class="task-icon" style="color:${color};border-color:${color}">${grade}</div>` +
      `<div class="task-body">` +
        `<div class="task-name">${t.abbreviation} ${t.name}</div>` +
        `<div class="task-meta">${t.unit} · ${grade}</div>` +
        `<div class="task-bar-wrap">` +
          `<div class="task-bar" style="width:${barWidth}%;background:${barColor}"></div>` +
        `</div>` +
      `</div>` +
      `<div class="task-right">` +
        `<div class="task-due ${cls}">${dueLabel(t.offset)}</div>` +
        `<div class="task-date">${formatDueDate(t.due_date)}</div>` +
      `</div>`;
    taskList.appendChild(item);
  });
}

// ── Sync label ────────────────────────────────────────────────────

function syncLabel(ts) {
  const sec = Math.floor((Date.now() - ts) / 1000);
  if (sec < 60)  return `Synced ${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60)  return `Synced ${min}m ago`;
  return `Synced ${Math.floor(min / 60)}h ago`;
}

// ── Snapshot load ─────────────────────────────────────────────────

let _snapshotAuth = null;

function loadSnapshot(authToken, username, baseUrl, force = false, days = 7) {
  _snapshotAuth = { authToken, username, baseUrl, days };

  noAuthSection.style.display   = "none";
  snapshotSection.style.display = "block";
  stripLoading.style.display    = "flex";
  stripRow.style.display        = "none";

  chrome.storage.local.get([SNAPSHOT_KEY], (stored) => {
    const cached = stored[SNAPSHOT_KEY];
    if (!force && cached && cached.data && (Date.now() - cached.ts) < SNAPSHOT_TTL_MS) {
      renderStrip(cached.data.days);
      renderTasks(cached.data.days);
      footerSync.textContent = syncLabel(cached.ts);
      return;
    }

    const fetchP   = fetch(`${APP_URL}/api/snapshot`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username, auth_token: authToken,
        base_url: baseUrl || "https://ontrack.deakin.edu.au",
        days,
      }),
    });
    const timeoutP = new Promise((_, rej) =>
      setTimeout(() => rej(new Error("timeout")), 10000)
    );

    Promise.race([fetchP, timeoutP])
      .then((r) => {
        if (!r.ok) {
          return r.json().then((body) => {
            if (body.hint === "open_ontrack") {
              setStatus("warning", "Session expired — open OnTrack to refresh");
            }
            throw new Error(`HTTP ${r.status}`);
          });
        }
        return r.json();
      })
      .then((data) => {
        const ts = Date.now();
        if (data.is_stale) {
          setStatus("warning", "Session expired — open OnTrack for latest updates");
        } else {
          setStatus("ok", `Logged in as ${username}`);
          chrome.storage.local.set({ [SNAPSHOT_KEY]: { ts, data } });
        }

        // Sync the server's fresh token back into chrome.storage
        if (data.auth_token && data.auth_token !== authToken) {
          chrome.storage.local.set({ auth_token: data.auth_token });
        }
        renderStrip(data.days);
        renderTasks(data.days);
        footerSync.textContent = data.is_stale ? "Stale Data" : syncLabel(ts);
      })
      .catch((err) => {
        console.warn("[OnTrack Brief] Snapshot failed:", err);
        snapshotSection.style.display = "none";
      });
  });
}

// ── Refresh button ────────────────────────────────────────────────

refreshBtn.addEventListener("click", () => {
  if (!_snapshotAuth) return;
  chrome.storage.local.remove(SNAPSHOT_KEY, () => {
    loadSnapshot(_snapshotAuth.authToken, _snapshotAuth.username, _snapshotAuth.baseUrl, true, _snapshotAuth.days);
  });
});

// ── Init ──────────────────────────────────────────────────────────

chrome.storage.local.get(["auth_token", "username", "base_url", "subscribed_email", "strip_weeks",
                          "recently_completed_days", "max_todo_tasks", "signup_skipped"], (data) => {
  const weeks = parseInt(data.strip_weeks || "1", 10);
  stripWeeksEl.value    = String(weeks);
  if (data.recently_completed_days) recentlyDaysEl.value = String(data.recently_completed_days);
  if (data.max_todo_tasks)          maxTodoEl.value       = String(data.max_todo_tasks);

  switchTab("main");
  updateView(data);

  if (data.subscribed_email) {
    emailInput.value       = data.subscribed_email;
    unsubRow.style.display = "block";
  }
});

// ── Sign Up ───────────────────────────────────────────────────────

signupBtn.addEventListener("click", () => {
  const email = signupEmail.value.trim();
  if (!email || !email.includes("@")) {
    signupMsg.className = "msg error";
    signupMsg.textContent = "Enter a valid email address.";
    return;
  }

  chrome.storage.local.get(["auth_token", "username", "base_url"], (data) => {
    signupBtn.disabled = true;
    signupBtn.textContent = "Setting up…";

    fetch(`${APP_URL}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        base_url: data.base_url || "https://ontrack.deakin.edu.au",
        username: data.username,
        auth_token: data.auth_token,
        email,
        brief_hour: 8
      }),
    })
      .then((r) => r.json())
      .then((res) => {
        if (res.ok) {
          chrome.storage.local.set({ subscribed_email: email }, () => {
            chrome.storage.local.get(null, (all) => updateView(all));
          });
        } else {
          signupMsg.className = "msg error";
          signupMsg.textContent = res.error || "Signup failed.";
        }
      })
      .catch(() => {
        signupMsg.className = "msg error";
        signupMsg.textContent = "Could not reach server.";
      })
      .finally(() => {
        signupBtn.disabled = false;
        signupBtn.textContent = "Subscribe to Email Briefs";
      });
  });
});

skipSignup.addEventListener("click", () => {
  chrome.storage.local.set({ signup_skipped: true }, () => {
    chrome.storage.local.get(null, (all) => updateView(all));
  });
});

// ── Subscribe ─────────────────────────────────────────────────────

subscribeBtn.addEventListener("click", () => {
  const email = emailInput.value.trim();
  const hour  = parseInt(hourSelect.value, 10);

  if (!email || !email.includes("@")) {
    showMsg("error", "Enter a valid email address.");
    return;
  }

  chrome.storage.local.get(["auth_token", "username", "base_url"], (data) => {
    if (!data.auth_token || !data.username) {
      showMsg("error", "No OnTrack session found. Open OnTrack first.");
      return;
    }

    subscribeBtn.disabled    = true;
    subscribeBtn.textContent = "Enabling…";

    fetch(`${APP_URL}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        base_url:                data.base_url || "https://ontrack.deakin.edu.au",
        username:                data.username,
        auth_token:              data.auth_token,
        email,
        brief_hour:              hour,
        recently_completed_days: recentlyDaysEl.value,
        max_todo_tasks:          maxTodoEl.value,
      }),
    })
      .then((r) => {
        if (r.ok) {
          chrome.storage.local.set({
            subscribed_email:        email,
            recently_completed_days: recentlyDaysEl.value,
            max_todo_tasks:          maxTodoEl.value,
          });
          setStatus("ok", `Email briefs enabled — daily at ${hourSelect.options[hourSelect.selectedIndex].text}`);
          showMsg("success", "Done! Check your inbox in a moment.");
          unsubRow.style.display = "block";
        } else if (r.status === 400) {
          showMsg("error", "OnTrack session expired — log out of OnTrack, log back in, then try again.");
        } else {
          showMsg("error", `Server error (${r.status}). Is app.py running?`);
        }
      })
      .catch(() => {
        showMsg("error", "Could not reach the OnTrack Brief server. Is app.py running?");
      })
      .finally(() => {
        subscribeBtn.disabled    = false;
        subscribeBtn.textContent = "Enable email briefs";
      });
  });
});

// ── Unsubscribe ───────────────────────────────────────────────────

unsubLink.addEventListener("click", () => {
  chrome.storage.local.get(["subscribed_email"], (data) => {
    if (!data.subscribed_email) return;
    fetch(`${APP_URL}/unsubscribe/${encodeURIComponent(data.subscribed_email)}`)
      .then(() => {
        chrome.storage.local.remove("subscribed_email");
        setStatus("ok", "Unsubscribed.");
        unsubRow.style.display = "none";
        showMsg("success", "You've been unsubscribed.");
      })
      .catch(() => showMsg("error", "Could not reach server."));
  });
});
