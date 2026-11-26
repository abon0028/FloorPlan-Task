"""
build_app.py

Generates app.html: a single, self-contained local web page implementing
the "campus management" feature end to end --
  - the floor plan image, with clickable highlights on every room whose
    real location was confidently matched (see map_locations.py)
  - a spreadsheet-style schedule grid below it: one row per room, one
    column per time slot, green = available / red = booked, click a cell
    to toggle it (booking is stored in the browser only -- there's no
    real backend yet, this is a working prototype of the UI)

Run this again any time output/rooms.json changes (e.g. after re-running
map_locations.py) to regenerate app.html with the latest data.

Usage:
    venv\\Scripts\\python.exe build_app.py
"""

import json
import os

ROOMS_JSON = os.path.join("output", "rooms.json")
OUTPUT_HTML = "app.html"

# Plain string substitution (not str.format) -- the page body is full of
# literal { } from CSS and JS, so a token-based replace is far less
# error-prone than escaping every brace for .format().
TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ - Campus Map</title>
<style>
  :root {
    --ink: #1a1a2e;
    --muted: #6b7280;
    --border: #e5e7eb;
    --accent: #2563eb;
    --accent-bg: rgba(37, 99, 235, 0.18);
    --available: #16a34a;
    --available-bg: #d7f0db;
    --available-bg-hover: #bfe6c7;
    --yours: #d97706;
    --yours-bg: #fde8c7;
    --yours-bg-hover: #fbd9a0;
    --unavailable: #dc2626;
    --unavailable-bg: #f3c6c6;
    --unavailable-bg-hover: #edb0b0;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
    color: var(--ink);
    background: #f8fafc;
  }
  header {
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    background: white;
  }
  header h1 { margin: 0; font-size: 20px; }
  header p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
  .overview-link {
    display: inline-block;
    margin-top: 8px;
    color: var(--accent);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
  }
  .overview-link:hover { text-decoration: underline; }
  #accountInfo { color: var(--muted); font-weight: 400; margin-left: 12px; }
  #accountInfo a { color: var(--accent); font-weight: 600; text-decoration: none; }
  #accountInfo a:hover { text-decoration: underline; }
  .legend { display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; }
  .legend-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--ink); font-weight: 600; }
  .legend .swatch { width: 16px; height: 16px; border-radius: 4px; display: inline-block; }
  .legend .swatch.available { background: var(--available); }
  .legend .swatch.yours { background: var(--yours); }
  .legend .swatch.unavailable { background: var(--unavailable); }
  .map-panel {
    margin: 20px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
  }
  .map-wrap {
    position: relative;
    max-width: 900px;
    margin: 0 auto;
    line-height: 0;
  }
  .map-wrap img { width: 100%; height: auto; display: block; border-radius: 6px; }
  .hotspot {
    position: absolute;
    border: 2px solid var(--available);
    background: rgba(22, 163, 74, 0.18);
    border-radius: 3px;
    cursor: pointer;
    transition: background 0.15s;
  }
  .hotspot:hover { background: rgba(22, 163, 74, 0.32); }
  .hotspot.yours { border-color: var(--yours); background: rgba(217, 119, 6, 0.22); }
  .hotspot.unavailable { border-color: var(--unavailable); background: rgba(220, 38, 38, 0.18); }
  .hotspot.selected { box-shadow: 0 0 0 3px rgba(26, 26, 46, 0.45); z-index: 2; }
  .grid-panel {
    margin: 0 20px 20px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
  }
  .controls {
    display: flex;
    gap: 12px;
    align-items: center;
    flex-wrap: wrap;
    padding-bottom: 12px;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--border);
  }
  .controls input[type=text] {
    flex: 1 1 220px;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
  }
  .controls input[type=date] {
    padding: 7px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
  }
  .controls label.toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    color: var(--muted);
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .closed-notice {
    background: #fef3c7;
    color: #92400e;
    border: 1px solid #fde68a;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 10px;
  }
  .grid-scroll { overflow-x: auto; }
  table.schedule { border-collapse: collapse; width: 100%; min-width: 760px; }
  table.schedule th, table.schedule td { border: 1px solid #94a3b8; }
  table.schedule thead th {
    position: sticky;
    top: 0;
    background: #f1f5f9;
    padding: 8px 6px;
    font-size: 12px;
    color: var(--muted);
    font-weight: 600;
    white-space: nowrap;
    z-index: 1;
  }
  table.schedule thead th.room-col { left: 0; z-index: 2; text-align: left; }
  .wing-row td {
    background: #f1f5f9;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    padding: 6px 10px;
    position: sticky;
    left: 0;
  }
  td.room-name {
    position: sticky;
    left: 0;
    background: white;
    padding: 8px 10px;
    font-size: 13px;
    white-space: nowrap;
    cursor: pointer;
  }
  tr.selected td.room-name { background: #eff6ff; }
  td.room-name .dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 6px; }
  td.room-name .dot.mapped { background: var(--accent); }
  td.room-name .dot.unmapped { background: #d1d5db; }
  td.slot-cell {
    padding: 0;
    text-align: center;
    cursor: pointer;
    min-width: 72px;
    height: 34px;
  }
  td.slot-cell.available { background: var(--available-bg); }
  td.slot-cell.available:hover { background: var(--available-bg-hover); }
  td.slot-cell.yours { background: var(--yours-bg); }
  td.slot-cell.yours:hover { background: var(--yours-bg-hover); }
  td.slot-cell.closed { background: var(--unavailable-bg); cursor: not-allowed; }
  .empty-state { padding: 16px; color: var(--muted); font-size: 13px; }
  .map-popover {
    position: absolute;
    display: none;
    background: white;
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.18);
    padding: 12px;
    width: 230px;
    z-index: 5;
  }
  .map-popover.open { display: block; }
  .map-popover .close-btn {
    position: absolute;
    top: 6px;
    right: 8px;
    border: none;
    background: none;
    font-size: 16px;
    line-height: 1;
    cursor: pointer;
    color: var(--muted);
  }
  .map-popover h3 { margin: 0 0 2px; font-size: 14px; padding-right: 16px; }
  .map-popover .wing-label { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
  .map-popover .slot-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5px;
  }
  .map-popover .slot {
    padding: 6px 4px;
    border: none;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 600;
    cursor: pointer;
    text-align: center;
  }
  .map-popover .slot.available { background: var(--available-bg); color: var(--available); }
  .map-popover .slot.available:hover { background: var(--available-bg-hover); }
  .map-popover .slot.yours { background: var(--yours-bg); color: var(--yours); }
  .map-popover .slot.yours:hover { background: var(--yours-bg-hover); }
  .map-popover .slot.closed { background: var(--unavailable-bg); color: var(--unavailable); cursor: not-allowed; }
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.45);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 20;
    padding: 20px;
  }
  .modal-overlay.open { display: flex; }
  .modal-card {
    background: white;
    border-radius: 10px;
    padding: 20px;
    width: 380px;
    max-width: 100%;
    max-height: 85vh;
    overflow-y: auto;
    box-shadow: 0 20px 50px rgba(0,0,0,0.25);
  }
  .modal-card h3 { margin: 0 0 2px; font-size: 17px; }
  .modal-card .modal-sub { color: var(--muted); font-size: 13px; margin-bottom: 14px; }
  .modal-card label { display: block; font-size: 12px; font-weight: 600; color: var(--muted); margin: 10px 0 4px; }
  .modal-card input, .modal-card textarea, .modal-card select {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 16px; /* 16px stops iOS Safari auto-zooming in on focus */
    font-family: inherit;
  }
  .modal-card textarea { resize: vertical; min-height: 60px; }
  .time-row { display: flex; gap: 10px; margin-top: 10px; }
  .time-row > div { flex: 1; }
  .time-box {
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
    background: #f8fafc;
    color: var(--ink);
  }
  .time-summary-bar {
    display: flex;
    align-items: center;
    gap: 8px;
    background: #f8fafc;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 12px;
    margin: 12px 0;
  }
  .time-summary-text { flex: 1; font-size: 13px; color: var(--ink); }
  .time-summary-bar select {
    padding: 6px 8px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 13px;
    font-family: inherit;
    background: white;
  }
  .trash-btn {
    background: white;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    cursor: pointer;
    font-size: 14px;
    color: var(--muted);
    line-height: 1;
  }
  .trash-btn:hover { background: #f1f5f9; color: var(--unavailable); }
  .btn-submit-times {
    width: 100%;
    margin-top: 16px;
    padding: 10px;
    border: none;
    border-radius: 6px;
    background: var(--accent);
    color: white;
    font-weight: 600;
    font-size: 14px;
    cursor: pointer;
  }
  .btn-submit-times:disabled { opacity: 0.6; cursor: not-allowed; }
  .modal-actions { display: flex; gap: 8px; margin-top: 16px; }
  .modal-actions button {
    flex: 1;
    padding: 10px;
    border: none;
    border-radius: 6px;
    font-weight: 600;
    cursor: pointer;
    font-size: 14px;
  }
  .modal-actions .btn-primary { background: var(--available); color: white; }
  .modal-actions .btn-danger { background: var(--unavailable); color: white; }
  .modal-actions .btn-secondary { background: #e5e7eb; color: var(--ink); }
  .detail-row { margin-bottom: 10px; font-size: 14px; }
  .detail-row .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em; display: block; margin-bottom: 1px; }
  .form-error { color: var(--unavailable); font-size: 12px; margin-top: 8px; display: none; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ &mdash; Campus Map</h1>
  <p>__MAPPED_COUNT__ of __TOTAL_COUNT__ rooms have a confirmed location on the map -- click a box to book it right there, per time slot.</p>
  <div class="legend">
    <span class="legend-item"><span class="swatch available"></span>Available</span>
    <span class="legend-item"><span class="swatch yours"></span>Your Booking</span>
    <span class="legend-item"><span class="swatch unavailable"></span>Unavailable</span>
  </div>
  <a class="overview-link" href="/overview">View all bookings &rarr;</a>
  <span class="overview-link" id="accountInfo"></span>
</header>
<div class="map-panel">
  <div class="map-wrap" id="mapWrap">
    <img src="__IMAGE_PATH__" id="floorplanImg" alt="Floor plan">
    <div class="map-popover" id="mapPopover">
      <button class="close-btn" id="popoverClose">&times;</button>
      <h3 id="popoverTitle"></h3>
      <div class="wing-label" id="popoverWing"></div>
      <div class="slot-grid" id="popoverSlots"></div>
    </div>
  </div>
</div>
<div class="grid-panel">
  <div class="controls">
    <input type="text" id="searchBox" placeholder="Search rooms...">
    <input type="date" id="bookingDate">
    <label class="toggle">
      <input type="checkbox" id="availableOnly">
      Available rooms only
    </label>
  </div>
  <div class="closed-notice" id="closedNotice" style="display:none"></div>
  <div class="grid-scroll">
    <table class="schedule" id="scheduleTable"></table>
  </div>
</div>
<div class="modal-overlay" id="bookingModal">
  <div class="modal-card" id="modalContent"></div>
</div>

<script>
const ROOMS = __ROOMS_JSON__;
const IMAGE_SIZE = __IMAGE_SIZE_JSON__;
const TIME_SLOTS = [
  '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
  '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00',
  '17:00-18:00', '18:00-19:00', '19:00-20:00',
];
// The hour marks a booking's Start/End pickers can land on -- one more
// entry than TIME_SLOTS, since each slot's end is the next slot's start.
const SLOT_BOUNDARIES = TIME_SLOTS.map(s => s.split('-')[0]).concat([TIME_SLOTS[TIME_SLOTS.length - 1].split('-')[1]]);

// Every TIME_SLOTS entry whose hour range falls within [startTime, endTime)
// -- this is what lets one booking span several consecutive hourly slots.
function slotsInRange(startTime, endTime) {
  return TIME_SLOTS.filter(s => {
    const [a, b] = s.split('-');
    return a >= startTime && b <= endTime;
  });
}

// Malaysia national public holidays, 2026-2027 (source: officeholidays.com,
// checked 2026-11-26). Several of these -- Chinese New Year, Hari Raya
// Aidilfitri, Hari Raya Haji, Wesak Day, Awal Muharram, and Maulidur Rasul --
// follow the Islamic or lunar calendar and are provisional until Malaysia's
// government confirms them closer to the date; re-check against the official
// gazette before relying on them. State-only holidays (e.g. Thaipusam,
// Deepavali, individual sultans'/governors' birthdays) are not included here.
//
// Stops at 2027: that's as far out as officeholidays.com has calculated
// lunar dates at the time of writing. A check of calendarific.com's 2028
// Malaysia list found every Islamic-calendar date marked "(Provisional)"
// and no Wesak Day entry at all, so 2028 isn't included here rather than
// guessing -- add it (and each year after) once a source has real dates.
//
// New Year's Day (Jan 1) is included even though it's technically a
// state-level holiday, not a national one: 5 states (Johor, Kedah,
// Kelantan, Perlis, Terengganu) treat it as a normal working day, but the
// rest, plus the federal territories, observe it -- included here since
// that's the majority.
const PUBLIC_HOLIDAYS = [
  // 2026
  '2026-01-01', // New Year's Day (not observed in Johor, Kedah, Kelantan, Perlis, Terengganu)
  '2026-02-17', // Chinese New Year
  '2026-02-18', // Chinese New Year holiday
  '2026-03-20', // Hari Raya Aidilfitri holiday
  '2026-03-21', // Hari Raya Aidilfitri (provisional)
  '2026-03-22', // Hari Raya Aidilfitri holiday
  '2026-03-23', // Hari Raya Aidilfitri holiday
  '2026-05-01', // Labour Day
  '2026-05-27', // Hari Raya Haji (provisional)
  '2026-05-31', // Wesak Day (provisional)
  '2026-06-01', // Birthday of SPB Yang di-Pertuan Agong
  '2026-06-17', // Awal Muharram (provisional)
  '2026-08-25', // Maulidur Rasul -- Birthday of Prophet Muhammad (provisional)
  '2026-08-31', // National Day (Merdeka Day)
  '2026-09-16', // Malaysia Day
  '2026-12-25', // Christmas Day

  // 2027
  '2027-01-01', // New Year's Day (not observed in Johor, Kedah, Kelantan, Perlis, Terengganu)
  '2027-02-06', // Chinese New Year
  '2027-02-07', // Chinese New Year holiday
  '2027-03-10', // Hari Raya Aidilfitri (provisional)
  '2027-03-11', // Hari Raya Aidilfitri holiday
  '2027-05-01', // Labour Day
  '2027-05-17', // Hari Raya Haji (provisional)
  '2027-05-20', // Wesak Day (provisional)
  '2027-06-06', // Awal Muharram (provisional)
  '2027-06-07', // Birthday of SPB Yang di-Pertuan Agong
  '2027-08-15', // Maulidur Rasul -- Birthday of Prophet Muhammad (provisional)
  '2027-08-31', // National Day (Merdeka Day)
  '2027-09-16', // Malaysia Day
  '2027-12-25', // Christmas Day
];

const mapWrap = document.getElementById('mapWrap');
const scheduleTable = document.getElementById('scheduleTable');
const searchBox = document.getElementById('searchBox');
const availableOnlyBox = document.getElementById('availableOnly');
const dateInput = document.getElementById('bookingDate');
const mapPopover = document.getElementById('mapPopover');
const popoverClose = document.getElementById('popoverClose');
const popoverTitle = document.getElementById('popoverTitle');
const popoverWing = document.getElementById('popoverWing');
const popoverSlots = document.getElementById('popoverSlots');
const bookingModal = document.getElementById('bookingModal');
const modalContent = document.getElementById('modalContent');

let selectedId = null;

function refreshAfterBookingChange() {
  renderGrid(searchBox.value);
  renderHotspots();
  if (selectedId !== null && mapPopover.classList.contains('open')) {
    renderPopoverSlots(ROOMS[selectedId]);
  }
}

function closeBookingModal() {
  bookingModal.classList.remove('open');
}
bookingModal.addEventListener('click', (e) => {
  if (e.target === bookingModal) closeBookingModal();
});

function openSlotModal(room, date, slot) {
  const existing = getBooking(room, date, slot);
  if (existing) renderBookingDetails(room, date, slot, existing);
  else renderBookingForm(room, date, slot);
  bookingModal.classList.add('open');
}

function formatDisplayDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  const weekday = d.toLocaleDateString('en-GB', { weekday: 'short' });
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${weekday}, ${dd}/${mm}/${d.getFullYear()}`;
}

function renderBookingForm(room, date, slot) {
  const [clickedStart, clickedEnd] = slot.split('-');
  const endOptions = SLOT_BOUNDARIES.slice(1);
  const optionTags = (options, selected) =>
    options.map(t => `<option value="${t}"${t === selected ? ' selected' : ''}>${t}</option>`).join('');

  modalContent.innerHTML = `
    <h3>${room.name} &mdash; ${formatDisplayDate(date)}</h3>
    <div class="modal-sub">${room.wing || 'Not part of a numbered wing'}</div>
    <div class="time-summary-bar">
      <div class="time-summary-text"><strong>${room.name}</strong>: ${clickedStart} ${formatDisplayDate(date)} until&hellip;</div>
      <select id="f_end">${optionTags(endOptions, clickedEnd)}</select>
      <button type="button" class="trash-btn" id="f_remove" title="Cancel this booking">&#128465;</button>
    </div>
    <label>Name (student / lecturer)</label>
    <input type="text" id="f_name">
    <label>Mobile number</label>
    <input type="tel" id="f_mobile" placeholder="Phone number">
    <label>ID (student / staff)</label>
    <input type="text" id="f_id">
    <label>Meeting information</label>
    <textarea id="f_meeting" placeholder="Enter your meeting description here"></textarea>
    <div class="form-error" id="f_error"></div>
    <button class="btn-submit-times" id="f_submit">Submit Times</button>
  `;
  document.getElementById('f_remove').addEventListener('click', closeBookingModal);
  document.getElementById('f_submit').addEventListener('click', async () => {
    const startTime = clickedStart;
    const endTime = document.getElementById('f_end').value;
    const name = document.getElementById('f_name').value.trim();
    const mobile = document.getElementById('f_mobile').value.trim();
    const studentId = document.getElementById('f_id').value.trim();
    const meeting = document.getElementById('f_meeting').value.trim();
    const errorEl = document.getElementById('f_error');
    const submitBtn = document.getElementById('f_submit');

    if (endTime <= startTime) {
      errorEl.textContent = 'End Time must be after Start Time.';
      errorEl.style.display = 'block';
      return;
    }
    const coveredSlots = slotsInRange(startTime, endTime);
    const alreadyBooked = coveredSlots.filter(s => isSlotBooked(room, date, s));
    if (alreadyBooked.length > 0) {
      errorEl.textContent = 'One or more of those hours is already booked (' + alreadyBooked.join(', ') + ').';
      errorEl.style.display = 'block';
      return;
    }
    if (!name || !mobile || !studentId || !meeting) {
      errorEl.textContent = 'Please fill in all fields.';
      errorEl.style.display = 'block';
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting...';
    const result = await createBookingOnServer(
      room, date, startTime, endTime, coveredSlots,
      { name, mobile, id: studentId, meeting }
    );
    if (!result.ok) {
      errorEl.textContent = result.error;
      errorEl.style.display = 'block';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Submit Times';
      return;
    }
    await loadBookingsForDate(date);
    closeBookingModal();
    refreshAfterBookingChange();
  });
}

function renderBookingDetails(room, date, slot, details) {
  const [fallbackStart, fallbackEnd] = slot.split('-');
  const startTime = details.startTime || fallbackStart;
  const endTime = details.endTime || fallbackEnd;

  modalContent.innerHTML = `
    <h3>${room.name} &mdash; ${formatDisplayDate(date)}</h3>
    <div class="modal-sub">${room.wing || 'Not part of a numbered wing'}</div>
    <div class="time-row">
      <div>
        <label>Start Time</label>
        <div class="time-box">${startTime}</div>
      </div>
      <div>
        <label>End Time</label>
        <div class="time-box">${endTime}</div>
      </div>
    </div>
    <div class="detail-row"><span class="label">Name</span>${details.name}</div>
    <div class="detail-row"><span class="label">Mobile</span>${details.mobile}</div>
    <div class="detail-row"><span class="label">ID</span>${details.id}</div>
    <div class="detail-row"><span class="label">University email</span>${details.email}</div>
    <div class="detail-row"><span class="label">Meeting information</span>${details.meeting}</div>
    <div class="modal-actions">
      <button class="btn-secondary" id="d_close">&#10006; Close</button>
      <button class="btn-danger" id="d_cancel">Cancel Booking</button>
    </div>
  `;
  document.getElementById('d_close').addEventListener('click', closeBookingModal);
  document.getElementById('d_cancel').addEventListener('click', async () => {
    const cancelBtn = document.getElementById('d_cancel');
    cancelBtn.disabled = true;
    cancelBtn.textContent = 'Cancelling...';
    const result = await cancelBookingOnServer(details.group_id);
    if (!result.ok) {
      alert(result.error);
      cancelBtn.disabled = false;
      cancelBtn.textContent = 'Cancel Booking';
      return;
    }
    await loadBookingsForDate(date);
    closeBookingModal();
    refreshAfterBookingChange();
  });
}

function todayStr() {
  const d = new Date();
  return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
}
dateInput.value = todayStr();
dateInput.min = todayStr(); // no booking dates before today

function isWeekend(dateStr) {
  const day = new Date(dateStr + 'T00:00:00').getDay();
  return day === 0 || day === 6; // Sunday, Saturday
}
function isHoliday(dateStr) { return PUBLIC_HOLIDAYS.includes(dateStr); }
function isPastDate(dateStr) { return dateStr < todayStr(); }
function isBookableDate(dateStr) { return !isPastDate(dateStr) && !isWeekend(dateStr) && !isHoliday(dateStr); }
function unbookableReason(dateStr) {
  if (isPastDate(dateStr)) return 'Past date';
  if (isHoliday(dateStr)) return 'Public holiday';
  if (isWeekend(dateStr)) return 'Weekend';
  return null;
}

// Bookings now live in a real database behind server.py, not the browser.
// This page fetches the whole day's bookings once per date shown and
// keeps them in this cache; every render function below reads the cache
// synchronously (unchanged from the localStorage version), so only the
// "load a date" and "create/cancel a booking" paths need to be async.
let bookingsCache = {};
let bookingsCacheDate = null;

function cacheKey(room, slot) { return room.name + '|' + slot; }

async function loadBookingsForDate(date) {
  try {
    const res = await fetch('/api/bookings?date=' + encodeURIComponent(date));
    if (res.status === 401) { window.location.href = '/login'; return; }
    if (!res.ok) throw new Error('server returned ' + res.status);
    bookingsCache = await res.json();
  } catch (err) {
    bookingsCache = {};
    alert('Could not reach the booking server at this address.\\n\\n' +
      'Make sure you started it with "python server.py" and are viewing ' +
      'this page at http://localhost:5000 -- opening app.html directly ' +
      'as a file will not work anymore.');
  }
  bookingsCacheDate = date;
}

function getBooking(room, date, slot) {
  if (date !== bookingsCacheDate) return null; // cache not loaded for this date yet
  return bookingsCache[cacheKey(room, slot)] || null;
}

async function createBookingOnServer(room, date, startTime, endTime, slots, details) {
  const res = await fetch('/api/bookings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ room: room.name, date, startTime, endTime, slots }, details)),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: body.error || ('Server error ' + res.status) };
  }
  return { ok: true };
}

async function cancelBookingOnServer(groupId) {
  const res = await fetch('/api/bookings/' + encodeURIComponent(groupId), { method: 'DELETE' });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: body.error || ('Server error ' + res.status) };
  }
  return { ok: true };
}

function isSlotBooked(room, date, slot) { return getBooking(room, date, slot) !== null; }
function isSlotMine(room, date, slot) {
  const b = getBooking(room, date, slot);
  return !!b && b.mine === true;
}

// Three-way status for a whole room on a given date, matching the legend:
// 'closed' (red -- the date isn't bookable, or every slot is taken and none
// of them are the logged-in user's), 'yours' (amber -- no free slots, but at
// least one of the booked ones is the logged-in user's own), or 'available'
// (green, at least one open slot).
function roomDateStatus(room, date) {
  if (!isBookableDate(date)) return 'closed';
  if (TIME_SLOTS.some(slot => !isSlotBooked(room, date, slot))) return 'available';
  return TIME_SLOTS.some(slot => isSlotMine(room, date, slot)) ? 'yours' : 'closed';
}

function pctBox(box) {
  return {
    left: (box.x0 / IMAGE_SIZE.width * 100) + '%',
    top: (box.y0 / IMAGE_SIZE.height * 100) + '%',
    width: ((box.x1 - box.x0) / IMAGE_SIZE.width * 100) + '%',
    height: ((box.y1 - box.y0) / IMAGE_SIZE.height * 100) + '%',
  };
}

function renderHotspots() {
  const date = dateInput.value;
  mapWrap.querySelectorAll('.hotspot').forEach(el => el.remove());
  ROOMS.forEach((room, i) => {
    if (!room.location_box) return;
    const status = roomDateStatus(room, date);
    if (availableOnlyBox.checked && status !== 'available') return;
    const el = document.createElement('div');
    el.className = 'hotspot' + (status !== 'available' ? ' ' + status : '') + (i === selectedId ? ' selected' : '');
    const p = pctBox(room.location_box);
    Object.assign(el.style, p);
    const statusText = status === 'closed' ? 'not bookable on ' + date
      : status === 'yours' ? 'fully booked on ' + date
      : 'available on ' + date;
    el.title = room.name + ' (' + statusText + ')';
    el.addEventListener('click', () => openMapPopover(i, el));
    mapWrap.appendChild(el);
  });
}

function renderPopoverSlots(room) {
  const date = dateInput.value;
  popoverSlots.innerHTML = '';
  const reason = unbookableReason(date);
  if (reason) {
    popoverSlots.innerHTML = `<div class="closed-notice">${reason} &mdash; not bookable</div>`;
    return;
  }
  TIME_SLOTS.forEach(slot => {
    const booked = isSlotBooked(room, date, slot);
    const mine = isSlotMine(room, date, slot);
    const btn = document.createElement('button');
    btn.className = 'slot ' + (!booked ? 'available' : mine ? 'yours' : 'closed');
    btn.textContent = slot + (booked ? ' X' : '');
    if (!booked || mine) btn.addEventListener('click', () => openSlotModal(room, date, slot));
    popoverSlots.appendChild(btn);
  });
}

function openMapPopover(i, hotspotEl) {
  selectedId = i;
  const room = ROOMS[i];
  popoverTitle.textContent = room.name;
  popoverWing.textContent = room.wing || 'Not part of a numbered wing';
  renderPopoverSlots(room);

  // position the popover next to the hotspot, clamped so it stays inside the map
  const left = Math.min(hotspotEl.offsetLeft + hotspotEl.offsetWidth + 10, mapWrap.offsetWidth - 240);
  const top = Math.min(hotspotEl.offsetTop, mapWrap.offsetHeight - 180);
  mapPopover.style.left = Math.max(10, left) + 'px';
  mapPopover.style.top = Math.max(10, top) + 'px';
  mapPopover.classList.add('open');

  renderGrid(searchBox.value);
  renderHotspots();
}

function closeMapPopover() {
  mapPopover.classList.remove('open');
}
popoverClose.addEventListener('click', closeMapPopover);

function renderGrid(filterText) {
  const date = dateInput.value;
  const closedReason = unbookableReason(date);
  const notice = document.getElementById('closedNotice');
  if (closedReason) {
    notice.textContent = closedReason + ' — no bookings available on this date.';
    notice.style.display = 'block';
  } else {
    notice.style.display = 'none';
  }

  const filtered = ROOMS
    .map((room, i) => ({ room, i }))
    .filter(({ room }) => !filterText || room.name.toLowerCase().includes(filterText.toLowerCase()))
    .filter(({ room }) => !availableOnlyBox.checked || roomDateStatus(room, date) === 'available');

  scheduleTable.innerHTML = '';
  if (filtered.length === 0) {
    scheduleTable.innerHTML = '';
    document.getElementById('scheduleTable').insertAdjacentHTML('afterend',
      '<div class="empty-state" id="emptyMsg">No rooms match your filters.</div>');
    return;
  }
  const existingEmpty = document.getElementById('emptyMsg');
  if (existingEmpty) existingEmpty.remove();

  const thead = document.createElement('thead');
  const headRow = document.createElement('tr');
  headRow.innerHTML = '<th class="room-col">Room</th>' +
    TIME_SLOTS.map(s => `<th>${s}</th>`).join('');
  thead.appendChild(headRow);
  scheduleTable.appendChild(thead);

  const tbody = document.createElement('tbody');
  const byWing = {};
  filtered.forEach(({ room, i }) => {
    const wing = room.wing || 'Other / Unassigned';
    (byWing[wing] = byWing[wing] || []).push(i);
  });

  Object.keys(byWing).sort((a, b) => {
    if (a === 'Other / Unassigned') return 1;
    if (b === 'Other / Unassigned') return -1;
    return a.localeCompare(b);
  }).forEach(wing => {
    const wingRow = document.createElement('tr');
    wingRow.className = 'wing-row';
    wingRow.innerHTML = `<td colspan="${TIME_SLOTS.length + 1}">${wing} (${byWing[wing].length})</td>`;
    tbody.appendChild(wingRow);

    byWing[wing].forEach(i => {
      const room = ROOMS[i];
      const tr = document.createElement('tr');
      if (i === selectedId) tr.className = 'selected';
      tr.id = 'room-row-' + i;

      const nameTd = document.createElement('td');
      nameTd.className = 'room-name';
      nameTd.innerHTML = `<span class="dot ${room.location_box ? 'mapped' : 'unmapped'}"></span>${room.name}`;
      nameTd.addEventListener('click', () => selectRoom(i));
      tr.appendChild(nameTd);

      TIME_SLOTS.forEach(slot => {
        const td = document.createElement('td');
        const bookedByOther = !closedReason && isSlotBooked(room, date, slot) && !isSlotMine(room, date, slot);
        if (closedReason || bookedByOther) {
          td.className = 'slot-cell closed';
          td.title = room.name + ' - ' + slot + ' (' + (closedReason || 'already booked') + ', not bookable)';
        } else {
          const booked = isSlotBooked(room, date, slot);
          td.className = 'slot-cell ' + (booked ? 'yours' : 'available');
          td.title = room.name + ' - ' + slot + (booked ? ' (your booking - click to view/cancel)' : ' (available - click to book)');
          td.addEventListener('click', () => openSlotModal(room, date, slot));
        }
        tr.appendChild(td);
      });

      tbody.appendChild(tr);
    });
  });
  scheduleTable.appendChild(tbody);
}

function selectRoom(i) {
  selectedId = i;
  renderGrid(searchBox.value);
  renderHotspots();
  const row = document.getElementById('room-row-' + i);
  if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

searchBox.addEventListener('input', () => renderGrid(searchBox.value));
availableOnlyBox.addEventListener('change', () => {
  if (selectedId !== null && availableOnlyBox.checked && roomDateStatus(ROOMS[selectedId], dateInput.value) !== 'available') {
    selectedId = null;
  }
  renderGrid(searchBox.value);
  renderHotspots();
});
dateInput.addEventListener('change', async () => {
  await loadBookingsForDate(dateInput.value);
  renderGrid(searchBox.value);
  renderHotspots();
  if (selectedId !== null && mapPopover.classList.contains('open')) {
    renderPopoverSlots(ROOMS[selectedId]);
  }
});

async function loadAccountInfo() {
  try {
    const res = await fetch('/api/me');
    if (!res.ok) return;
    const me = await res.json();
    document.getElementById('accountInfo').innerHTML =
      'Logged in as ' + me.email + ' &middot; <a href="/logout">Log out</a>';
  } catch (err) { /* not critical -- just leave the line blank */ }
}

(async () => {
  loadAccountInfo();
  await loadBookingsForDate(dateInput.value);
  renderGrid('');
  renderHotspots();
})();
</script>
</body>
</html>
"""


def main():
    with open(ROOMS_JSON, encoding="utf-8") as f:
        data = json.load(f)

    rooms = data["rooms"]
    mapped_count = sum(1 for r in rooms if "location_box" in r)
    title = os.path.splitext(os.path.basename(data["source_image"]))[0].replace("_", " ").title()

    html = TEMPLATE
    html = html.replace("__TITLE__", title)
    html = html.replace("__MAPPED_COUNT__", str(mapped_count))
    html = html.replace("__TOTAL_COUNT__", str(len(rooms)))
    html = html.replace("__IMAGE_PATH__", data["source_image"])
    html = html.replace("__ROOMS_JSON__", json.dumps(rooms))
    html = html.replace("__IMAGE_SIZE_JSON__", json.dumps(data["image_size"]))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {OUTPUT_HTML} ({mapped_count}/{len(rooms)} rooms clickable on the map)")


if __name__ == "__main__":
    main()
