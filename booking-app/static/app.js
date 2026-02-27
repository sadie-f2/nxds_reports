/**
 * A² Booking App — frontend JS
 *
 * Uses FullCalendar resource-timeline view (Scheduler, free for non-profits).
 * Talks to FastAPI backend at /api/*.
 */

let calendar;
let allResources = [];
let selectedMemberId = null;
let currentUser = null;  // { id, name, email }

// ── Identity / auth gate ──────────────────────────────────────────────────────

function loadStoredIdentity() {
  try {
    const stored = localStorage.getItem("a2_user");
    return stored ? JSON.parse(stored) : null;
  } catch { return null; }
}

function storeIdentity(user) {
  localStorage.setItem("a2_user", JSON.stringify(user));
}

function clearIdentity() {
  localStorage.removeItem("a2_user");
}

async function submitIdentity() {
  const email = document.getElementById("identity-email").value.trim();
  const errEl = document.getElementById("identity-error");
  errEl.style.display = "none";

  if (!email) return;

  try {
    const resp = await fetch("/api/auth/identify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (resp.ok) {
      const user = await resp.json();
      currentUser = user;
      storeIdentity(user);
      applyIdentity(user);
      document.getElementById("identity-gate").classList.remove("open");
    } else {
      errEl.textContent = "No active member found with that email. Please check and try again.";
      errEl.style.display = "block";
    }
  } catch {
    errEl.textContent = "Connection error — please try again.";
    errEl.style.display = "block";
  }
}

function applyIdentity(user) {
  // Show greeting in header
  document.getElementById("current-user").textContent = `${user.name} (sign out)`;
  // Pre-fill the booking form member field
  selectedMemberId = user.id;
  document.getElementById("member-search").value = user.name;
  document.getElementById("form-member-id").value = user.id;
}

function signOut() {
  clearIdentity();
  currentUser = null;
  selectedMemberId = null;
  document.getElementById("current-user").textContent = "";
  document.getElementById("identity-email").value = "";
  document.getElementById("identity-error").style.display = "none";
  document.getElementById("identity-gate").classList.add("open");
}

// ── Utility ──────────────────────────────────────────────────────────────────

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

function fmtTime(isoStr) {
  const dt = new Date(isoStr);
  return dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZoneName: "short" });
}

function fmtDate(isoStr) {
  const dt = new Date(isoStr);
  return dt.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

// ── Resources ─────────────────────────────────────────────────────────────────

async function loadResources() {
  const resp = await fetch("/api/resources");
  allResources = await resp.json();

  // Populate shop filter
  const shops = [...new Set(allResources.map(r => r.shop))].sort();
  const shopSel = document.getElementById("shop-filter");
  shops.forEach(s => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    shopSel.appendChild(opt);
  });

  // Populate booking form resource dropdown
  const formRes = document.getElementById("form-resource");
  allResources.forEach(r => {
    const opt = document.createElement("option");
    opt.value = r.id;
    opt.textContent = r.name;
    formRes.appendChild(opt);
  });

  return allResources;
}

function filteredResources() {
  const shop = document.getElementById("shop-filter").value;
  if (!shop) return allResources;
  return allResources.filter(r => r.shop === shop);
}

// ── Calendar ──────────────────────────────────────────────────────────────────

async function fetchEvents(fetchInfo, successCallback, failureCallback) {
  const from = fetchInfo.startStr.slice(0, 10);
  const to = fetchInfo.endStr.slice(0, 10);

  try {
    const resp = await fetch(`/api/bookings?from=${from}&to=${to}`);
    const bookings = await resp.json();
    const shop = document.getElementById("shop-filter").value;

    const events = bookings
      .filter(b => !shop || b.shop === shop)
      .map(b => ({
        id: String(b.id),
        resourceId: String(b.resource_id),
        title: b.member_name,
        start: b.from_time,
        end: b.to_time,
        extendedProps: { booking: b },
      }));

    successCallback(events);
  } catch (err) {
    failureCallback(err);
  }
}

