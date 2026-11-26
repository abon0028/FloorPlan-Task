# Deploying to PythonAnywhere

This makes the app reachable from anywhere (not just your laptop), with real
accounts so multiple students and staff can use it. PythonAnywhere's free
tier is used because, unlike most free hosts, its filesystem is **persistent**
— `bookings.db` survives restarts instead of getting wiped.

This is a one-time setup you do yourself (it needs your own PythonAnywhere
account and login) — the steps below are everything to copy-paste once you
have an account.

## 1. Create a free account

Go to [pythonanywhere.com](https://www.pythonanywhere.com) and sign up for
the **Beginner** (free) plan. No credit card needed.

## 2. Open a Bash console and get the code

From your PythonAnywhere dashboard: **Consoles** tab → **Bash**.

```bash
git clone https://github.com/abon0028/FloorPlan-Task.git
cd FloorPlan-Task
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

(This installs PaddleOCR too, which you don't need just to run the booking
app — only `Flask` actually matters for serving it. If `pip install` is slow
or hits the free tier's disk-space limit, install just what `server.py`
needs instead: `pip install Flask`.)

## 3. Create the web app

**Web** tab → **Add a new web app** → pick **Manual configuration** (not the
Flask wizard) → **Python 3.10**.

- **Source code / Working directory**: `/home/yourusername/FloorPlan-Task`
- **Virtualenv**: `/home/yourusername/FloorPlan-Task/venv`

## 4. Point the WSGI file at `server.py`

Still on the **Web** tab, click the WSGI configuration file link (something
like `/var/www/yourusername_pythonanywhere_com_wsgi.py`). Delete its contents
and replace with:

```python
import sys

path = '/home/yourusername/FloorPlan-Task'
if path not in sys.path:
    sys.path.insert(0, path)

from server import app as application
```

(Replace `yourusername` with your actual PythonAnywhere username, in both
this file and step 3.)

## 5. Set a persistent session secret

Still on the **Web** tab, under **Environment variables**, add:

- `SECRET_KEY` — any long random string (e.g. generate one locally with
  `python -c "import secrets; print(secrets.token_hex(32))"` and paste the
  result). This keeps everyone logged in across server restarts. If you skip
  this, `server.py` generates and persists its own key in a local file
  instead — also fine, just slightly less standard practice.

## 6. Set up email for password resets (optional, but recommended)

Without this, "Forgot password" still works for testing — it just prints the
reset link to the app's log output (visible from the log links on the
**Web** tab) instead of emailing it, which isn't something you want real
users to have to ask you for.

To send real emails, add these as more **Environment variables** (same place
as `SECRET_KEY`). The easiest option is a Gmail account with an
[App Password](https://myaccount.google.com/apppasswords) (requires 2-Step
Verification turned on for that Google account first — a regular Gmail
password won't work here):

- `SMTP_HOST` — `smtp.gmail.com`
- `SMTP_PORT` — `587`
- `SMTP_USER` — the Gmail address sending the emails
- `SMTP_PASSWORD` — the 16-character App Password (not your regular Gmail
  password)
- `SMTP_FROM` — optional, defaults to `SMTP_USER` if not set

Any other SMTP provider works the same way — just use its host/port instead.

## 7. Reload

Click the big green **Reload** button at the top of the **Web** tab. Your
app is now live at `https://yourusername.pythonanywhere.com`, with HTTPS
included automatically.

## Notes

- The deployed `bookings.db` starts **empty** — it's a separate database
  from the one on your own laptop (your local testing data stays local,
  nothing is migrated).
- Free tier gives you `yourusername.pythonanywhere.com`, not a custom domain.
  A custom domain needs a paid plan.
- After pulling new code changes (`git pull` in the Bash console), click
  **Reload** on the **Web** tab again to pick them up — PythonAnywhere
  doesn't auto-restart on file changes.
- If something goes wrong, the **Web** tab has an **Error log** link —
  that's the first place to check.
