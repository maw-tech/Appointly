# Appointly – Appointment Scheduling and Management System

Appointly is a web application for a small service provider, such as a tutor or consultant, to take appointment bookings online. Customers pick a free 30-minute slot and enter their name and email. The provider logs in to an admin dashboard to review bookings, cancel them and set weekly working hours.

It replaces manual scheduling and prevents double bookings. Every request is checked on the server, and a unique index in the database also rejects a second active booking for the same slot.

> IT Capstone project. All customer data in the demo is fictional (`example.com` addresses). No payment information is collected.

---

## Features

| Area | What it does |
|------|--------------|
| **Customer booking** | Shows available dates and 30-minute time slots for the next 14 days (this can be changed). The customer enters a name, email and optional notes, books one slot and gets a confirmation page with a reference code. |
| **Provider availability** | One provider and one configurable timezone. Working days and hours are set per weekday in a protected admin page. Slots outside working hours or in the past are never offered and are rejected if submitted. |
| **Double-booking prevention** | The server checks the slot inside a write-locked transaction (`BEGIN IMMEDIATE`). A **partial unique index** in SQLite also allows only one `booked` row per date and time. A clear error is shown when a slot is taken, and cancelling a booking frees the slot. |
| **Admin dashboard** | Password-protected login. Lists Upcoming, Past, Cancelled and All bookings with customer name, email, date, time and status, and supports search. Bookings can be cancelled. Bookings that fall outside new working hours are flagged. |
| **Persistence** | Everything is stored in a local SQLite file, so data survives a server restart. Demo availability is created automatically: Mon–Fri 09:00–17:00, Sat 10:00–14:00, Sunday closed. |
| **Security** | Backend validation of all input, parameterised SQL, hashed admin passwords (Werkzeug scrypt), CSRF tokens on every form, `HttpOnly`/`SameSite` session cookies, login session renewed on sign-in, safe redirects, security headers and secrets read from environment variables. |
| **Responsive UI** | Bootstrap 5 with a custom theme. Works on desktop and mobile, and the admin table stacks into cards on small screens. Bootstrap is served from the installed Python package, so **no internet connection is needed** at runtime. |

## Technology

Python 3 · Flask 3 · SQLite (built-in `sqlite3` module) · Jinja2 templates · Bootstrap 5 (via Bootstrap-Flask, served locally) · pytest

Developed and tested on **Windows 11 with Python 3.14.6**. Any Python 3.10 or newer should work.

## Project structure

```
Appointly/
├── appointly/                 # Flask application package
│   ├── __init__.py            # create_app() factory, template filters, error pages
│   ├── config.py              # settings read from environment variables / .env
│   ├── db.py                  # SQLite connection, transactions, CLI commands
│   ├── schema.sql             # tables, unique index, demo availability
│   ├── models.py              # data access (parameterised SQL only)
│   ├── scheduling.py          # pure date/time + 30-minute slot logic
│   ├── booking.py             # booking rules and safe reservation saving
│   ├── validation.py          # name / email / notes validation
│   ├── security.py            # CSRF, login_required, security headers
│   ├── public.py              # customer routes (blueprint)
│   ├── admin.py               # administrator routes (blueprint)
│   ├── templates/             # Jinja2 templates (base, booking pages, admin/)
│   └── static/                # css/style.css, js/app.js
├── tests/                     # pytest suite (unit + integration)
├── docs/
│   ├── ARCHITECTURE.md        # architecture overview
│   └── DATABASE_SCHEMA.md     # database schema documentation
├── requirements.txt
├── pytest.ini
├── .env.example               # template for local configuration (copy to .env)
└── .gitignore
```

---

## Installation and running on Windows

Run these commands in **Windows PowerShell** from the project folder (the folder containing this README). Each command is on its own line.

### 1. Check Python

```powershell
py --version
```

You need Python 3.10 or newer. If `py` is not found, install Python from <https://www.python.org/downloads/windows/> and tick **"Add python.exe to PATH"**.

### 2. Create and activate a virtual environment

```powershell
py -m venv .venv
```

