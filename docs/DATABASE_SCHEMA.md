# Appointly – Database Schema

- **Engine:** SQLite 3 (Python's built-in `sqlite3` module)
- **File:** `instance\appointly.sqlite3` by default (`APPOINTLY_DATABASE` overrides it)
- **Definition:** [`appointly/schema.sql`](../appointly/schema.sql). It is applied by `flask --app appointly init-db` and automatically at application start-up. Every statement uses `IF NOT EXISTS` / `INSERT OR IGNORE`, so existing data is never overwritten.

## Entity overview

```
┌──────────────────────┐        ┌──────────────────────────────┐        ┌────────────────────┐
│ availability         │        │ appointments                 │        │ admin_users        │
├──────────────────────┤        ├──────────────────────────────┤        ├────────────────────┤
│ PK weekday   INTEGER │        │ PK id              INTEGER   │        │ PK id      INTEGER │
│    is_working INTEGER│        │ UQ reference       TEXT      │        │ UQ username TEXT   │
│    start_time TEXT   │        │    customer_name   TEXT      │        │    password_hash   │
│    end_time   TEXT   │        │    customer_email  TEXT      │        │    created_at      │
└──────────────────────┘        │    notes           TEXT      │        └────────────────────┘
   7 rows (Mon..Sun)            │    appointment_date TEXT  ┐  │
                                │    start_time       TEXT  ┘ UQ when status = 'booked'
                                │    status          TEXT      │
                                │    created_at      TEXT      │
                                │    cancelled_at    TEXT      │
                                └──────────────────────────────┘
```

The tables have no foreign keys between them. An appointment is linked to availability through its weekday and time, which are checked by the application when booking. With only one provider, no provider table is needed.

---

## Table `availability`

Weekly working hours. There is exactly one row per weekday.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `weekday` | INTEGER | PRIMARY KEY, `CHECK (weekday BETWEEN 0 AND 6)` | 0 = Monday … 6 = Sunday (Python's `date.weekday()`). |
| `is_working` | INTEGER | NOT NULL, default 0, `CHECK (is_working IN (0,1))` | 1 = bookable day, 0 = closed. |
| `start_time` | TEXT | NOT NULL, default `'09:00'` | First slot start, `HH:MM`, provider local time. |
| `end_time` | TEXT | NOT NULL, default `'17:00'` | End of the working day, `HH:MM`. The last slot starts 30 minutes earlier. |
| | | `CHECK (start_time < end_time)` | Valid even for closed days. Zero-padded text compares correctly. |

**Seed data (demonstration):**

| weekday | is_working | start_time | end_time |
|---------|-----------|------------|----------|
| 0 Monday | 1 | 09:00 | 17:00 |
| 1 Tuesday | 1 | 09:00 | 17:00 |
| 2 Wednesday | 1 | 09:00 | 17:00 |
| 3 Thursday | 1 | 09:00 | 17:00 |
| 4 Friday | 1 | 09:00 | 17:00 |
| 5 Saturday | 1 | 10:00 | 14:00 |
| 6 Sunday | 0 | 09:00 | 17:00 |

## Table `appointments`

One row per reservation. Cancelled rows are kept as history.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Internal identifier (used in admin URLs). |
| `reference` | TEXT | NOT NULL, UNIQUE | Random 12-character hex code shown to the customer and used in the confirmation URL. It is hard to guess, so customers cannot browse other customers' bookings. |
| `customer_name` | TEXT | NOT NULL | 2–80 characters, validated on the server. |
| `customer_email` | TEXT | NOT NULL | Lower-cased, validated, at most 254 characters. |
| `notes` | TEXT | NOT NULL, default `''` | Optional customer notes, at most 500 characters. |
| `appointment_date` | TEXT | NOT NULL | `YYYY-MM-DD` in the provider's timezone. |
| `start_time` | TEXT | NOT NULL | `HH:MM` on the 30-minute grid. The end time is always start + 30 minutes. |
| `status` | TEXT | NOT NULL, default `'booked'`, `CHECK (status IN ('booked','cancelled'))` | Lifecycle state. "Completed" is shown in the UI for past booked rows; it is not stored. |
| `created_at` | TEXT | NOT NULL | ISO 8601 timestamp in UTC. |
| `cancelled_at` | TEXT | NULL | ISO 8601 UTC, set when cancelled. |

### Indexes

| Name | Definition | Purpose |
|------|-----------|---------|
| `ux_appointments_active_slot` | `UNIQUE (appointment_date, start_time) WHERE status = 'booked'` | **Double-booking prevention at the database level.** Only one active booking can exist per slot. It is a *partial* index, so cancelled rows are not included, and cancelling a booking frees the slot for a new one while the history is kept. |
| `ix_appointments_date` | `(appointment_date, start_time)` | Fast lookups by date for the booking page and dashboard. |
| *(automatic)* | `UNIQUE (reference)` | Guarantees each confirmation code is unique. |

**Example – the database itself rejects a double booking:**

```sql
INSERT INTO appointments (reference, customer_name, customer_email, appointment_date, start_time, status, created_at)
VALUES ('A1', 'Alex Morgan', 'alex@example.com', '2026-11-03', '10:00', 'booked', '2026-11-01T12:00:00+00:00');

INSERT INTO appointments (reference, customer_name, customer_email, appointment_date, start_time, status, created_at)
VALUES ('B2', 'Blake Chen', 'blake@example.com', '2026-11-03', '10:00', 'booked', '2026-11-01T12:00:05+00:00');
-- Error: UNIQUE constraint failed: appointments.appointment_date, appointments.start_time

UPDATE appointments SET status = 'cancelled' WHERE reference = 'A1';
-- The second INSERT now succeeds: the slot was released.
```

## Table `admin_users`

Administrator accounts. Created with `flask --app appointly create-admin`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Stored in the session after login. |
| `username` | TEXT | NOT NULL, UNIQUE, `COLLATE NOCASE` | Case-insensitive login name. |
| `password_hash` | TEXT | NOT NULL | Werkzeug `generate_password_hash` output (scrypt with a random salt). The plain-text password is never stored. |
| `created_at` | TEXT | NOT NULL | ISO 8601 UTC. |

## Transactions and connection settings

- Connections are opened in autocommit mode (`isolation_level=None`) with a 10-second busy timeout.
- Creating a booking uses `BEGIN IMMEDIATE … COMMIT`. This takes the write lock *before* the availability check, so two simultaneous requests are processed one after the other. If anything fails, the transaction is rolled back.
- Other writes (cancel, availability update, admin creation) are single statements and are atomic on their own.

## Data conventions

- Dates and times are stored as fixed-width, zero-padded text. Ordering and comparison work without date functions, for example `appointment_date || ' ' || start_time >= '2026-11-02 10:15'` finds upcoming appointments.
- All demonstration customer data is fictional and uses the reserved `example.com` / `example.org` domains.
