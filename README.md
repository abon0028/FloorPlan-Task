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
  student/staff ID, meeting info), booking rules (no weekends/holidays/past
  dates, closes 8pm), "Add to Google Calendar" and email-draft links, and a
  3-color status legend (a slot booked by someone else shows the same as
  "Unavailable" — only your own bookings show as "Your Booking").
- **Backend** (`server.py`) — a Flask server with a SQLite database
  (`bookings.db`), serving the app's pages plus the JSON API they talk to.
- **Accounts** — real email + password sign-up/log-in (`login.html`,
  `signup.html`), so multiple students and staff can use the same
  deployment. Everyone can only view full details of, or cancel, their own
  bookings — not anyone else's.
- **Bookings overview** (`overview.html`, at `/overview`) — stat cards and a
  "most-booked rooms" chart covering everyone's bookings (no personal info in
  those), plus a "My Bookings" list of just your own, with search, an
  "upcoming only" filter, and cancelling from the list.

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

Then open **http://localhost:5000** in a browser — it redirects to `/login`
if you're not signed in yet; use `/signup` to create the first account.
Opening `app.html` directly as a file will not work — the app needs the
server running to load and save bookings.

By default this runs locally only: the server binds to `127.0.0.1`, so it's
only reachable from this machine. Booking data (and accounts) live in
`bookings.db` next to `server.py` (a plain SQLite file) — delete it to start
over with an empty database, including all accounts.

To make it reachable by other people (students/staff, not just you), see
[DEPLOY.md](DEPLOY.md) for deploying it to PythonAnywhere's free tier.

## Known limitations

- 12 of the 48 extracted entries have no map location: 1 (`IT ROOM`) is a
  real room PaddleOCR just couldn't confidently locate; the other 11 are
  wing labels, office blocks, and similar non-room entries.
- Accounts have no email verification and no "forgot password" flow — anyone
  can sign up with any email address (nothing confirms they own it), and a
  lost password means asking whoever controls the database to delete the
  account and sign up again.
- No staff/student permission difference — every account behaves the same:
  it can see full details of, and cancel, only its own bookings.
- `PUBLIC_HOLIDAYS` in `build_app.py` holds Malaysia's national public
  holidays for 2026-2027. Several of them (Chinese New Year, Hari Raya
  Aidilfitri, Hari Raya Haji, Wesak Day, Awal Muharram, Maulidur Rasul)
  follow the Islamic/lunar calendar and are provisional until the government
  confirms them closer to the date — re-check against the official gazette.
  It stops at 2027 because that's as far out as reliable calculated dates
  were available when this was written (2028's Islamic dates were still
  marked provisional everywhere checked, and Wesak Day wasn't listed at
  all) — add later years once a source has real dates for them.
- `server.py` still runs as Flask's single-process development server
  locally (`python server.py`). That's fine at this scale either way — once
  deployed (see `DEPLOY.md`), PythonAnywhere's own WSGI serving replaces
  `app.run()`, so this isn't a production concern for the hosted version.