function initCalendar(resources) {
  const calEl = document.getElementById("calendar");

  calendar = new FullCalendar.Calendar(calEl, {
    schedulerLicenseKey: "CC-Attribution-NonCommercial-NoDerivatives",
    initialView: "resourceTimelineWeek",
    initialDate: todayStr(),
    headerToolbar: {
      left: "prev,next today",
      center: "title",
      right: "resourceTimelineDay,resourceTimelineWeek",
    },
    slotMinTime: "00:00:00",
    slotMaxTime: "24:00:00",
    slotDuration: "01:00:00",
    slotLabelInterval: "02:00",
    resourceAreaHeaderContent: "Equipment",
    resourceAreaWidth: "200px",
    resources: resources.map(r => ({
      id: String(r.id),
      title: r.name.includes("|") ? r.name.split("|").slice(1).join("|").trim() : r.name,
      extendedProps: { shop: r.shop },
    })),
    resourceGroupField: "shop",
    events: fetchEvents,
    eventClick: onEventClick,
    height: "auto",
    nowIndicator: true,
  });

  calendar.render();
}

function refreshCalendar() {
  if (calendar) {
    calendar.refetchResources();
    calendar.refetchEvents();
  }
}

// ── Event detail panel ────────────────────────────────────────────────────────

function onEventClick(info) {
  const b = info.event.extendedProps.booking;
  document.getElementById("d-resource").textContent = b.resource_name;
  document.getElementById("d-member").textContent = b.member_name;
  document.getElementById("d-date").textContent = fmtDate(b.from_time);
  document.getElementById("d-time").textContent =
    `${fmtTime(b.from_time)} – ${fmtTime(b.to_time)}`;
  document.getElementById("d-duration").textContent =
    `${b.duration_hours} hr${b.duration_hours !== 1 ? "s" : ""}`;
  document.getElementById("detail-panel").style.display = "block";
}

function closeDetail() {
  document.getElementById("detail-panel").style.display = "none";
}

// ── Booking form ──────────────────────────────────────────────────────────────

function populateStartTimes() {
  const sel = document.getElementById("form-start");
  sel.innerHTML = "";
  for (let h = 0; h < 24; h++) {
    for (let m of [0, 30]) {
      const label = new Date(2000, 0, 1, h, m).toLocaleTimeString("en-US", {
        hour: "numeric", minute: "2-digit",
      });
      const val = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = label;
      sel.appendChild(opt);
    }
  }
  // Default to next round hour
  const now = new Date();
  const nextHour = `${String(now.getHours() + 1).padStart(2, "0")}:00`;
  sel.value = nextHour;
}

function onDurationChange() {
  const sel = document.getElementById("form-duration");
  const custom = document.getElementById("form-duration-custom");
  custom.style.display = sel.value === "custom" ? "block" : "none";
  if (sel.value === "custom") custom.focus();
}

function getDurationMinutes() {
  const sel = document.getElementById("form-duration");
  if (sel.value !== "custom") return parseInt(sel.value);
  const raw = document.getElementById("form-duration-custom").value.trim();
  const match = raw.match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const total = parseInt(match[1]) * 60 + parseInt(match[2]);
  if (total <= 0 || total > 23 * 60) return null;
  return total;
}

function openModal() {
  // Pre-fill with current user; they can type to change to someone else
  if (currentUser) {
    selectedMemberId = currentUser.id;
    document.getElementById("member-search").value = currentUser.name;
    document.getElementById("form-member-id").value = currentUser.id;
  } else {
    selectedMemberId = null;
    document.getElementById("member-search").value = "";
    document.getElementById("form-member-id").value = "";
  }
  document.getElementById("member-results").style.display = "none";
  document.getElementById("form-duration").value = "60";
  document.getElementById("form-duration-custom").style.display = "none";
  document.getElementById("form-date").value = todayStr();
  document.getElementById("status-msg").className = "";
  document.getElementById("status-msg").style.display = "none";
  document.getElementById("booking-modal").classList.add("open");
}

function closeModal() {
  document.getElementById("booking-modal").classList.remove("open");
}

