const APP_URL = "http://localhost:5001";  // Change to deployed URL when hosted

const statusEl    = document.getElementById("status");
const statusText  = document.getElementById("status-text");
const statusDot   = statusEl.querySelector(".dot");
const subscribeBtn = document.getElementById("subscribe-btn");
const emailInput  = document.getElementById("email");
const hourSelect  = document.getElementById("hour");
const msgEl       = document.getElementById("msg");
const unsubRow    = document.getElementById("unsubscribe-row");
const unsubLink   = document.getElementById("unsubscribe-link");

function setStatus(type, text) {
  statusEl.className   = `status ${type}`;
  statusDot.className  = `dot ${type}`;
  statusText.textContent = text;
}

function showMsg(type, text) {
  msgEl.className   = `msg ${type}`;
  msgEl.textContent = text;
}

// Load stored credentials from background worker
chrome.storage.local.get(["auth_token", "username", "base_url", "subscribed_email"], (data) => {
  if (data.auth_token && data.username) {
    setStatus("ok", `Logged in as ${data.username}`);
    subscribeBtn.disabled = false;

    if (data.subscribed_email) {
      emailInput.value = data.subscribed_email;
      unsubRow.style.display = "block";
    }
  } else {
    setStatus("warning", "Open OnTrack first — then click Subscribe");
    subscribeBtn.disabled = true;
  }
});

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

    subscribeBtn.disabled  = true;
    subscribeBtn.textContent = "Subscribing…";

    fetch(`${APP_URL}/setup`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        base_url:   data.base_url   || "https://ontrack.deakin.edu.au",
        username:   data.username,
        auth_token: data.auth_token,
        email:      email,
        brief_hour: hour,
      }),
    })
      .then((r) => {
        if (r.ok) {
          chrome.storage.local.set({ subscribed_email: email });
          setStatus("ok", `Subscribed — briefs at ${hourSelect.options[hourSelect.selectedIndex].text}`);
          showMsg("success", "Done! Check your inbox in a moment.");
          unsubRow.style.display = "block";
        } else if (r.status === 400) {
          showMsg("error", "OnTrack token is stale — reload your OnTrack tab, then try again.");
        } else {
          showMsg("error", `Server error (${r.status}). Is app.py running?`);
        }
      })
      .catch(() => {
        showMsg("error", "Could not reach the OnTrack Brief server. Is app.py running?");
      })
      .finally(() => {
        subscribeBtn.disabled    = false;
        subscribeBtn.textContent = "Subscribe";
      });
  });
});

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