```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell says that running scripts is disabled, allow it for this window only and then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

```powershell
.\.venv\Scripts\Activate.ps1
```

(In **Command Prompt** use `.venv\Scripts\activate.bat` instead.) Your prompt should now start with `(.venv)`.

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure the application

```powershell
Copy-Item .env.example .env
```

Generate a secret key:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Open `.env` in a text editor (for example `notepad .env`) and replace `replace-with-a-long-random-string` with the value printed above. You can also change the timezone, provider name and booking window there:

| Variable | Default | Meaning |
|----------|---------|---------|
| `SECRET_KEY` | *(required)* | Signs session cookies. Keep it secret. |
| `APPOINTLY_TIMEZONE` | `America/New_York` | IANA timezone for all appointment times, e.g. `Europe/London`, `Asia/Manila`. |
| `APPOINTLY_PROVIDER_NAME` | `Riverside Tutoring` | Name shown to customers. |
| `APPOINTLY_BOOKING_WINDOW_DAYS` | `14` | How many days ahead customers may book (1–90). |
| `APPOINTLY_DATABASE` | `instance\appointly.sqlite3` | Optional custom path to the database file. |
| `SESSION_COOKIE_SECURE` | `0` | Set to `1` only when serving over HTTPS. |

### 5. Initialise the database

```powershell
flask --app appointly init-db
```

This creates `instance\appointly.sqlite3` with the tables and the demo weekly availability. The command is safe to run again, because existing data is kept. To delete **all** data and start over, use `flask --app appointly init-db --reset`.

### 6. Create the administrator account

```powershell
flask --app appointly create-admin
```

Enter a username (default `admin`) and a password of at least 8 characters. Only a salted hash of the password is stored. Run the command again to reset the password.

### 7. (Optional) Add fictional demo bookings

```powershell
flask --app appointly seed-demo
```

This books four upcoming appointments for fictional customers (`@example.com` / `@example.org`), so the dashboard has data to show.

### 8. Run the automated tests

```powershell
python -m pytest
```

Each test uses its own temporary database and a fixed "current time", so the tests never touch your real data.

### 9. Start the web server

```powershell
flask --app appointly run
```

Open <http://127.0.0.1:5000> in a browser:

- **Customer booking:** <http://127.0.0.1:5000/book>
- **Admin login:** <http://127.0.0.1:5000/admin/login>

Press `Ctrl+C` in the terminal to stop the server. Bookings remain in `instance\appointly.sqlite3` and are there again after the next `flask --app appointly run`.

For development with automatic reloading, use `flask --app appointly run --debug`. Never use debug mode on a shared network.

### Next time (quick start)

```powershell
.\.venv\Scripts\Activate.ps1
```

```powershell
flask --app appointly run
```

---

## Demonstration walkthrough

1. Open `/book`. Days with no free slots are greyed out and past times today are hidden.
2. Pick a time and submit the form with an invalid email to see the server-side validation message. Then correct it and confirm the booking.
3. Open the same time again, for example by pressing the browser's Back button and resubmitting. You get the message *"Sorry, that time slot has already been booked."*
4. Log in at `/admin/login`. The new booking appears under **Upcoming** with name, email, date, time and status.
5. Click **Cancel** on the booking. The slot appears again on `/book` and can be booked by someone else.
6. Open **Availability**, change a day's hours or switch a day off and save. The booking page updates immediately. If existing bookings fall outside the new hours, you get a warning and the bookings are flagged on the dashboard.
7. Stop the server (`Ctrl+C`) and start it again. All bookings are still there.

## Testing summary

`python -m pytest` runs 119 tests in `tests/`:

- `test_scheduling.py`: slot generation, date/time parsing, past-time rules, booking window, name/email/notes validation.
- `test_booking.py`: slot listing, successful booking and confirmation, HTML escaping, double-booking rejection, the **database-level unique index**, a simulated race condition, past, out-of-hours, closed-day, off-grid and out-of-window slots, and invalid customer fields.
- `test_admin.py`: login protection on every admin route, wrong passwords, password hashing, safe `next` redirects, logout, dashboard contents, filters and search, cancellation releasing the slot, availability updates and validation, and the warning about bookings outside the new hours.
- `test_security_and_persistence.py`: CSRF rejection and acceptance, security headers, `HttpOnly` cookie, data surviving an application restart, availability not being overwritten on restart, and the `init-db`, `create-admin` and `seed-demo` commands.

## Scope and future improvements

The following are intentionally **not** included in the MVP: online payments, SMS or email reminders, Google Calendar integration, multiple service providers, external login providers, customer self-service cancellation, and one-off holidays or blocked dates.

## Further documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, request flow, design decisions
- [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md): tables, columns, constraints and indexes
