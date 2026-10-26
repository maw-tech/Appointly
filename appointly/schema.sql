-- Appointly database schema (SQLite).
-- All statements are idempotent so the schema can be applied on every start.

-- Weekly working hours: one row per weekday (0 = Monday ... 6 = Sunday).
CREATE TABLE IF NOT EXISTS availability (
    weekday     INTEGER PRIMARY KEY CHECK (weekday BETWEEN 0 AND 6),
    is_working  INTEGER NOT NULL DEFAULT 0 CHECK (is_working IN (0, 1)),
    start_time  TEXT    NOT NULL DEFAULT '09:00',   -- HH:MM, provider local time
    end_time    TEXT    NOT NULL DEFAULT '17:00',   -- HH:MM, provider local time
    CHECK (start_time < end_time)
);

-- Customer reservations. Dates and times are in the provider's timezone.
CREATE TABLE IF NOT EXISTS appointments (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    reference         TEXT    NOT NULL UNIQUE,      -- unguessable code shown to the customer
    customer_name     TEXT    NOT NULL,
    customer_email    TEXT    NOT NULL,
    notes             TEXT    NOT NULL DEFAULT '',
    appointment_date  TEXT    NOT NULL,             -- YYYY-MM-DD
    start_time        TEXT    NOT NULL,             -- HH:MM (slot length is 30 minutes)
    status            TEXT    NOT NULL DEFAULT 'booked'
                              CHECK (status IN ('booked', 'cancelled')),
    created_at        TEXT    NOT NULL,             -- ISO 8601, UTC
    cancelled_at      TEXT                          -- ISO 8601, UTC
);

-- Double-booking protection at the database level: at most ONE active
-- ('booked') appointment per date and start time. Cancelled rows are not
-- covered by this partial index, so cancelling releases the slot.
CREATE UNIQUE INDEX IF NOT EXISTS ux_appointments_active_slot
    ON appointments (appointment_date, start_time)
    WHERE status = 'booked';

CREATE INDEX IF NOT EXISTS ix_appointments_date
    ON appointments (appointment_date, start_time);

-- Administrator accounts (passwords are stored as salted hashes only).
CREATE TABLE IF NOT EXISTS admin_users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    username       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

-- Demonstration availability: Mon-Fri 09:00-17:00, Saturday 10:00-14:00,
-- Sunday closed. INSERT OR IGNORE keeps any hours the admin has changed.
INSERT OR IGNORE INTO availability (weekday, is_working, start_time, end_time) VALUES
    (0, 1, '09:00', '17:00'),
    (1, 1, '09:00', '17:00'),
    (2, 1, '09:00', '17:00'),
    (3, 1, '09:00', '17:00'),
    (4, 1, '09:00', '17:00'),
    (5, 1, '10:00', '14:00'),
    (6, 0, '09:00', '17:00');
