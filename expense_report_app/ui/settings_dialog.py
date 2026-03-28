from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(self, settings: dict[str, str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Application Settings")

        self.default_employee_name = QLineEdit(settings.get("default_employee_name", ""))
        self.default_mileage_rate = QLineEdit(settings.get("default_mileage_rate", "0.67"))
        self.partner_name = QLineEdit(settings.get("partner_name", ""))
        self.google_maps_api_key = QLineEdit(settings.get("google_maps_api_key", ""))
        self.google_maps_api_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        self.employee_signature_path = QLineEdit(settings.get("employee_signature_image_path", ""))
        self.partner_signature_path = QLineEdit(
            settings.get("partner_signature_image_path", "") or settings.get("approver_signature_image_path", "")
        )
        self.default_output_folder = QLineEdit(settings.get("default_output_folder", ""))

        form_layout = QFormLayout()
        form_layout.addRow("Default Employee Name", self.default_employee_name)
        form_layout.addRow("Default Mileage Rate", self.default_mileage_rate)
        form_layout.addRow("Partner Name", self.partner_name)
        form_layout.addRow("Google Maps API Key", self.google_maps_api_key)
        form_layout.addRow("Employee Signature Image Path", self._row_with_picker(self.employee_signature_path, file_mode=True))
        form_layout.addRow("Partner Signature Image Path", self._row_with_picker(self.partner_signature_path, file_mode=True))
        form_layout.addRow("Default Output Folder", self._row_with_picker(self.default_output_folder, file_mode=False))

        button_row = QHBoxLayout()
        save_btn = QPushButton("Save")
        cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(save_btn)
        button_row.addWidget(cancel_btn)

        layout = QVBoxLayout()
        layout.addLayout(form_layout)
        layout.addLayout(button_row)
        self.setLayout(layout)

    def _row_with_picker(self, line_edit: QLineEdit, file_mode: bool) -> QHBoxLayout:
        row = QHBoxLayout()
        browse = QPushButton("Browse")

        def on_browse() -> None:
            if file_mode:
                path, _ = QFileDialog.getOpenFileName(self, "Select File")
            else:
                path = QFileDialog.getExistingDirectory(self, "Select Folder")
            if path:
                line_edit.setText(path)

        browse.clicked.connect(on_browse)
        row.addWidget(line_edit)
        row.addWidget(browse)
        return row

    def to_dict(self) -> dict[str, str]:
        return {
            "default_employee_name": self.default_employee_name.text().strip(),
            "default_mileage_rate": self.default_mileage_rate.text().strip(),
            "partner_name": self.partner_name.text().strip(),
            "google_maps_api_key": self.google_maps_api_key.text().strip(),
            "employee_signature_image_path": self.employee_signature_path.text().strip(),
            "partner_signature_image_path": self.partner_signature_path.text().strip(),
            "approver_signature_image_path": self.partner_signature_path.text().strip(),
            "default_output_folder": self.default_output_folder.text().strip(),
        }
