from __future__ import annotations

from pathlib import Path

from expense_report_app.database.db import Database
from expense_report_app.database.repositories import SettingsRepository


DEFAULT_SETTINGS = {
    "default_employee_name": "",
    "default_mileage_rate": "0.67",
    "employee_signature_image_path": "",
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
        if not existing:
            self.repo.set_many(merged)
        return merged

    def update_settings(self, settings: dict[str, str]) -> None:
        self.repo.set_many(settings)
