# Appointly – Architecture Overview

## 1. Style

Appointly is a **server-rendered monolith**. It is a single Flask application that renders HTML with Jinja2 templates and stores data in one local SQLite file. There is no separate front-end application, no external API and no cloud service. This keeps the system simple to install, run and assess on one Windows machine.

```
 Browser (desktop / mobile)
        │  HTTP (HTML forms, GET/POST)
        ▼
 ┌───────────────────────────── Flask application (appointly/) ─────────────────────────────┐
 │  security.py   before_request: CSRF check, load logged-in admin   after_request: headers │
 │                                                                                         │
 │  public.py  (blueprint "public")          admin.py  (blueprint "admin", /admin/...)     │
 │    /            home                        /admin/login, /admin/logout                 │
 │    /book        choose date & slot          /admin/              dashboard              │
 │    /book/details customer form              /admin/appointments/<id>/cancel             │
 │    POST /book   create booking              /admin/availability  weekly hours           │
 │    /booking/<ref> confirmation                                                          │
 │              │                                      │                                   │
 │              ▼                                      ▼                                   │
 │   validation.py  (customer fields)     booking.py  (business rules, safe save)          │
 │                                         │        │                                      │
 │                       scheduling.py  ◄──┘        └──►  models.py  (parameterised SQL)    │
 │                       (pure time/slot logic)                 │                           │
 │                                                              ▼                           │
 │                                                   db.py  (connection, transactions, CLI) │
 └──────────────────────────────────────────────────────────────┼───────────────────────────┘
                                                                ▼
                                                   SQLite file: instance/appointly.sqlite3
```

## 2. Components

| Module | Responsibility |
|--------|----------------|
| `__init__.py` | `create_app()` application factory. Loads configuration, checks the timezone, applies the schema (idempotent), registers blueprints, template filters and error pages. |
| `config.py` | Reads settings from environment variables. `.env` is loaded with python-dotenv, so secrets are never in source code. |
| `db.py` | Opens one SQLite connection per request (`flask.g`) and provides the `transaction()` helper (`BEGIN IMMEDIATE … COMMIT/ROLLBACK`). Defines the CLI commands `init-db`, `create-admin` and `seed-demo`. |
| `schema.sql` | Tables, CHECK constraints, the partial unique index and the demo availability. |
| `models.py` | All SQL statements, using `?` / named placeholders only. Handles admin password hashing and verification. |
| `scheduling.py` | Pure functions with no database access: strict parsing of `YYYY-MM-DD` and `HH:MM`, 30-minute slot generation, past-time checks and the booking window. `current_time()` returns "now" in the provider's timezone, and tests replace it with a fixed time. |
| `booking.py` | Business rules: which slots are open (`available_slots_for_day`, `availability_overview`), why a slot cannot be booked (`check_slot`), and `book_appointment`, which saves a reservation safely. |
| `validation.py` | Normalises and validates the customer's name, email and notes. |
| `security.py` | CSRF tokens, the `login_required` decorator, open-redirect protection and security headers. |
| `public.py` / `admin.py` | Thin route handlers. They read the request, call the modules above and render a template or redirect. |
| `templates/`, `static/` | Bootstrap 5 UI with a custom theme (`style.css`) and a small progressive-enhancement script (`app.js`). |

## 3. Key flows

### 3.1 Customer booking

1. `GET /book`: `availability_overview()` loads the weekly hours and all booked slots in the booking window with two queries. It then builds the open slots for each day, leaving out past times, closed days and booked times.
2. The customer clicks a slot, which calls `GET /book/details?date=…&time=…`. The slot is checked again with `check_slot()` before the form is shown.
3. `POST /book`:
   1. The CSRF token is verified.
   2. Name, email and notes are validated. Errors redisplay the form with HTTP 400 and messages next to the fields.
   3. `book_appointment()` opens `BEGIN IMMEDIATE`, which takes SQLite's write lock. It runs `check_slot()` (valid format, not past, inside the window, a working day, inside the hours, not booked) and then `INSERT`s.
   4. If the `INSERT` violates the unique index (`sqlite3.IntegrityError`), the transaction is rolled back and the customer sees *"Sorry, that time slot has already been booked."*
