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
    destination TEXT,
    reimbursable_expense TEXT,
    number_of_miles REAL NOT NULL DEFAULT 0,
    miles_reimbursement REAL NOT NULL DEFAULT 0,
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
        existing_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(misc_items)").fetchall()
        }
        if "receipt_file_path" not in existing_columns:
            conn.execute("ALTER TABLE misc_items ADD COLUMN receipt_file_path TEXT")
        conn.commit()
