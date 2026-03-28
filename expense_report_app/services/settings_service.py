from __future__ import annotations

from pathlib import Path

from expense_report_app.database.db import Database
from expense_report_app.database.repositories import SettingsRepository


DEFAULT_SETTINGS = {
    "default_employee_name": "",
    "default_mileage_rate": "0.67",
    "partner_name": "",
    "employee_signature_image_path": "",
    "partner_signature_image_path": "",
    "approver_signature_image_path": "",
    "default_output_folder": str(
        Path(__file__).resolve().parents[1] / "data" / "generated_pdfs"
    ),
}


class SettingsService:
    def __init__(self, db: Database):
        self.repo = SettingsRepository(db)

    def get_settings(self) -> dict[str, str]:
        existing = self.repo.get_all()
        merged = DEFAULT_SETTINGS | existing
        partner_signature = merged.get("partner_signature_image_path", "").strip()
        legacy_approver_signature = merged.get("approver_signature_image_path", "").strip()
        if not partner_signature and legacy_approver_signature:
            merged["partner_signature_image_path"] = legacy_approver_signature
            self.repo.set_many({"partner_signature_image_path": legacy_approver_signature})
        if not existing:
            self.repo.set_many(merged)
        return merged

    def update_settings(self, settings: dict[str, str]) -> None:
        self.repo.set_many(settings)
