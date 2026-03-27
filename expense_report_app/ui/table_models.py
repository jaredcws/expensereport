from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt


class EditableTableModel(QAbstractTableModel):
    def __init__(self, headers: list[str], rows: list[dict[str, Any]], keys: list[str], read_only: set[str] | None = None):
        super().__init__()
        self.headers = headers
        self.rows = rows
        self.keys = keys
        self.read_only = read_only or set()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self.rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self.headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        key = self.keys[index.column()]
        value = self.rows[index.row()].get(key, "")
        if key == "receipt_enclosed" and role == Qt.CheckStateRole:
            return Qt.Checked if bool(value) else Qt.Unchecked
        if role in (Qt.DisplayRole, Qt.EditRole):
            if isinstance(value, bool):
                return "Yes" if value else "No"
            return "" if value is None else str(value)
        return None

    def setData(self, index: QModelIndex, value: Any, role: int = Qt.EditRole) -> bool:  # noqa: N802
        if not index.isValid():
            return False
        key = self.keys[index.column()]
        if key in self.read_only:
            return False
        if key == "receipt_enclosed" and role == Qt.CheckStateRole:
            self.rows[index.row()][key] = value == Qt.Checked
            self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
            return True
        if role != Qt.EditRole:
            return False
        if isinstance(value, str):
            value = value.strip()
        if key == "receipt_enclosed":
            value = str(value).lower() in {"yes", "true", "1", "y"}
        self.rows[index.row()][key] = value
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.ItemIsEnabled
        key = self.keys[index.column()]
        base_flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if key == "receipt_enclosed":
            return base_flags | Qt.ItemIsUserCheckable | Qt.ItemIsEditable
        if key in self.read_only:
            return base_flags
        return base_flags | Qt.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.headers[section]
        return super().headerData(section, orientation, role)

    def insert_empty_row(self, template: dict[str, Any]) -> None:
        self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows))
        self.rows.append(template.copy())
        self.endInsertRows()

    def remove_row(self, row: int) -> None:
        if row < 0 or row >= len(self.rows):
            return
        self.beginRemoveRows(QModelIndex(), row, row)
        self.rows.pop(row)
        self.endRemoveRows()

    def replace_rows(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()