4. On success the browser is redirected (Post/Redirect/Get) to `/booking/<reference>`. The reference is a random 12-character hex code.

### 3.2 Double-booking prevention (defence in depth)

| Layer | Mechanism |
|-------|-----------|
| UI | Booked and past slots are not displayed. |
| Server check | `check_slot()` runs inside a write transaction just before the insert. |
| Serialisation | `BEGIN IMMEDIATE` means only one booking transaction can write at a time. |
| Database | `CREATE UNIQUE INDEX … ON appointments(appointment_date, start_time) WHERE status = 'booked'` makes SQLite reject a second active booking even if application code is bypassed. |
| Release | Cancelling sets `status = 'cancelled'`. That row leaves the partial index, so the slot can be booked again, and the history is kept. |

### 3.3 Administration

- **Login:** `models.verify_admin()` compares the password with a Werkzeug scrypt hash. On success the session is cleared and replaced (preventing session fixation), marked permanent (2-hour lifetime) and given `admin_id`. Unknown usernames are checked against a dummy hash, so response time does not reveal which usernames exist.
- **Authorisation:** `security.load_admin()` runs before every request. `@login_required` redirects anonymous users to the login page with a validated local `next` URL.
- **Cancel:** `POST /admin/appointments/<id>/cancel` (POST + CSRF only) runs a conditional `UPDATE … WHERE status = 'booked'`, so cancelling twice is harmless.
- **Availability:** seven rows (Mon–Sun) with a working flag and start and end times chosen from the 30-minute grid. Server-side validation requires values from the grid and *start < end*, matching the database CHECK constraint. After saving, upcoming bookings that no longer fit the new hours are counted and flagged. They are never deleted automatically.

## 4. Time handling

- All appointment dates and times are stored as **provider-local** text (`YYYY-MM-DD`, `HH:MM`) in the single configured timezone (`APPOINTLY_TIMEZONE`). Zero-padded strings sort and compare correctly in SQL.
- "Now" is computed with `zoneinfo` in that timezone, so the "in the past" rule is correct whatever timezone the server machine uses. The `tzdata` package supplies timezone data on Windows.
- Audit timestamps (`created_at`, `cancelled_at`) are stored in UTC (ISO 8601).

## 5. Security summary

| Concern | Measure |
|---------|---------|
| SQL injection | Parameterised queries only. The one dynamic `ORDER BY` uses fixed literals chosen in code. LIKE wildcards in search are escaped. |
| XSS | Jinja2 autoescaping. Customer input is never marked safe. |
| CSRF | A per-session random token is required on every POST and compared with `hmac.compare_digest`. |
| Passwords | Stored only as Werkzeug scrypt hashes. Created through a CLI prompt, never in source or `.env`. |
| Sessions | Signed cookie, `HttpOnly`, `SameSite=Lax`, optional `Secure`, renewed on login, 2-hour lifetime. |
| Secrets | `SECRET_KEY` comes from the environment or `.env`. `.env` is excluded by `.gitignore`. |
| Headers | `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, and `Cache-Control: no-store` on admin pages. |
| Input | Every booking field is validated on the server: strict date and time formats, slot grid, name and email patterns, length limits. |

## 6. Testing strategy

- **Unit tests:** `scheduling.py` and `validation.py` (pure functions).
- **Integration tests:** the Flask test client exercises full HTTP flows against a temporary SQLite file per test.
- **Determinism:** `scheduling.current_time` is replaced with a fixed time (Monday 2 Nov 2026, 10:15 New York), so results do not depend on the day the tests run.
- **Database guarantees:** tested directly with raw SQL, and through a simulated race in which the application check is bypassed and the unique index must catch the conflict.

## 7. Known limitations

- A single provider with one block of hours per weekday (no lunch breaks or one-off holidays).
- Changes to working hours do not cancel existing bookings. They are flagged for the admin to handle.
- Flask's built-in server is intended for local or demo use. A production deployment would use a WSGI server such as Waitress, run over HTTPS, and add login rate limiting.
