from __future__ import annotations

from typing import Any

from expense_report_app.database.db import Database


class ReportRepository:
    def __init__(self, db: Database):
        self.db = db

    def list_reports(self) -> list[dict[str, Any]]:
        rows = self.db.fetchall(
            """
            SELECT id, employee_name, date_from, date_to, total_period, updated_at
            FROM reports
            ORDER BY updated_at DESC
            """
        )
        return [dict(row) for row in rows]

    def save_report(self, report: dict[str, Any], mileage_items: list[dict[str, Any]], misc_items: list[dict[str, Any]]) -> int:
        with self.db.connect() as conn:
            if report.get("id"):
                report_id = report["id"]
                conn.execute(
                    """
                    UPDATE reports
                    SET employee_name=?, date_from=?, date_to=?, mileage_rate=?,
                        mileage_subtotal=?, misc_subtotal=?, total_period=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        report["employee_name"],
                        report["date_from"],
                        report["date_to"],
                        report["mileage_rate"],
                        report["mileage_subtotal"],
                        report["misc_subtotal"],
                        report["total_period"],
                        report_id,
                    ),
                )
                conn.execute("DELETE FROM mileage_items WHERE report_id=?", (report_id,))
                conn.execute("DELETE FROM misc_items WHERE report_id=?", (report_id,))
            else:
                cur = conn.execute(
                    """
                    INSERT INTO reports(
                        employee_name, date_from, date_to, mileage_rate,
                        mileage_subtotal, misc_subtotal, total_period, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft')
                    """,
                    (
                        report["employee_name"],
                        report["date_from"],
                        report["date_to"],
                        report["mileage_rate"],
                        report["mileage_subtotal"],
                        report["misc_subtotal"],
                        report["total_period"],
                    ),
                )
                report_id = cur.lastrowid

            conn.executemany(
                """
                INSERT INTO mileage_items(
                    report_id, item_date, project_number, destination,
                    reimbursable_expense, number_of_miles, miles_reimbursement
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        report_id,
                        item.get("date", ""),
                        item.get("project_number", ""),
                        item.get("destination", ""),
                        item.get("reimbursable_expense", ""),
                        item.get("number_of_miles", 0),
                        item.get("miles_reimbursement", 0),
                    )
                    for item in mileage_items
                ],
            )

            conn.executemany(
                """
                INSERT INTO misc_items(
                    report_id, item_date, receipt_number, description,
                    reimbursable_expense, receipt_enclosed, amount, receipt_file_path, receipt_file_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        report_id,
                        item.get("date", ""),
                        item.get("receipt_number", ""),
                        item.get("description", ""),
                        item.get("reimbursable_expense", ""),
                        1 if item.get("receipt_enclosed") else 0,
                        item.get("amount", 0),
                        item.get("receipt_file", ""),
                        None,
                    )
                    for item in misc_items
                ],
            )
            conn.commit()
            return report_id

    def load_report(self, report_id: int) -> dict[str, Any] | None:
        report_row = self.db.fetchone("SELECT * FROM reports WHERE id=?", (report_id,))
        if not report_row:
            return None

        mileage_rows = self.db.fetchall(
            "SELECT * FROM mileage_items WHERE report_id=? ORDER BY id", (report_id,)
        )
        misc_rows = self.db.fetchall("SELECT * FROM misc_items WHERE report_id=? ORDER BY id", (report_id,))

        report = dict(report_row)
        report["mileage_items"] = [
            {
                "date": row["item_date"],
                "project_number": row["project_number"],
                "destination": row["destination"],
                "reimbursable_expense": row["reimbursable_expense"],
                "number_of_miles": row["number_of_miles"],
                "miles_reimbursement": row["miles_reimbursement"],
            }
            for row in mileage_rows
        ]
        report["misc_items"] = [
            {
                "date": row["item_date"],
                "receipt_number": row["receipt_number"],
                "description": row["description"],
                "reimbursable_expense": row["reimbursable_expense"],
                "receipt_enclosed": bool(row["receipt_enclosed"]),
                "amount": row["amount"],
                "receipt_file": row["receipt_file_path"] or "",
            }
            for row in misc_rows
        ]
        return report


class SettingsRepository:
    def __init__(self, db: Database):
        self.db = db

    def get_all(self) -> dict[str, str]:
        rows = self.db.fetchall("SELECT key, value FROM app_settings")
        return {row["key"]: row["value"] for row in rows}

    def set_many(self, payload: dict[str, str]) -> None:
        with self.db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO app_settings(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                list(payload.items()),
            )
            conn.commit()
