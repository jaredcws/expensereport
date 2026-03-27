from __future__ import annotations

from typing import Any

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from expense_report_app.services.calculations import (
    calculate_mileage_reimbursement,
    calculate_mileage_subtotal,
    calculate_misc_subtotal,
    calculate_period_total,
)
from expense_report_app.ui.table_models import EditableTableModel
from expense_report_app.utils.formatters import as_currency
from expense_report_app.utils.validators import is_number, validate_report_inputs


MILEAGE_KEYS = [
    "date",
    "project_number",
    "destination",
    "reimbursable_expense",
    "number_of_miles",
    "miles_reimbursement",
]
MISC_KEYS = [
    "date",
    "receipt_number",
    "description",
    "reimbursable_expense",
    "receipt_enclosed",
    "amount",
    "receipt_file",
]


class ReportForm(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.current_report_id: int | None = None

        self.employee_name_input = QLineEdit()
        self.date_from_input = QDateEdit()
        self.date_from_input.setCalendarPopup(True)
        self.date_from_input.setDisplayFormat("yyyy-MM-dd")
        self.date_from_input.setDate(QDate.currentDate())
        self.date_to_input = QDateEdit()
        self.date_to_input.setCalendarPopup(True)
        self.date_to_input.setDisplayFormat("yyyy-MM-dd")
        self.date_to_input.setDate(QDate.currentDate())
        self.mileage_rate_input = QDoubleSpinBox()
        self.mileage_rate_input.setDecimals(2)
        self.mileage_rate_input.setMaximum(999)
        self.mileage_rate_input.setValue(0.67)

        header_group = QGroupBox("Header / Report Info")
        header_layout = QFormLayout()
        header_layout.addRow("Employee Name", self.employee_name_input)
        header_layout.addRow("Date From", self.date_from_input)
        header_layout.addRow("Date To", self.date_to_input)
        header_layout.addRow("Mileage Rate", self.mileage_rate_input)
        header_group.setLayout(header_layout)

        self.mileage_model = EditableTableModel(
            [
                "Date",
                "Project Number",
                "Destination",
                "Reimbursable Expense",
                "Number of Miles",
                "Miles Reimbursement",
            ],
            [],
            MILEAGE_KEYS,
            read_only={"miles_reimbursement"},
        )
        self.mileage_table = QTableView()
        self.mileage_table.setModel(self.mileage_model)

        self.misc_model = EditableTableModel(
            [
                "Date",
                "Receipt Number",
                "Description",
                "Reimbursable Expense",
                "Receipt Enclosed",
                "Amount",
                "Receipt File",
            ],
            [],
            MISC_KEYS,
        )
        self.misc_table = QTableView()
        self.misc_table.setModel(self.misc_model)

        mileage_group = QGroupBox("Mileage Entries")
        mileage_group_layout = QVBoxLayout()
        mileage_group_layout.addWidget(self.mileage_table)
        mileage_buttons = QHBoxLayout()
        self.add_mileage_btn = QPushButton("Add Mileage Row")
        self.remove_mileage_btn = QPushButton("Remove Mileage Row")
        mileage_buttons.addWidget(self.add_mileage_btn)
        mileage_buttons.addWidget(self.remove_mileage_btn)
        mileage_group_layout.addLayout(mileage_buttons)
        mileage_group.setLayout(mileage_group_layout)

        misc_group = QGroupBox("Miscellaneous Entries")
        misc_group_layout = QVBoxLayout()
        misc_group_layout.addWidget(self.misc_table)
        misc_buttons = QHBoxLayout()
        self.add_misc_btn = QPushButton("Add Misc Row")
        self.remove_misc_btn = QPushButton("Remove Misc Row")
        self.attach_receipt_btn = QPushButton("Attach Receipt")
        misc_buttons.addWidget(self.add_misc_btn)
        misc_buttons.addWidget(self.remove_misc_btn)
        misc_buttons.addWidget(self.attach_receipt_btn)
        misc_group_layout.addLayout(misc_buttons)
        misc_group.setLayout(misc_group_layout)

        totals_group = QGroupBox("Totals")
        totals_layout = QFormLayout()
        self.mileage_subtotal_label = QLabel("$0.00")
        self.misc_subtotal_label = QLabel("$0.00")
        self.total_period_label = QLabel("$0.00")
        totals_layout.addRow("Mileage Subtotal", self.mileage_subtotal_label)
        totals_layout.addRow("Misc Subtotal", self.misc_subtotal_label)
        totals_layout.addRow("Total This Period", self.total_period_label)
        totals_group.setLayout(totals_layout)

        main_layout = QVBoxLayout()
        main_layout.addWidget(header_group)
        main_layout.addWidget(mileage_group)
        main_layout.addWidget(misc_group)
        main_layout.addWidget(totals_group)
        self.setLayout(main_layout)

        self.add_mileage_btn.clicked.connect(self.add_mileage_row)
        self.remove_mileage_btn.clicked.connect(self.remove_mileage_row)
        self.add_misc_btn.clicked.connect(self.add_misc_row)
        self.remove_misc_btn.clicked.connect(self.remove_misc_row)
        self.attach_receipt_btn.clicked.connect(self.placeholder_attach_receipt)
        self.mileage_model.dataChanged.connect(self.recalculate_totals)
        self.misc_model.dataChanged.connect(self.recalculate_totals)
        self.mileage_rate_input.valueChanged.connect(lambda _v: self.recalculate_totals())

    def default_mileage_item(self) -> dict[str, Any]:
        return {
            "date": "",
            "project_number": "",
            "destination": "",
            "reimbursable_expense": "",
            "number_of_miles": "0",
            "miles_reimbursement": "0.00",
        }

    def default_misc_item(self) -> dict[str, Any]:
        return {
            "date": "",
            "receipt_number": "",
            "description": "",
            "reimbursable_expense": "",
            "receipt_enclosed": False,
            "amount": "0.00",
            "receipt_file": "",
        }

    def add_mileage_row(self) -> None:
        self.mileage_model.insert_empty_row(self.default_mileage_item())

    def remove_mileage_row(self) -> None:
        self.mileage_model.remove_row(self.mileage_table.currentIndex().row())
        self.recalculate_totals()

    def add_misc_row(self) -> None:
        self.misc_model.insert_empty_row(self.default_misc_item())

    def remove_misc_row(self) -> None:
        self.misc_model.remove_row(self.misc_table.currentIndex().row())
        self.recalculate_totals()

    def placeholder_attach_receipt(self) -> None:
        row_index = self.misc_table.currentIndex().row()
        if row_index < 0:
            QMessageBox.information(
                self,
                "Attach Receipt",
                "Select a miscellaneous row first, then choose a receipt file.",
            )
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Receipt",
            "",
            "Receipt Files (*.png *.jpg *.jpeg *.pdf *.tiff *.bmp);;All Files (*)",
        )
        if not file_path:
            return
        self.misc_model.rows[row_index]["receipt_file"] = file_path
        self.misc_model.layoutChanged.emit()

    def apply_settings_defaults(self, settings: dict[str, str]) -> None:
        if settings.get("default_employee_name"):
            self.employee_name_input.setText(settings["default_employee_name"])
        rate = settings.get("default_mileage_rate", "0.67")
        if is_number(rate):
            self.mileage_rate_input.setValue(float(rate))

    def reset_form(self, settings: dict[str, str]) -> None:
        self.current_report_id = None
        self.employee_name_input.clear()
        self.date_from_input.setDate(QDate.currentDate())
        self.date_to_input.setDate(QDate.currentDate())
        self.mileage_model.replace_rows([])
        self.misc_model.replace_rows([])
        self.apply_settings_defaults(settings)
        self.recalculate_totals()

    def recalculate_totals(self) -> None:
        rate = self.mileage_rate_input.value()
        for row in self.mileage_model.rows:
            miles = row.get("number_of_miles", "0")
            if is_number(str(miles)):
                row["miles_reimbursement"] = f"{calculate_mileage_reimbursement(miles, rate):.2f}"
            else:
                row["miles_reimbursement"] = "0.00"

        mileage_subtotal = calculate_mileage_subtotal(self.mileage_model.rows, rate)
        misc_subtotal = calculate_misc_subtotal(self.misc_model.rows)
        total = calculate_period_total(mileage_subtotal, misc_subtotal)

        self.mileage_subtotal_label.setText(as_currency(mileage_subtotal))
        self.misc_subtotal_label.setText(as_currency(misc_subtotal))
        self.total_period_label.setText(as_currency(total))
        self.mileage_model.layoutChanged.emit()

    def collect_report_data(self) -> dict[str, Any] | None:
        errors = validate_report_inputs(
            self.employee_name_input.text(),
            self.date_from_input.date().toString("yyyy-MM-dd"),
            self.date_to_input.date().toString("yyyy-MM-dd"),
            str(self.mileage_rate_input.value()),
        )

        for idx, item in enumerate(self.mileage_model.rows, start=1):
            if item.get("number_of_miles") and not is_number(item["number_of_miles"]):
                errors.append(f"Mileage row {idx}: Number of Miles must be numeric.")
        for idx, item in enumerate(self.misc_model.rows, start=1):
            if item.get("amount") and not is_number(item["amount"]):
                errors.append(f"Misc row {idx}: Amount must be numeric.")

        if errors:
            QMessageBox.warning(self, "Validation Error", "\n".join(errors))
            return None

        mileage_subtotal = float(self.mileage_subtotal_label.text().replace("$", ""))
        misc_subtotal = float(self.misc_subtotal_label.text().replace("$", ""))
        total_period = float(self.total_period_label.text().replace("$", ""))

        return {
            "id": self.current_report_id,
            "employee_name": self.employee_name_input.text().strip(),
            "date_from": self.date_from_input.date().toString("yyyy-MM-dd"),
            "date_to": self.date_to_input.date().toString("yyyy-MM-dd"),
            "mileage_rate": round(self.mileage_rate_input.value(), 2),
            "mileage_subtotal": mileage_subtotal,
            "misc_subtotal": misc_subtotal,
            "total_period": total_period,
            "mileage_items": self.mileage_model.rows,
            "misc_items": self.misc_model.rows,
        }

    def load_report_data(self, data: dict[str, Any]) -> None:
        self.current_report_id = data.get("id")
        self.employee_name_input.setText(data.get("employee_name", ""))
        date_from = QDate.fromString(data.get("date_from", ""), "yyyy-MM-dd")
        date_to = QDate.fromString(data.get("date_to", ""), "yyyy-MM-dd")
        self.date_from_input.setDate(date_from if date_from.isValid() else QDate.currentDate())
        self.date_to_input.setDate(date_to if date_to.isValid() else QDate.currentDate())
        self.mileage_rate_input.setValue(float(data.get("mileage_rate", 0.67)))
        self.mileage_model.replace_rows(data.get("mileage_items", []))
        self.misc_model.replace_rows(data.get("misc_items", []))
        self.recalculate_totals()
