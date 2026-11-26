"""
server.py

Backend for the campus booking app: a Flask server with a SQLite database.
Serves app.html, overview.html, login.html and signup.html, plus a small
JSON API they talk to. Supports real accounts (email + password) so multiple
students and staff can use the same deployment, each only able to view full
details of / cancel their own bookings.

Run locally:
    venv\\Scripts\\python.exe server.py
Then open http://localhost:5000 in your browser.

For running this on a real host (e.g. PythonAnywhere) so it's reachable from
anywhere, see DEPLOY.md.

Data lives in bookings.db (SQLite, a plain file next to this script) --
delete that file to reset everything, including accounts.
"""

import os
import re
import secrets
import smtplib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from functools import wraps

from flask import Flask, g, jsonify, redirect, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "bookings.db")
SECRET_KEY_PATH = os.path.join(APP_DIR, ".secret_key")

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
MIN_PASSWORD_LENGTH = 8
RESET_TOKEN_LIFETIME = timedelta(hours=1)

app = Flask(__name__)


def _get_or_create_secret_key():
    """Prefer a SECRET_KEY env var (set this in PythonAnywhere's dashboard).
    Falls back to a key persisted in a local, gitignored file, so sessions
    survive a restart even without one -- works out of the box locally."""
    env_key = os.environ.get("SECRET_KEY")
    if env_key:
        return env_key
    if os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w", encoding="utf-8") as f:
        f.write(key)
    return key


app.secret_key = _get_or_create_secret_key()


def send_email(to_address, subject, body):
    """Send a plain-text email via SMTP, configured with environment
    variables (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM --
    see DEPLOY.md). With no SMTP_HOST set (e.g. running locally without
    setting any of this up), prints the email to the console instead, so
    the reset flow is still fully testable without real SMTP credentials."""
    host = os.environ.get("SMTP_HOST")
    if not host:
        print("=" * 60, flush=True)
        print("[dev] No SMTP_HOST configured -- printing email instead of sending it.", flush=True)
        print(f"To: {to_address}\nSubject: {subject}\n\n{body}", flush=True)
        print("=" * 60, flush=True)
        return
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    from_address = os.environ.get("SMTP_FROM", user)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_address
    msg["To"] = to_address
    msg.set_content(body)

    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls()
        if user and password:
            smtp.login(user, password)
        smtp.send_message(msg)


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
    db.row_factory = sqlite3.Row
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
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
    # Migration for databases created before the password-reset feature --
    # CREATE TABLE IF NOT EXISTS above won't add columns to an existing table.
    existing_cols = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if "reset_token" not in existing_cols:
        db.execute("ALTER TABLE users ADD COLUMN reset_token TEXT")
    if "reset_token_expires" not in existing_cols:
        db.execute("ALTER TABLE users ADD COLUMN reset_token_expires TEXT")
    db.commit()
    db.close()


# Runs at import time (not just "python server.py" directly) so the tables
# exist whether PythonAnywhere imports this module via WSGI or it's run
# locally in the usual way.
init_db()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login_page"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
@login_required
def index():
    return send_from_directory(APP_DIR, "app.html")


@app.route("/floorplan.png")
def floorplan_image():
    return send_from_directory(APP_DIR, "floorplan.png")


@app.route("/overview")
@login_required
def overview_page():
    return send_from_directory(APP_DIR, "overview.html")


@app.route("/signup", methods=["GET"])
def signup_page():
    return send_from_directory(APP_DIR, "signup.html")


@app.route("/login", methods=["GET"])
def login_page():
    return send_from_directory(APP_DIR, "login.html")


@app.route("/forgot-password", methods=["GET"])
def forgot_password_page():
    return send_from_directory(APP_DIR, "forgot_password.html")


@app.route("/reset-password", methods=["GET"])
def reset_password_page():
    return send_from_directory(APP_DIR, "reset_password.html")


@app.route("/api/signup", methods=["POST"])
def signup_submit():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not EMAIL_RE.match(email):
        return jsonify({"error": "Please enter a valid email address."}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400

    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if existing:
        return jsonify({"error": "An account with that email already exists."}), 409

    password_hash = generate_password_hash(password)
    created_at = datetime.now(timezone.utc).isoformat()
    cur = db.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
        (email, password_hash, created_at),
    )
    db.commit()
    session["user_id"] = cur.lastrowid
    session["email"] = email
    return jsonify({"ok": True})


@app.route("/api/login", methods=["POST"])
def login_submit():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Incorrect email or password."}), 401

    session["user_id"] = user["id"]
    session["email"] = user["email"]
    return jsonify({"ok": True})


