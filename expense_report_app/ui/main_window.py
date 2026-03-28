from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from expense_report_app.services.report_service import ReportService
from expense_report_app.services.receipt_service import ReceiptService
from expense_report_app.services.settings_service import SettingsService
from expense_report_app.services.pdf_generator import PdfGenerator
from expense_report_app.ui.report_form import ReportForm
from expense_report_app.ui.settings_dialog import SettingsDialog
from expense_report_app.utils.validators import is_number


class MainWindow(QMainWindow):
    def __init__(
        self,
        report_service: ReportService,
        settings_service: SettingsService,
        receipt_service: ReceiptService,
    ) -> None:
        super().__init__()
        self.report_service = report_service
        self.settings_service = settings_service
        self.pdf_generator = PdfGenerator()
        self.settings = self.settings_service.get_settings()

        self.setWindowTitle("Expense Report App")
        self.resize(1300, 800)

        self.report_form = ReportForm(receipt_service)
        self.report_form.apply_settings_defaults(self.settings)

        toolbar_layout = QHBoxLayout()
        self.new_btn = QPushButton("New Report")
        self.open_btn = QPushButton("Open Report")
        self.save_btn = QPushButton("Save Draft")
        self.settings_btn = QPushButton("Settings")
        self.generate_pdf_btn = QPushButton("Generate PDF")

        toolbar_layout.addWidget(self.new_btn)
        toolbar_layout.addWidget(self.open_btn)
        toolbar_layout.addWidget(self.save_btn)
        toolbar_layout.addWidget(self.settings_btn)
        toolbar_layout.addWidget(self.generate_pdf_btn)

        root = QWidget()
        root_layout = QVBoxLayout()
        root_layout.addLayout(toolbar_layout)
        root_layout.addWidget(self.report_form)
        root.setLayout(root_layout)
        self.setCentralWidget(root)

        self.new_btn.clicked.connect(self.on_new_report)
        self.open_btn.clicked.connect(self.on_open_report)
        self.save_btn.clicked.connect(self.on_save_report)
        self.settings_btn.clicked.connect(self.on_settings)
        self.generate_pdf_btn.clicked.connect(self.on_generate_pdf)

    def on_new_report(self) -> None:
        self.report_form.reset_form(self.settings)

    def on_open_report(self) -> None:
        reports = self.report_service.list_reports()
        if not reports:
            QMessageBox.information(self, "Open Report", "No saved reports found.")
            return

        choices = [
            f"#{r['id']} | {r['employee_name']} | {r['date_from']} to {r['date_to']} | ${r['total_period']:.2f}"
            for r in reports
        ]
        selected, ok = QInputDialog.getItem(self, "Open Report", "Select a saved draft:", choices, editable=False)
        if not ok:
            return

        report_id = int(selected.split("|")[0].strip().replace("#", ""))
        report_data = self.report_service.load_report(report_id)
        if not report_data:
            QMessageBox.warning(self, "Open Report", "Could not load selected report.")
            return
        self.report_form.load_report_data(report_data)

    def on_save_report(self) -> None:
        data = self.report_form.collect_report_data()
        if not data:
            return

        report_id = self.report_service.save_draft(data)
        self.report_form.current_report_id = report_id
        QMessageBox.information(self, "Save Draft", f"Draft saved (ID: {report_id}).")

    def on_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self)
        if dialog.exec():
            new_settings = dialog.to_dict()
            if not is_number(new_settings.get("default_mileage_rate", "")):
                QMessageBox.warning(self, "Settings", "Default Mileage Rate must be numeric.")
                return
            self.settings_service.update_settings(new_settings)
            self.settings = self.settings_service.get_settings()
            self.report_form.update_integration_settings(self.settings)
            QMessageBox.information(self, "Settings", "Settings updated.")

    def on_generate_pdf(self) -> None:
        data = self.report_form.collect_report_data()
        if not data:
            return

        report_id = self.report_service.save_draft(data)
        self.report_form.current_report_id = report_id
        data["id"] = report_id

        try:
            output_dir = Path(self.settings.get("default_output_folder", "")).expanduser()
            pdf_path = self.pdf_generator.generate_report_pdf(data, output_dir, self.settings)
        except Exception as exc:
            QMessageBox.warning(self, "Generate PDF", f"Could not generate the PDF.\n\n{exc}")
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        QMessageBox.information(
            self,
            "Generate PDF",
            f"PDF generated successfully.\n\n{pdf_path}",
        )
