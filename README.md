# Floorplan AI — Campus Room Booking

Reads a campus floor plan image with a free, open-source OCR model, turns the
rooms it finds into a bookable web app, and matches as many of those rooms as
possible to their actual location on the map.

## What's in here

- **OCR pipeline** (`find_rooms.py` + `clean_rooms.py`) — reads `floorplan.png`
  with [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) (CPU only, no
  GPU needed), cleans up the raw text (fixes OCR mistakes like two words
  being squished together), and writes the room list to `output/rooms.json`
  / `output/rooms.md`.
- **Location mapping** (`map_locations.py`) — matches each room name to a
  pixel location on the floor plan drawing, using the colored legend numbers
  next to each room. 36 of 48 extracted entries get a real location; the
  other 11 are things like wing labels and office blocks ("OFFICES S1-8")
  that aren't actually single rooms, so they're intentionally left unmatched.
  `output/location_debug.png` shows the matches as red boxes, for a quick
  visual check.
- **Web app** (`build_app.py` generates `app.html`) — a list view, a
  clickable floor-plan map, and a full day/time-slot schedule grid for every
  room. Supports multi-slot bookings, a real booking form (name, mobile,
  student/staff ID, university email, meeting info), booking rules (no
  weekends/holidays/past dates, closes 8pm), "Add to Google Calendar" and
  email-draft links, and a 3-color status legend.
- **Backend** (`server.py`) — a small local Flask server with a SQLite
  database (`bookings.db`) that the web app talks to, so bookings persist in
  a real file instead of one browser's local storage.

## Setup

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

## Running the OCR pipeline (optional — already done once)

`output/rooms.json` and `app.html` are already generated and committed, so
you don't need to re-run this unless you want to regenerate them (e.g. after
changing `floorplan.png`):

```powershell
venv\Scripts\python.exe find_rooms.py       # OCR + clean -> output/rooms.json, rooms.md
venv\Scripts\python.exe map_locations.py    # match rooms to map locations -> output/location_debug.png
venv\Scripts\python.exe build_app.py        # regenerate app.html from the latest room data
```

## Running the booking app

```powershell
venv\Scripts\python.exe server.py
```

Then open **http://localhost:5000** in a browser. Opening `app.html` directly
as a file will not work — the app needs the server running to load and save
bookings.

This is local-only: the server binds to `127.0.0.1`, so it's only reachable
from this machine. Booking data lives in `bookings.db` next to `server.py`
(a plain SQLite file) — delete it to start over with an empty schedule.

## Known limitations

- 12 of the 48 extracted entries have no map location: 1 (`IT ROOM`) is a
  real room PaddleOCR just couldn't confidently locate; the other 11 are
  wing labels, office blocks, and similar non-room entries.
- No login system — a booking just shows as "yours" in whichever browser
  made it, there's no real identity check beyond the details typed into the
  booking form.
- `PUBLIC_HOLIDAYS` in `build_app.py` holds Malaysia's 2026 national public
  holidays. Six of them (Chinese New Year, Hari Raya Aidilfitri, Hari Raya
  Haji, Wesak Day, Awal Muharram, Maulidur Rasul) follow the Islamic/lunar
  calendar and are provisional until the government confirms them closer to
  the date — re-check against the official gazette. The list needs new
  dates added for each new year.
- Single-user, local-only by design (not set up for multiple people sharing
  one server over a network).
