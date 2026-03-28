from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from expense_report_app.database.db import Database
from expense_report_app.database.schema import initialize_schema
from expense_report_app.services.report_service import ReportService
from expense_report_app.services.receipt_service import ReceiptService
from expense_report_app.services.settings_service import SettingsService
from expense_report_app.ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)

    data_dir = Path(__file__).resolve().parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "receipts").mkdir(parents=True, exist_ok=True)
    (data_dir / "generated_pdfs").mkdir(parents=True, exist_ok=True)
    (Path(__file__).resolve().parent / "assets" / "signatures").mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "expense_reports.db"

    db = Database(db_path)
    initialize_schema(db)

    settings_service = SettingsService(db)
    report_service = ReportService(db)
    receipt_service = ReceiptService(data_dir / "receipts")

    window = MainWindow(report_service, settings_service, receipt_service)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