async function submitBooking() {
  const resourceId = parseInt(document.getElementById("form-resource").value);
  const date = document.getElementById("form-date").value;
  const startTime = document.getElementById("form-start").value;
  const memberId = parseInt(document.getElementById("form-member-id").value);

  if (!memberId) {
    showStatus("Please select a member.", "error");
    return;
  }
  if (!date || !startTime) {
    showStatus("Please select a date and time.", "error");
    return;
  }

  const durationMin = getDurationMinutes();
  if (!durationMin) {
    showStatus("Please enter a valid duration (HH:MM, max 23:00).", "error");
    return;
  }

  const fromDt = new Date(`${date}T${startTime}:00`);
  const toDt = new Date(fromDt.getTime() + durationMin * 60000);

  // Detect on-behalf-of
  const onBehalf = currentUser && currentUser.id !== memberId;
  const memberName = document.getElementById("member-search").value;

  const payload = {
    resource_id: resourceId,
    member_id: memberId,
    member_name: memberName,
    from_time: fromDt.toISOString(),
    to_time: toDt.toISOString(),
    booked_by_id: currentUser ? currentUser.id : null,
    booked_by_name: currentUser ? currentUser.name : null,
  };

  try {
    const resp = await fetch("/api/bookings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (resp.ok) {
      showStatus("Booking confirmed!", "success");
      setTimeout(() => {
        closeModal();
        calendar.refetchEvents();
      }, 1200);
    } else {
      const err = await resp.json();
      showStatus(`Error: ${err.detail || "Booking failed"}`, "error");
    }
  } catch (e) {
    showStatus("Network error — please try again.", "error");
  }
}

function showStatus(msg, type) {
  const el = document.getElementById("status-msg");
  el.textContent = msg;
  el.className = type;
  el.style.display = "block";
}

// ── Member search ─────────────────────────────────────────────────────────────

let memberSearchTimeout;

document.addEventListener("DOMContentLoaded", async () => {
  const searchInput = document.getElementById("member-search");
  const resultsEl = document.getElementById("member-results");

  searchInput.addEventListener("input", () => {
    clearTimeout(memberSearchTimeout);
    memberSearchTimeout = setTimeout(async () => {
      const q = searchInput.value.trim();
      const resp = await fetch(`/api/members/search?q=${encodeURIComponent(q)}`);
      const members = await resp.json();

      resultsEl.innerHTML = "";
      if (members.length === 0) {
        resultsEl.style.display = "none";
        return;
      }

      members.forEach(m => {
        const div = document.createElement("div");
        div.textContent = m.name;
        div.dataset.id = m.id;
        div.addEventListener("click", () => {
          selectedMemberId = m.id;
          searchInput.value = m.name;
          document.getElementById("form-member-id").value = m.id;
          resultsEl.style.display = "none";
        });
        resultsEl.appendChild(div);
      });

      resultsEl.style.display = "block";
    }, 200);
  });

  // Close results when clicking outside
  document.addEventListener("click", e => {
    if (!searchInput.contains(e.target) && !resultsEl.contains(e.target)) {
      resultsEl.style.display = "none";
    }
  });

  // Wire up controls
  document.getElementById("book-btn").addEventListener("click", openModal);
  document.getElementById("shop-filter").addEventListener("change", () => {
    if (calendar) calendar.refetchEvents();
  });

  populateStartTimes();

  // Enter key on identity gate
  document.getElementById("identity-email").addEventListener("keydown", e => {
    if (e.key === "Enter") submitIdentity();
  });

  // Boot sequence — check config, then stored identity
  const cfg = await fetch("/api/config").then(r => r.json());

  if (cfg.email_gate) {
    const stored = loadStoredIdentity();
    if (stored) {
      currentUser = stored;
      applyIdentity(stored);
      document.getElementById("identity-gate").classList.remove("open");
    }
    // else: gate stays open
  } else {
    // Email gate disabled — close it immediately
    document.getElementById("identity-gate").classList.remove("open");
  }

  loadResources().then(resources => {
    initCalendar(resources);
  });
});
