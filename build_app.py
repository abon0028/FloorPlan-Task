"""
build_app.py

Generates app.html: a single, self-contained local web page implementing
the "campus management" feature end to end --
  - a searchable list of every room/classroom found on the floor plan
  - the floor plan image itself, with clickable highlights on every room
    whose real location was confidently matched (see map_locations.py)
  - a basic "book this room" action (stored in the browser only --
    there's no real backend yet, this is a working prototype of the UI)

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
    --accent-bg-hover: rgba(37, 99, 235, 0.32);
    --booked: #16a34a;
    --booked-bg: rgba(22, 163, 74, 0.15);
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
  .layout {
    display: flex;
    gap: 20px;
    padding: 20px;
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .map-panel {
    flex: 1 1 560px;
    min-width: 320px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px;
  }
  .map-wrap {
    position: relative;
    width: 100%;
    line-height: 0;
  }
  .map-wrap img { width: 100%; height: auto; display: block; border-radius: 6px; }
  .hotspot {
    position: absolute;
    border: 2px solid var(--accent);
    background: var(--accent-bg);
    border-radius: 3px;
    cursor: pointer;
    transition: background 0.15s, transform 0.15s;
  }
  .hotspot:hover { background: var(--accent-bg-hover); }
  .hotspot.selected {
    background: rgba(234, 88, 12, 0.35);
    border-color: #ea580c;
    z-index: 2;
  }
  .hotspot.booked { border-color: var(--booked); background: var(--booked-bg); }
  .list-panel {
    flex: 1 1 380px;
    min-width: 300px;
    background: white;
    border: 1px solid var(--border);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    max-height: 80vh;
  }
  .list-panel .search {
    padding: 12px;
    border-bottom: 1px solid var(--border);
  }
  .list-panel input[type=text] {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 14px;
  }
  .available-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 10px;
    font-size: 13px;
    color: var(--muted);
    cursor: pointer;
    user-select: none;
  }
  .available-toggle input { cursor: pointer; }
  .room-list { overflow-y: auto; flex: 1; }
  .wing-group h3 {
    margin: 0;
    padding: 8px 14px;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    background: #f1f5f9;
    position: sticky;
    top: 0;
  }
  .room-item {
    padding: 9px 14px;
    border-bottom: 1px solid #f1f5f9;
    cursor: pointer;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    font-size: 14px;
  }
  .room-item:hover { background: #f8fafc; }
  .room-item.selected { background: #eff6ff; }
  .room-item .name { flex: 1; }
  .dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
  .dot.mapped { background: var(--accent); }
  .dot.unmapped { background: #d1d5db; }
  .badge {
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 999px;
    background: var(--booked-bg);
    color: var(--booked);
    font-weight: 600;
  }
  .detail-panel {
    padding: 14px;
    border-top: 1px solid var(--border);
    background: #fafafa;
  }
  .detail-panel h2 { margin: 0 0 4px; font-size: 16px; }
  .detail-panel .wing-label { color: var(--muted); font-size: 13px; margin-bottom: 10px; }
  .detail-panel button {
    width: 100%;
    padding: 10px;
    border: none;
    border-radius: 6px;
    background: var(--accent);
    color: white;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
  }
  .detail-panel button.booked { background: var(--booked); }
  .detail-panel .no-location {
    font-size: 12px;
    color: var(--muted);
    margin-top: 8px;
  }
  .empty-state { padding: 16px; color: var(--muted); font-size: 13px; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__ &mdash; Campus Map</h1>
  <p>__MAPPED_COUNT__ of __TOTAL_COUNT__ rooms have a confirmed location on the map (blue dot). The rest are listed but not yet clickable.</p>
</header>
<div class="layout">
  <div class="map-panel">
    <div class="map-wrap" id="mapWrap">
      <img src="__IMAGE_PATH__" id="floorplanImg" alt="Floor plan">
    </div>
  </div>
  <div class="list-panel">
    <div class="search">
      <input type="text" id="searchBox" placeholder="Search rooms...">
      <label class="available-toggle">
        <input type="checkbox" id="availableOnly">
        Show available rooms only
      </label>
    </div>
    <div class="room-list" id="roomList"></div>
    <div class="detail-panel" id="detailPanel" style="display:none"></div>
  </div>
</div>

<script>
const ROOMS = __ROOMS_JSON__;
const IMAGE_SIZE = __IMAGE_SIZE_JSON__;

const roomListEl = document.getElementById('roomList');
const mapWrap = document.getElementById('mapWrap');
const detailPanel = document.getElementById('detailPanel');
const searchBox = document.getElementById('searchBox');
const availableOnlyBox = document.getElementById('availableOnly');

let selectedId = null;

function bookingKey(room) { return 'booking:' + room.name; }
function isBooked(room) { return localStorage.getItem(bookingKey(room)) === '1'; }
function setBooked(room, value) {
  if (value) localStorage.setItem(bookingKey(room), '1');
  else localStorage.removeItem(bookingKey(room));
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
  mapWrap.querySelectorAll('.hotspot').forEach(el => el.remove());
  ROOMS.forEach((room, i) => {
    if (!room.location_box) return;
    if (availableOnlyBox.checked && isBooked(room)) return;
    const el = document.createElement('div');
    el.className = 'hotspot' + (i === selectedId ? ' selected' : '') + (isBooked(room) ? ' booked' : '');
    const p = pctBox(room.location_box);
    Object.assign(el.style, p);
    el.title = room.name;
    el.addEventListener('click', () => selectRoom(i));
    mapWrap.appendChild(el);
  });
}

function renderList(filterText) {
  const filtered = ROOMS
    .map((room, i) => ({ room, i }))
    .filter(({ room }) => !filterText || room.name.toLowerCase().includes(filterText.toLowerCase()))
    .filter(({ room }) => !availableOnlyBox.checked || !isBooked(room));

  roomListEl.innerHTML = '';
  if (filtered.length === 0) {
    roomListEl.innerHTML = availableOnlyBox.checked
      ? '<div class="empty-state">No available rooms match your search.</div>'
      : '<div class="empty-state">No rooms match your search.</div>';
    return;
  }

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
    const groupEl = document.createElement('div');
    groupEl.className = 'wing-group';
    groupEl.innerHTML = `<h3>${wing} (${byWing[wing].length})</h3>`;
    byWing[wing].forEach(i => {
      const room = ROOMS[i];
      const item = document.createElement('div');
      item.className = 'room-item' + (i === selectedId ? ' selected' : '');
      item.innerHTML = `
        <span class="dot ${room.location_box ? 'mapped' : 'unmapped'}"></span>
        <span class="name">${room.name}</span>
        ${isBooked(room) ? '<span class="badge">Booked</span>' : ''}
      `;
      item.addEventListener('click', () => selectRoom(i));
      groupEl.appendChild(item);
    });
    roomListEl.appendChild(groupEl);
  });
}

function renderDetail() {
  if (selectedId === null) { detailPanel.style.display = 'none'; return; }
  const room = ROOMS[selectedId];
  const booked = isBooked(room);
  detailPanel.style.display = 'block';
  detailPanel.innerHTML = `
    <h2>${room.name}</h2>
    <div class="wing-label">${room.wing || 'Not part of a numbered wing'}</div>
    <button id="bookBtn" class="${booked ? 'booked' : ''}">${booked ? 'Booked - Click to Cancel' : 'Book This Room'}</button>
    ${!room.location_box ? '<div class="no-location">Location on the map not yet confirmed for this room.</div>' : ''}
  `;
  document.getElementById('bookBtn').addEventListener('click', () => {
    setBooked(room, !booked);
    renderDetail();
    renderList(searchBox.value);
    renderHotspots();
  });
}

function selectRoom(i) {
  selectedId = i;
  renderList(searchBox.value);
  renderHotspots();
  renderDetail();
}

searchBox.addEventListener('input', () => renderList(searchBox.value));
availableOnlyBox.addEventListener('change', () => {
  if (selectedId !== null && availableOnlyBox.checked && isBooked(ROOMS[selectedId])) {
    selectedId = null;
    renderDetail();
  }
  renderList(searchBox.value);
  renderHotspots();
});

renderList('');
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
