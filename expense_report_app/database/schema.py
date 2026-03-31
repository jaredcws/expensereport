from __future__ import annotations

from expense_report_app.database.db import Database


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_name TEXT NOT NULL,
    date_from TEXT NOT NULL,
    date_to TEXT NOT NULL,
    mileage_rate REAL NOT NULL,
    mileage_subtotal REAL NOT NULL DEFAULT 0,
    misc_subtotal REAL NOT NULL DEFAULT 0,
    total_period REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mileage_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    item_date TEXT,
    project_number TEXT,
    start_location TEXT,
    end_location TEXT,
    destination TEXT,
    reimbursable_expense TEXT,
    round_trip INTEGER NOT NULL DEFAULT 1,
    number_of_miles REAL NOT NULL DEFAULT 0,
    miles_reimbursement REAL NOT NULL DEFAULT 0,
    google_maps_url TEXT,
    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS misc_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    item_date TEXT,
    receipt_number TEXT,
    description TEXT,
    reimbursable_expense TEXT,
    receipt_enclosed INTEGER NOT NULL DEFAULT 0,
    amount REAL NOT NULL DEFAULT 0,
    receipt_file_path TEXT,
    receipt_file_id INTEGER,
    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE,
    FOREIGN KEY(receipt_file_id) REFERENCES receipt_files(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS receipt_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER NOT NULL,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    mime_type TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def initialize_schema(db: Database) -> None:
    with db.connect() as conn:
        conn.executescript(SCHEMA_SQL)
        _ensure_column(conn, "misc_items", "receipt_file_path", "TEXT")
        _ensure_column(conn, "mileage_items", "start_location", "TEXT")
        _ensure_column(conn, "mileage_items", "end_location", "TEXT")
        _ensure_column(conn, "mileage_items", "round_trip", "INTEGER NOT NULL DEFAULT 1")
        _ensure_column(conn, "mileage_items", "google_maps_url", "TEXT")
        conn.commit()


def _ensure_column(conn, table_name: str, column_name: str, definition: str) -> None:
    existing_columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")
