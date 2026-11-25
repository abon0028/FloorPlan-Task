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
  td.slot-cell.unavailable { background: var(--unavailable-bg); }
  td.slot-cell.unavailable:hover { background: var(--unavailable-bg-hover); }
  td.slot-cell.closed { background: #f1f5f9; cursor: not-allowed; }
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
  .map-popover .slot.unavailable { background: var(--unavailable-bg); color: var(--unavailable); }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ &mdash; Campus Map</h1>
  <p>__MAPPED_COUNT__ of __TOTAL_COUNT__ rooms have a confirmed location on the map -- click a box to book it right there. Green = available, red = booked, per time slot.</p>
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

<script>
const ROOMS = __ROOMS_JSON__;
const IMAGE_SIZE = __IMAGE_SIZE_JSON__;
const TIME_SLOTS = [
  '09:00-10:00', '10:00-11:00', '11:00-12:00', '12:00-13:00',
  '13:00-14:00', '14:00-15:00', '15:00-16:00', '16:00-17:00',
  '17:00-18:00', '18:00-19:00', '19:00-20:00',
];

// Placeholder public holiday list -- just a couple of fixed-date examples
// (New Year's Day, Christmas Day) so the mechanism has something to show.
// Replace with your institution's actual closure dates (ISO yyyy-mm-dd);
// dates that move every year (e.g. Easter Monday) need to be added per-year.
const PUBLIC_HOLIDAYS = ['2026-01-01', '2026-12-25', '2026-12-26'];

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

let selectedId = null;

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

function slotKey(room, date, slot) { return 'slotbooking:' + room.name + '|' + date + '|' + slot; }
function isSlotBooked(room, date, slot) { return localStorage.getItem(slotKey(room, date, slot)) === '1'; }
function setSlotBooked(room, date, slot, value) {
  if (value) localStorage.setItem(slotKey(room, date, slot), '1');
  else localStorage.removeItem(slotKey(room, date, slot));
}
function isFullyBooked(room, date) {
  if (!isBookableDate(date)) return true; // closed day -- nothing is available
  return TIME_SLOTS.every(slot => isSlotBooked(room, date, slot));
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
    const fullyBooked = isFullyBooked(room, date);
    if (availableOnlyBox.checked && fullyBooked) return;
    const el = document.createElement('div');
    el.className = 'hotspot' + (fullyBooked ? ' unavailable' : '') + (i === selectedId ? ' selected' : '');
    const p = pctBox(room.location_box);
    Object.assign(el.style, p);
    el.title = room.name + (fullyBooked ? ' (fully booked on ' + date + ')' : ' (available on ' + date + ')');
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
    const btn = document.createElement('button');
    btn.className = 'slot ' + (booked ? 'unavailable' : 'available');
    btn.textContent = slot + (booked ? ' X' : '');
    btn.addEventListener('click', () => {
      setSlotBooked(room, date, slot, !booked);
      renderPopoverSlots(room);
      renderGrid(searchBox.value);
      renderHotspots();
    });
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
    .filter(({ room }) => !availableOnlyBox.checked || !isFullyBooked(room, date));

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
        if (closedReason) {
          td.className = 'slot-cell closed';
          td.title = room.name + ' - ' + slot + ' (' + closedReason + ', not bookable)';
        } else {
          const booked = isSlotBooked(room, date, slot);
          td.className = 'slot-cell ' + (booked ? 'unavailable' : 'available');
          td.title = room.name + ' - ' + slot + (booked ? ' (booked, click to cancel)' : ' (available, click to book)');
          td.addEventListener('click', () => {
            setSlotBooked(room, date, slot, !booked);
            renderGrid(searchBox.value);
            renderHotspots();
          });
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
  if (selectedId !== null && availableOnlyBox.checked && isFullyBooked(ROOMS[selectedId], dateInput.value)) {
    selectedId = null;
  }
  renderGrid(searchBox.value);
  renderHotspots();
});
dateInput.addEventListener('change', () => {
  renderGrid(searchBox.value);
  renderHotspots();
  if (selectedId !== null && mapPopover.classList.contains('open')) {
    renderPopoverSlots(ROOMS[selectedId]);
  }
});

renderGrid('');
renderHotspots();
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
