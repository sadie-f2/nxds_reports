/**
 * A² Booking App — frontend JS
 *
 * Uses FullCalendar resource-timeline view (Scheduler, free for non-profits).
 * Talks to FastAPI backend at /api/*.
 */

let calendar;
let allResources = [];
let selectedMemberId = null;
let currentUser = null;   // { id, name, email }
let _pendingBookingOpts = null;  // stashed opts when identity gate interrupts openModal
let facilityTZ = "America/New_York";  // overridden from /api/config

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
      if (_pendingBookingOpts !== null) {
        const opts = _pendingBookingOpts;
        _pendingBookingOpts = null;
        openModal(opts);
      }
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
  const userEl = document.getElementById("current-user");
  const signinEl = document.getElementById("signin-btn");
  userEl.textContent = `${user.name} (sign out)`;
  userEl.style.display = "inline";
  signinEl.style.display = "none";
  selectedMemberId = user.id;
}

function signOut() {
  clearIdentity();
  currentUser = null;
  selectedMemberId = null;
  document.getElementById("current-user").style.display = "none";
  document.getElementById("identity-email").value = "";
  document.getElementById("identity-error").style.display = "none";
  // If gate is mandatory, reopen it; otherwise show Sign in button
  if (document.getElementById("identity-gate").dataset.mandatory === "1") {
    document.getElementById("identity-gate").classList.add("open");
  } else {
    document.getElementById("signin-btn").style.display = "inline";
  }
}

function openIdentityGate() {
  document.getElementById("identity-error").style.display = "none";
  document.getElementById("identity-gate").classList.add("open");
  setTimeout(() => document.getElementById("identity-email").focus(), 50);
}

// ── Utility ──────────────────────────────────────────────────────────────────

function todayStr() {
  // Today's date in the facility timezone
  return new Date().toLocaleDateString("en-CA", { timeZone: facilityTZ });
}

function facilityDatetimeToISO(dateStr, timeStr) {
  // Convert a naive date+time (in facilityTZ) to a UTC ISO string.
  //
  // Strategy: treat the input as UTC (initial guess), ask Intl what local time
  // that UTC maps to in facilityTZ, then shift by the difference. Handles DST
  // automatically without any sign arithmetic.
  const utcGuess = new Date(`${dateStr}T${timeStr}:00Z`);

  // What local time does our UTC guess correspond to in facilityTZ?
  const localStr = utcGuess.toLocaleString("en-CA", {
    timeZone: facilityTZ,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  });
  // en-CA gives "YYYY-MM-DD, HH:MM:SS"
  const [localDate, localTime] = localStr.split(", ");
  const actualLocalMs = new Date(`${localDate}T${localTime}Z`).getTime();

  // Shift: desired local - actual local = how much to move the UTC guess
  const offsetMs = utcGuess.getTime() - actualLocalMs;
  return new Date(utcGuess.getTime() + offsetMs).toISOString();
}

function fmtFacilityTime(isoStr) {
  return new Date(isoStr).toLocaleTimeString("en-US", {
    timeZone: facilityTZ,
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

function fmtFacilityDate(isoStr) {
  return new Date(isoStr).toLocaleDateString("en-US", {
    timeZone: facilityTZ,
    weekday: "short", month: "short", day: "numeric",
  });
}

// Convert a JS Date to { dateStr: "YYYY-MM-DD", timeStr: "HH:MM" } in facilityTZ
function facilityLocalParts(date) {
  const dateStr = date.toLocaleDateString("en-CA", { timeZone: facilityTZ }); // YYYY-MM-DD
  const timeStr = date.toLocaleTimeString("en-GB", {
    timeZone: facilityTZ,
    hour: "2-digit", minute: "2-digit",
  }); // HH:MM
  return { dateStr, timeStr };
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
    initialView: "resourceTimeline7Day",
    initialDate: todayStr(),
    views: {
      resourceTimeline7Day: {
        type: "resourceTimeline",
        duration: { days: 7 },
      },
    },
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
    selectable: true,
    selectMirror: true,
    select: onSelect,
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
  document.getElementById("d-date").textContent = fmtFacilityDate(b.from_time);
  document.getElementById("d-time").textContent =
    `${fmtFacilityTime(b.from_time)} – ${fmtFacilityTime(b.to_time)}`;
  document.getElementById("d-duration").textContent =
    `${b.duration_hours} hr${b.duration_hours !== 1 ? "s" : ""}`;
  document.getElementById("detail-panel").style.display = "block";
}

function closeDetail() {
  document.getElementById("detail-panel").style.display = "none";
}

// Click or drag on cells → open modal pre-populated with resource, start time, and duration
function onSelect(info) {
  const { dateStr, timeStr } = facilityLocalParts(info.start);
  const durationMs = info.end - info.start;
  const durationMinutes = Math.round(durationMs / 60000);
  const resourceId = info.resource ? info.resource.id : null;
  openModal({ resourceId, dateStr, startTime: timeStr, durationMinutes });
  calendar.unselect();
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

// opts: optional { resourceId, dateStr, startTime, durationMinutes }
function openModal(opts = {}) {
  // Require identity before booking — open gate and resume after sign-in
  if (!currentUser) {
    _pendingBookingOpts = opts;
    openIdentityGate();
    return;
  }

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

  // Resource
  if (opts.resourceId) {
    document.getElementById("form-resource").value = String(opts.resourceId);
  }

  // Date
  document.getElementById("form-date").value = opts.dateStr || todayStr();

  // Start time — snap to nearest 30-min slot present in the select
  if (opts.startTime) {
    const [h, m] = opts.startTime.split(":").map(Number);
    const snapped = m < 30
      ? `${String(h).padStart(2, "0")}:00`
      : `${String(h).padStart(2, "0")}:30`;
    document.getElementById("form-start").value = snapped;
  }

  // Duration
  const dur = (opts.durationMinutes > 0) ? opts.durationMinutes : 60;
  const durSel = document.getElementById("form-duration");
  const customEl = document.getElementById("form-duration-custom");
  const presets = Array.from(durSel.options).map(o => parseInt(o.value)).filter(v => !isNaN(v));
  if (presets.includes(dur)) {
    durSel.value = String(dur);
    customEl.style.display = "none";
  } else {
    durSel.value = "custom";
    const h = Math.floor(dur / 60);
    const m = dur % 60;
    customEl.value = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
    customEl.style.display = "block";
  }

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

  const fromISO = facilityDatetimeToISO(date, startTime);
  const fromDt = new Date(fromISO);
  const toDt = new Date(fromDt.getTime() + durationMin * 60000);

  // Past-booking check
  if (fromDt < new Date()) {
    showStatus("Start time is in the past.", "error");
    return;
  }

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

  // Boot sequence — fetch config, then handle identity
  const cfg = await fetch("/api/config").then(r => r.json());
  facilityTZ = cfg.timezone || "America/New_York";

  if (cfg.email_gate) {
    document.getElementById("identity-gate").dataset.mandatory = "1";
  }

  const stored = loadStoredIdentity();
  if (stored) {
    currentUser = stored;
    applyIdentity(stored);
    document.getElementById("identity-gate").classList.remove("open");
  } else if (cfg.email_gate) {
    // Gate is mandatory — leave it open, no sign-in button needed
  } else {
    // Gate is optional — close it, show Sign in button
    document.getElementById("identity-gate").classList.remove("open");
    document.getElementById("signin-btn").style.display = "inline";
  }

  loadResources().then(resources => {
    initCalendar(resources);
  });
});
