from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QDate, QEvent, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCalendarWidget,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStyledItemDelegate,
    QTableView,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from expense_report_app.services.calculations import (
    calculate_mileage_reimbursement,
    calculate_mileage_subtotal,
    calculate_misc_subtotal,
    calculate_period_total,
)
from expense_report_app.services.google_places_service import GooglePlacesService
from expense_report_app.services.google_routes_service import GoogleRoutesService
from expense_report_app.services.mileage_service import (
    build_google_maps_directions_url,
    build_mileage_description,
)
from expense_report_app.services.receipt_service import ReceiptService
from expense_report_app.ui.address_autocomplete import AddressAutocompleteDelegate
from expense_report_app.ui.table_models import EditableTableModel
from expense_report_app.utils.formatters import as_currency
from expense_report_app.utils.validators import is_number, validate_report_inputs


MILEAGE_KEYS = [
    "date",
    "project_number",
    "start_location",
    "end_location",
    "maps_url",
    "destination",
    "reimbursable_expense",
    "round_trip",
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
GOOGLE_MILEAGE_TRIGGER_KEYS = {"start_location", "end_location", "round_trip"}


class CheckboxDelegate(QStyledItemDelegate):
    def editorEvent(self, event, model, option, index):  # noqa: N802
        if not index.isValid() or not (index.flags() & Qt.ItemIsUserCheckable):
            return super().editorEvent(event, model, option, index)

        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            current = model.data(index, Qt.CheckStateRole)
            next_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
            return model.setData(index, next_state, Qt.CheckStateRole)

        if event.type() == QEvent.KeyPress and event.key() in {Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Select}:
            current = model.data(index, Qt.CheckStateRole)
            next_state = Qt.Unchecked if current == Qt.Checked else Qt.Checked
            return model.setData(index, next_state, Qt.CheckStateRole)

        return super().editorEvent(event, model, option, index)


class ReportForm(QWidget):
    def __init__(self, receipt_service: ReceiptService) -> None:
        super().__init__()
        self.current_report_id: int | None = None
        self.receipt_service = receipt_service
        self.google_places_service = GooglePlacesService(self)
        self.google_routes_service = GoogleRoutesService(self)
        self._route_requests: dict[str, dict[str, Any]] = {}

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
                "Start Location",
                "End Location",
                "Google Maps Route",
                "Destination",
                "Reimbursable Expense",
                "Round Trip",
                "Number of Miles",
                "Miles Reimbursement",
            ],
            [],
            MILEAGE_KEYS,
            read_only={"maps_url", "miles_reimbursement"},
            checkable={"round_trip"},
            link_keys={"maps_url"},
        )
        self.mileage_table = QTableView()
        self.mileage_table.setModel(self.mileage_model)
        self.mileage_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.mileage_table.horizontalHeader().setStretchLastSection(True)
        self.checkbox_delegate = CheckboxDelegate(self)
        self.address_autocomplete_delegate = AddressAutocompleteDelegate(self.google_places_service, self.mileage_table)
        self.mileage_table.setItemDelegateForColumn(
            MILEAGE_KEYS.index("start_location"),
            self.address_autocomplete_delegate,
        )
        self.mileage_table.setItemDelegateForColumn(
            MILEAGE_KEYS.index("end_location"),
            self.address_autocomplete_delegate,
        )
        self.mileage_table.setItemDelegateForColumn(
            MILEAGE_KEYS.index("round_trip"),
            self.checkbox_delegate,
        )

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
            read_only={"receipt_number"},
            checkable={"receipt_enclosed"},
        )
        self.misc_table = QTableView()
        self.misc_table.setModel(self.misc_model)
        self.misc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.misc_table.horizontalHeader().setStretchLastSection(True)
        self.misc_table.setItemDelegateForColumn(
            MISC_KEYS.index("receipt_enclosed"),
            self.checkbox_delegate,
        )

        mileage_group = QGroupBox("Mileage Entries")
        mileage_group_layout = QVBoxLayout()
        mileage_group_layout.addWidget(self.mileage_table)
        mileage_buttons = QHBoxLayout()
        self.add_mileage_btn = QPushButton("Add Mileage Row")
        self.remove_mileage_btn = QPushButton("Remove Mileage Row")
        self.fill_mileage_btn = QPushButton("Open Maps / Fill Mileage")
        mileage_buttons.addWidget(self.add_mileage_btn)
        mileage_buttons.addWidget(self.remove_mileage_btn)
        mileage_buttons.addWidget(self.fill_mileage_btn)
        mileage_group_layout.addLayout(mileage_buttons)
        self.maps_hint_label = QLabel(
            "Type in Start Location and End Location for Google Maps suggestions. "
            "Double-click Google Maps Route to open directions."
        )
        self.maps_hint_label.setWordWrap(True)
        mileage_group_layout.addWidget(self.maps_hint_label)
        self.route_status_label = QLabel("Google route lookup is waiting for both addresses.")
        self.route_status_label.setWordWrap(True)
        self.set_route_status(
            "Set a Google Maps API key in Settings to enable automatic mileage lookup.",
            "warning",
        )
        mileage_group_layout.addWidget(self.route_status_label)
        mileage_group.setLayout(mileage_group_layout)

        misc_group = QGroupBox("Miscellaneous Entries")
        misc_group_layout = QVBoxLayout()
        misc_group_layout.addWidget(self.misc_table)
        misc_buttons = QHBoxLayout()
        self.add_misc_btn = QPushButton("Add Misc Row")
        self.remove_misc_btn = QPushButton("Remove Misc Row")
        self.attach_receipt_btn = QPushButton("Attach Receipt + Autofill")
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
        self.fill_mileage_btn.clicked.connect(self.fill_mileage_from_maps)
        self.add_misc_btn.clicked.connect(self.add_misc_row)
        self.remove_misc_btn.clicked.connect(self.remove_misc_row)
        self.attach_receipt_btn.clicked.connect(self.attach_receipt_and_autofill)
        self.mileage_model.dataChanged.connect(self.on_mileage_model_changed)
        self.misc_model.dataChanged.connect(self.recalculate_totals)
        self.mileage_rate_input.valueChanged.connect(lambda _v: self.recalculate_totals())
        self.mileage_table.doubleClicked.connect(self.on_mileage_table_double_clicked)
        self.mileage_table.clicked.connect(self.on_mileage_table_clicked)
        self.misc_table.clicked.connect(self.on_misc_table_clicked)
        self.google_routes_service.mileage_ready.connect(self.on_google_mileage_ready)
        self.google_routes_service.request_failed.connect(self.on_google_mileage_failed)
        self._calendar_popup: QDialog | None = None

    def default_mileage_item(self) -> dict[str, Any]:
        return {
            "date": "",
            "project_number": "",
            "start_location": "",
            "end_location": "",
            "maps_url": "",
            "destination": "",
            "reimbursable_expense": "",
            "round_trip": True,
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
        self.renumber_misc_receipts()
        self.misc_model.layoutChanged.emit()

    def remove_misc_row(self) -> None:
        self.misc_model.remove_row(self.misc_table.currentIndex().row())
        self.renumber_misc_receipts()
        self.misc_model.layoutChanged.emit()
        self.recalculate_totals()

    def attach_receipt_and_autofill(self) -> None:
        row_index = self.misc_table.currentIndex().row()
        if row_index < 0:
            self.add_misc_row()
            row_index = len(self.misc_model.rows) - 1
            self.misc_table.selectRow(row_index)
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Receipt",
            "",
            "Receipt Files (*.png *.jpg *.jpeg *.pdf *.tiff *.bmp);;All Files (*)",
        )
        if not file_path:
            return

        try:
            parsed_receipt = self.receipt_service.attach_receipt(Path(file_path))
        except Exception as exc:
            QMessageBox.warning(self, "Attach Receipt", f"Could not process the selected receipt.\n\n{exc}")
            return

        row = self.misc_model.rows[row_index]
        row["receipt_file"] = parsed_receipt.stored_path
        row["receipt_enclosed"] = True
        filled_fields: list[str] = ["receipt enclosed", "receipt file"]

        if parsed_receipt.date:
            row["date"] = parsed_receipt.date
            filled_fields.append("date")
        if parsed_receipt.description:
            row["description"] = parsed_receipt.description
            filled_fields.append("description")
        if parsed_receipt.reimbursable_expense:
            row["reimbursable_expense"] = parsed_receipt.reimbursable_expense
            filled_fields.append("expense category")
        if parsed_receipt.amount:
            row["amount"] = parsed_receipt.amount
            filled_fields.append("amount")

        self.renumber_misc_receipts()
        self.misc_model.layoutChanged.emit()
        self.recalculate_totals()

        if len(filled_fields) > 2:
            QMessageBox.information(
                self,
                "Receipt Attached",
                "Receipt attached and autofilled fields: " + ", ".join(filled_fields) + ".",
            )
        else:
            QMessageBox.information(
                self,
                "Receipt Attached",
                "Receipt attached. I could not confidently extract details from this file, so the row is ready for manual edits.",
            )

    def on_mileage_model_changed(self, top_left: Any, bottom_right: Any, _roles: Any) -> None:
        if top_left.isValid() and bottom_right.isValid():
            row_indexes = range(top_left.row(), bottom_right.row() + 1)
            changed_keys = {
                self.mileage_model.keys[column]
                for column in range(top_left.column(), bottom_right.column() + 1)
            }
        else:
            row_indexes = range(len(self.mileage_model.rows))
            changed_keys = set(GOOGLE_MILEAGE_TRIGGER_KEYS)

        changed = False
        should_refresh_google = bool(changed_keys & GOOGLE_MILEAGE_TRIGGER_KEYS)
        for index in row_indexes:
            if index < 0 or index >= len(self.mileage_model.rows):
                continue
            row = self.mileage_model.rows[index]
            if should_refresh_google:
                changed = self.apply_mileage_defaults(row) or changed
                self.request_google_mileage(index, row)
        if changed:
            self.mileage_model.layoutChanged.emit()
        self.recalculate_totals()

    def apply_mileage_defaults(self, row: dict[str, Any]) -> bool:
        start_location = str(row.get("start_location", "")).strip()
        end_location = str(row.get("end_location", "")).strip()
        round_trip = bool(row.get("round_trip", True))
        if not start_location or not end_location:
            row.pop("_last_route_signature", None)
            row.pop("_pending_route_signature", None)
            row.pop("_route_error", None)
            if row.get("maps_url"):
                row["maps_url"] = ""
                return True
            return False

        changed = False
        maps_url = build_google_maps_directions_url(start_location, end_location, round_trip=round_trip)
        if row.get("maps_url") != maps_url:
            row["maps_url"] = maps_url
            changed = True
        if row.get("destination") != end_location:
            row["destination"] = end_location
            changed = True
        route_description = build_mileage_description(start_location, end_location, round_trip)
        if row.get("reimbursable_expense") != route_description:
            row["reimbursable_expense"] = route_description
            changed = True
        if not str(row.get("date", "")).strip():
            row["date"] = QDate.currentDate().toString("yyyy-MM-dd")
            changed = True
        return changed

    def request_google_mileage(self, row_index: int, row: dict[str, Any], force: bool = False) -> None:
        start_location = str(row.get("start_location", "")).strip()
        end_location = str(row.get("end_location", "")).strip()
        round_trip = bool(row.get("round_trip", True))
        if not start_location and not end_location:
            return
        if not start_location or not end_location:
            self.set_route_status("Enter both a start and end location to calculate mileage.", "warning")
            return
        if not self.google_routes_service.is_configured():
            self.set_route_status(
                "Add a Google Maps API key in Settings to enable automatic mileage lookup.",
                "warning",
            )
            return

        request_signature = {
            "row_index": row_index,
            "start_location": start_location,
            "end_location": end_location,
            "round_trip": round_trip,
        }
        if not force and row.get("_pending_route_signature") == request_signature:
            return
        if (
            not force
            and row.get("_last_route_signature") == request_signature
            and not row.get("_route_error")
            and is_number(str(row.get("number_of_miles", "")).strip())
        ):
            return

        row["_pending_route_signature"] = request_signature
        row.pop("_route_error", None)
        row["number_of_miles"] = "Calculating..."
        row["miles_reimbursement"] = "0.00"
        self.set_route_status("Calculating miles from Google Maps...", "warning")
        request_id = self.google_routes_service.compute_mileage(start_location, end_location, round_trip)
        self._route_requests[request_id] = request_signature

    def on_google_mileage_ready(self, request_id: str, miles: float) -> None:
        request_data = self._route_requests.pop(request_id, None)
        if not request_data:
            return
        row_index = request_data["row_index"]
        if row_index < 0 or row_index >= len(self.mileage_model.rows):
            return

        row = self.mileage_model.rows[row_index]
        current_signature = {
            "row_index": row_index,
            "start_location": str(row.get("start_location", "")).strip(),
            "end_location": str(row.get("end_location", "")).strip(),
            "round_trip": bool(row.get("round_trip", True)),
        }
        if current_signature != request_data:
            return

        row.pop("_pending_route_signature", None)
        row["_last_route_signature"] = request_data
        row["number_of_miles"] = f"{miles:.2f}"
        row["miles_reimbursement"] = f"{calculate_mileage_reimbursement(miles, self.mileage_rate_input.value()):.2f}"
        row.pop("_route_error", None)
        self.set_route_status(
            f"Google Maps updated the route to {miles:.2f} miles.",
            "success",
        )
        self.mileage_model.layoutChanged.emit()
        self.recalculate_totals()

    def on_google_mileage_failed(self, request_id: str, message: str) -> None:
        request_data = self._route_requests.pop(request_id, None)
        if not request_data:
            return
        row_index = request_data["row_index"]
        if row_index < 0 or row_index >= len(self.mileage_model.rows):
            return

        row = self.mileage_model.rows[row_index]
        current_signature = {
            "row_index": row_index,
            "start_location": str(row.get("start_location", "")).strip(),
            "end_location": str(row.get("end_location", "")).strip(),
            "round_trip": bool(row.get("round_trip", True)),
        }
        if current_signature != request_data:
            return

        row.pop("_pending_route_signature", None)
        row.pop("_last_route_signature", None)
        row["number_of_miles"] = ""
        row["miles_reimbursement"] = "0.00"
        row["_route_error"] = message
        self.set_route_status(self.describe_route_error(message), "error")
        self.mileage_model.layoutChanged.emit()
        self.recalculate_totals()

    def on_mileage_table_clicked(self, index: Any) -> None:
        self.handle_date_click(self.mileage_table, self.mileage_model, index)

    def on_misc_table_clicked(self, index: Any) -> None:
        self.handle_date_click(self.misc_table, self.misc_model, index)

    def handle_date_click(self, table: QTableView, model: EditableTableModel, index: Any) -> None:
        if not index.isValid():
            return
        key = model.keys[index.column()]
        if key != "date":
            return
        self.open_calendar_popup(table, model, index.row(), key)

    def open_calendar_popup(
        self,
        table: QTableView,
        model: EditableTableModel,
        row_index: int,
        key: str,
    ) -> None:
        popup = QDialog(self, Qt.Popup | Qt.FramelessWindowHint)
        popup.setObjectName("calendarPopup")
        popup_layout = QVBoxLayout()
        popup_layout.setContentsMargins(8, 8, 8, 8)
        calendar = QCalendarWidget(popup)
        current_text = str(model.rows[row_index].get(key, "")).strip()
        current_date = QDate.fromString(current_text, "yyyy-MM-dd")
        if not current_date.isValid():
            current_date = QDate.currentDate()
        calendar.setSelectedDate(current_date)
        popup_layout.addWidget(calendar)
        popup.setLayout(popup_layout)

        def apply_date(selected_date: QDate) -> None:
            model.rows[row_index][key] = selected_date.toString("yyyy-MM-dd")
            model.layoutChanged.emit()
            self.recalculate_totals()
            popup.close()

        calendar.clicked.connect(apply_date)
        cell_rect = table.visualRect(table.model().index(row_index, model.keys.index(key)))
        popup.move(table.viewport().mapToGlobal(cell_rect.bottomLeft()))
        self._calendar_popup = popup
        popup.show()

    def set_route_status(self, text: str, status: str) -> None:
        self.route_status_label.setText(text)

    def on_mileage_table_double_clicked(self, index: Any) -> None:
        if not index.isValid():
            return
        key = self.mileage_model.keys[index.column()]
        if key != "maps_url":
            return
        row = self.mileage_model.rows[index.row()]
        maps_url = str(row.get("maps_url", "")).strip()
        if maps_url:
            QDesktopServices.openUrl(QUrl(maps_url))

    def fill_mileage_from_maps(self) -> None:
        row_index = self.mileage_table.currentIndex().row()
        if row_index < 0:
            QMessageBox.information(
                self,
                "Fill Mileage",
                "Select a mileage row first, then enter the start and end locations.",
            )
            return

        row = self.mileage_model.rows[row_index]
        start_location = str(row.get("start_location", "")).strip()
        end_location = str(row.get("end_location", "")).strip()
        if not start_location or not end_location:
            QMessageBox.information(
                self,
                "Fill Mileage",
                "Enter both a start location and an end location in the selected mileage row.",
            )
            return

        self.apply_mileage_defaults(row)
        maps_url = str(row.get("maps_url", "")).strip()
        if maps_url:
            QDesktopServices.openUrl(QUrl(maps_url))

        round_trip = bool(row.get("round_trip", True))
        row["destination"] = end_location
        row["reimbursable_expense"] = build_mileage_description(start_location, end_location, round_trip)
        if not str(row.get("date", "")).strip():
            row["date"] = QDate.currentDate().toString("yyyy-MM-dd")
        self.request_google_mileage(row_index, row, force=True)
        self.mileage_model.layoutChanged.emit()
        self.recalculate_totals()
        QMessageBox.information(
            self,
            "Fill Mileage",
            "Opened Google Maps so you can verify the route. The app will try to fill miles automatically from Google, and you can still type the miles manually if Google does not return a route.",
        )

    def apply_settings_defaults(self, settings: dict[str, str]) -> None:
        self.update_integration_settings(settings)
        if settings.get("default_employee_name"):
            self.employee_name_input.setText(settings["default_employee_name"])
        rate = settings.get("default_mileage_rate", "0.67")
        if is_number(rate):
            self.mileage_rate_input.setValue(float(rate))

    def update_integration_settings(self, settings: dict[str, str]) -> None:
        api_key = settings.get("google_maps_api_key", "")
        self.google_places_service.set_api_key(api_key)
        self.google_routes_service.set_api_key(api_key)
        if self.google_routes_service.is_configured():
            self.maps_hint_label.setText(
                "Type in Start Location and End Location for Google suggestions. "
                "Miles are filled automatically from Google Maps routing. "
                "Double-click Google Maps Route to verify directions."
            )
            self.set_route_status(
                "Google Maps integration is ready. Address suggestions and automatic mileage are enabled.",
                "success",
            )
        else:
            self.maps_hint_label.setText(
                "Set a Google Maps API key in Settings to enable address suggestions and automatic mileage calculation."
            )
            self.set_route_status(
                "Add a Google Maps API key in Settings to enable automatic mileage lookup.",
                "warning",
            )
        for row in self.mileage_model.rows:
            row.pop("_last_route_signature", None)
            row.pop("_pending_route_signature", None)
            row.pop("_route_error", None)
        for index, row in enumerate(self.mileage_model.rows):
            self.request_google_mileage(index, row)
        self.mileage_model.layoutChanged.emit()
        self.recalculate_totals()

    def renumber_misc_receipts(self) -> None:
        for index, row in enumerate(self.misc_model.rows, start=1):
            row["receipt_number"] = str(index)

    def reset_form(self, settings: dict[str, str]) -> None:
        self.current_report_id = None
        self.employee_name_input.clear()
        self.date_from_input.setDate(QDate.currentDate())
        self.date_to_input.setDate(QDate.currentDate())
        self.mileage_model.replace_rows([])
        self.misc_model.replace_rows([])
        self.renumber_misc_receipts()
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

        self.renumber_misc_receipts()
        self.misc_model.layoutChanged.emit()
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
        self.renumber_misc_receipts()
        for row in self.mileage_model.rows:
            row.pop("_last_route_signature", None)
            row.pop("_pending_route_signature", None)
            row.pop("_route_error", None)
        for index, row in enumerate(self.mileage_model.rows):
            self.request_google_mileage(index, row)
        self.recalculate_totals()

    def describe_route_error(self, message: str) -> str:
        cleaned_message = " ".join(message.split())
        if "SERVICE_DISABLED" in cleaned_message or "Routes API has not been used" in cleaned_message:
            return (
                "Google Routes API is disabled for the current Google project. "
                f"{cleaned_message} You can still type miles manually in Number of Miles."
            )
        if "API key not valid" in cleaned_message or "REQUEST_DENIED" in cleaned_message:
            return (
                "Google rejected the API key for mileage lookup. "
                "Confirm the saved key is valid and has Places API and Routes API access. "
                "You can still type miles manually in Number of Miles."
            )
        if cleaned_message:
            return f"Google mileage lookup failed: {cleaned_message} You can still type miles manually in Number of Miles."
        return "Google mileage lookup failed. Check your Google Maps API key and Routes API access. You can still type miles manually in Number of Miles."