@app.route("/api/forgot-password", methods=["POST"])
def forgot_password_submit():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    # Always return the same message whether or not the email is registered
    # -- otherwise this endpoint would let anyone check who has an account.
    generic_response = jsonify({"ok": True, "message": "If an account exists for that email, a reset link has been sent."})

    if not EMAIL_RE.match(email):
        return generic_response

    db = get_db()
    user = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        return generic_response

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + RESET_TOKEN_LIFETIME).isoformat()
    db.execute(
        "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
        (token, expires_at, user["id"]),
    )
    db.commit()

    reset_link = request.host_url.rstrip("/") + "/reset-password?token=" + token
    send_email(
        email,
        "Reset your campus booking password",
        "Someone (hopefully you) asked to reset the password for this account.\n\n"
        f"Reset it here (expires in 1 hour): {reset_link}\n\n"
        "If you didn't request this, you can ignore this email.",
    )
    return generic_response


@app.route("/api/reset-password", methods=["POST"])
def reset_password_submit():
    data = request.get_json(force=True, silent=True) or {}
    token = data.get("token") or ""
    password = data.get("password") or ""

    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"Password must be at least {MIN_PASSWORD_LENGTH} characters."}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()
    if not user or not user["reset_token_expires"]:
        return jsonify({"error": "That reset link is invalid. Request a new one."}), 400

    expires_at = datetime.fromisoformat(user["reset_token_expires"])
    if datetime.now(timezone.utc) > expires_at:
        return jsonify({"error": "That reset link has expired. Request a new one."}), 400

    password_hash = generate_password_hash(password)
    db.execute(
        "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
        (password_hash, user["id"]),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login_page"))


@app.route("/api/me")
def api_me():
    if not session.get("user_id"):
        return jsonify({"error": "login required"}), 401
    return jsonify({"email": session["email"]})


@app.route("/api/bookings/all")
@login_required
def list_all_bookings():
    """Every booking, one entry per group_id (a multi-slot booking shares
    one group_id across several rows) -- powers the overview page's stats
    (room + date only, for everyone) and "My Bookings" list (full details,
    only for the logged-in user's own). Personal fields (name/mobile/ID/
    email/meeting) are only ever sent for the caller's own bookings -- never
    sent to the client at all for anyone else's, not just hidden by the
    page's own display logic."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM bookings ORDER BY date ASC, start_time ASC"
    ).fetchall()
    grouped = {}
    for row in rows:
        gid = row["group_id"]
        mine = row["user_id"] == session["user_id"]
        if gid not in grouped:
            entry = {
                "group_id": gid,
                "room": row["room_name"],
                "date": row["date"],
                "startTime": row["start_time"],
                "endTime": row["end_time"],
                "slotCount": 0,
                "mine": mine,
            }
            if mine:
                entry.update({
                    "name": row["name"],
                    "mobile": row["mobile"],
                    "id": row["student_id"],
                    "email": row["email"],
                    "meeting": row["meeting"],
                    "bookedAt": row["booked_at"],
                })
            grouped[gid] = entry
        grouped[gid]["slotCount"] += 1
    bookings = sorted(grouped.values(), key=lambda b: (b["date"], b["startTime"]))
    return jsonify(bookings)


@app.route("/api/bookings")
@login_required
def list_bookings():
    """All bookings for one date, across every room -- the client fetches
    this once per date shown and renders every room's status from it.
    Personal fields are only sent for the caller's own bookings -- for
    anyone else's, the client only learns that the slot is taken."""
    date = request.args.get("date")
    if not date:
        return jsonify({"error": "date query param required"}), 400
    db = get_db()
    rows = db.execute("SELECT * FROM bookings WHERE date = ?", (date,)).fetchall()
    bookings = {}
    for row in rows:
        key = row["room_name"] + "|" + row["slot"]
        mine = row["user_id"] == session["user_id"]
        if mine:
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
                "mine": True,
            }
        else:
            bookings[key] = {"mine": False}
    return jsonify(bookings)


@app.route("/api/bookings", methods=["POST"])
@login_required
def create_booking():
    data = request.get_json(force=True, silent=True) or {}
    required = ["room", "date", "startTime", "endTime", "slots", "name", "mobile", "id", "meeting"]
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
               (group_id, user_id, room_name, date, slot, start_time, end_time,
                name, mobile, student_id, email, meeting, booked_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                group_id, session["user_id"], data["room"], data["date"], slot,
                data["startTime"], data["endTime"], data["name"], data["mobile"],
                data["id"], session["email"], data["meeting"], booked_at,
            ),
        )
    db.commit()
    return jsonify({"group_id": group_id}), 201


@app.route("/api/bookings/<group_id>", methods=["DELETE"])
@login_required
def cancel_booking(group_id):
    db = get_db()
    rows = db.execute("SELECT user_id FROM bookings WHERE group_id = ?", (group_id,)).fetchall()
    if not rows:
        return jsonify({"error": "booking not found"}), 404
    if rows[0]["user_id"] != session["user_id"]:
        return jsonify({"error": "you can only cancel your own bookings"}), 403
    db.execute("DELETE FROM bookings WHERE group_id = ?", (group_id,))
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    print(f"Database: {DB_PATH}")
    print("Starting server at http://localhost:5000 ...")
    app.run(host="127.0.0.1", port=5000, debug=False)
