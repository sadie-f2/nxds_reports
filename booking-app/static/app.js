/**
 * A² Booking App — frontend JS
 *
 * Uses FullCalendar resource-timeline view (Scheduler, free for non-profits).
 * Talks to FastAPI backend at /api/*.
 */

let calendar;
let allResources = [];
let selectedMemberId = null;

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

function openModal() {
  selectedMemberId = null;
  document.getElementById("member-search").value = "";
  document.getElementById("member-results").style.display = "none";
  document.getElementById("form-member-id").value = "";
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
  const durationMin = parseInt(document.getElementById("form-duration").value);
  const memberId = parseInt(document.getElementById("form-member-id").value);

  if (!memberId) {
    showStatus("Please select a member.", "error");
    return;
  }
  if (!date || !startTime) {
    showStatus("Please select a date and time.", "error");
    return;
  }

  const fromDt = new Date(`${date}T${startTime}:00`);
  const toDt = new Date(fromDt.getTime() + durationMin * 60000);

  const payload = {
    resource_id: resourceId,
    member_id: memberId,
    from_time: fromDt.toISOString(),
    to_time: toDt.toISOString(),
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

document.addEventListener("DOMContentLoaded", () => {
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

  // Boot sequence
  loadResources().then(resources => {
    initCalendar(resources);
  });
});
