from __future__ import annotations

from typing import Any

from expense_report_app.database.db import Database
from expense_report_app.database.repositories import ReportRepository
from expense_report_app.services.receipt_service import ReceiptService


class ReportService:
    def __init__(self, db: Database, receipt_service: ReceiptService):
        self.repo = ReportRepository(db)
        self.receipt_service = receipt_service

    def save_draft(self, report_data: dict[str, Any]) -> int:
        report = {
            "id": report_data.get("id"),
            "employee_name": report_data["employee_name"],
            "date_from": report_data["date_from"],
            "date_to": report_data["date_to"],
            "mileage_rate": report_data["mileage_rate"],
            "mileage_subtotal": report_data["mileage_subtotal"],
            "misc_subtotal": report_data["misc_subtotal"],
            "total_period": report_data["total_period"],
        }
        report_id = self.repo.save_report(report, report_data["mileage_items"], report_data["misc_items"])
        if self.receipt_service.organize_report_receipts(report_id, report_data["misc_items"]):
            report["id"] = report_id
            self.repo.save_report(report, report_data["mileage_items"], report_data["misc_items"])
        return report_id

    def list_reports(self) -> list[dict[str, Any]]:
        return self.repo.list_reports()

    def load_report(self, report_id: int) -> dict[str, Any] | None:
        return self.repo.load_report(report_id)
