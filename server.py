"""
server.py

Local-only backend for the campus booking app: a small Flask server with a
SQLite database, replacing the browser-localStorage prototype. Serves
app.html itself plus a small JSON API it talks to, so bookings are stored
in a real file-based database instead of one browser's local storage.

Run:
    venv\\Scripts\\python.exe server.py
Then open http://localhost:5000 in your browser.

This is single-machine only: it binds to 127.0.0.1 (localhost), not your
network IP, so nobody else can reach it. Data lives in bookings.db
(SQLite, a plain file next to this script) -- delete that file to reset.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request, send_from_directory

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "bookings.db")

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            room_name TEXT NOT NULL,
            date TEXT NOT NULL,
            slot TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            name TEXT NOT NULL,
            mobile TEXT NOT NULL,
            student_id TEXT NOT NULL,
            email TEXT NOT NULL,
            meeting TEXT NOT NULL,
            booked_at TEXT NOT NULL,
            UNIQUE(room_name, date, slot)
        )
        """
    )
    db.commit()
    db.close()


@app.route("/")
def index():
    return send_from_directory(APP_DIR, "app.html")


@app.route("/floorplan.png")
def floorplan_image():
    return send_from_directory(APP_DIR, "floorplan.png")


@app.route("/overview")
def overview_page():
    return send_from_directory(APP_DIR, "overview.html")


@app.route("/api/bookings/all")
def list_all_bookings():
    """Every booking, one entry per group_id (a multi-slot booking shares
    one group_id across several rows) -- powers the overview page."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM bookings ORDER BY date ASC, start_time ASC"
    ).fetchall()
    grouped = {}
    for row in rows:
        gid = row["group_id"]
        if gid not in grouped:
            grouped[gid] = {
                "group_id": gid,
                "room": row["room_name"],
                "date": row["date"],
                "startTime": row["start_time"],
                "endTime": row["end_time"],
                "name": row["name"],
                "mobile": row["mobile"],
                "id": row["student_id"],
                "email": row["email"],
                "meeting": row["meeting"],
                "bookedAt": row["booked_at"],
                "slotCount": 0,
            }
        grouped[gid]["slotCount"] += 1
    bookings = sorted(grouped.values(), key=lambda b: (b["date"], b["startTime"]))
    return jsonify(bookings)


@app.route("/api/bookings")
def list_bookings():
    """All bookings for one date, across every room -- the client fetches
    this once per date shown and renders every room's status from it."""
    date = request.args.get("date")
    if not date:
        return jsonify({"error": "date query param required"}), 400
    db = get_db()
    rows = db.execute("SELECT * FROM bookings WHERE date = ?", (date,)).fetchall()
    bookings = {}
    for row in rows:
        key = row["room_name"] + "|" + row["slot"]
        bookings[key] = {
            "group_id": row["group_id"],
            "name": row["name"],
            "mobile": row["mobile"],
            "id": row["student_id"],
            "email": row["email"],
            "meeting": row["meeting"],
            "startTime": row["start_time"],
            "endTime": row["end_time"],
            "bookedAt": row["booked_at"],
        }
    return jsonify(bookings)


@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(force=True, silent=True) or {}
    required = ["room", "date", "startTime", "endTime", "slots", "name", "mobile", "id", "email", "meeting"]
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({"error": "missing field(s): " + ", ".join(missing)}), 400
    if not isinstance(data["slots"], list) or not data["slots"]:
        return jsonify({"error": "slots must be a non-empty list"}), 400

    db = get_db()
    placeholders = ",".join("?" * len(data["slots"]))
    existing = db.execute(
        f"SELECT slot FROM bookings WHERE room_name = ? AND date = ? AND slot IN ({placeholders})",
        [data["room"], data["date"], *data["slots"]],
    ).fetchall()
    if existing:
        return jsonify({"error": "one or more slots already booked", "slots": [r["slot"] for r in existing]}), 409

    group_id = str(uuid.uuid4())
    booked_at = datetime.now(timezone.utc).isoformat()
    for slot in data["slots"]:
        db.execute(
            """INSERT INTO bookings
               (group_id, room_name, date, slot, start_time, end_time,
                name, mobile, student_id, email, meeting, booked_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                group_id, data["room"], data["date"], slot, data["startTime"], data["endTime"],
                data["name"], data["mobile"], data["id"], data["email"], data["meeting"], booked_at,
            ),
        )
    db.commit()
    return jsonify({"group_id": group_id}), 201


@app.route("/api/bookings/<group_id>", methods=["DELETE"])
def cancel_booking(group_id):
    db = get_db()
    db.execute("DELETE FROM bookings WHERE group_id = ?", (group_id,))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    print(f"Database: {DB_PATH}")
    print("Starting server at http://localhost:5000 ...")
    app.run(host="127.0.0.1", port=5000, debug=False)
