from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, QStringListModel
from PySide6.QtWidgets import QCompleter, QLineEdit, QStyledItemDelegate

from expense_report_app.services.google_places_service import GooglePlacesService


class AddressAutocompleteLineEdit(QLineEdit):
    def __init__(self, places_service: GooglePlacesService, parent=None) -> None:
        super().__init__(parent)
        self._places_service = places_service
        self._pending_query = ""
        self._completer_model = QStringListModel(self)
        self._completer = QCompleter(self._completer_model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(self._completer)

        self._debounce = QTimer(self)
        self._debounce.setInterval(250)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._request_suggestions)

        self._places_service.suggestions_ready.connect(self._apply_suggestions)
        self.textEdited.connect(self._on_text_edited)
        self._completer.activated.connect(self._apply_completion)
        self._refresh_hint()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._places_service.reset_session_token()
        self._refresh_hint()

    def _on_text_edited(self, text: str) -> None:
        self._pending_query = text.strip()
        self._refresh_hint()
        if len(self._pending_query) < 3 or not self._places_service.is_configured():
            self._debounce.stop()
            self._completer_model.setStringList([])
            return
        self._debounce.start()

    def _request_suggestions(self) -> None:
        self._places_service.autocomplete(self._pending_query)

    def _apply_suggestions(self, query: str, suggestions: list[str]) -> None:
        if query != self._pending_query:
            return
        self._completer_model.setStringList(suggestions)
        if suggestions:
            self.completer().complete()

    def _apply_completion(self, text: str) -> None:
        self.setText(text)
        self.editingFinished.emit()

    def _refresh_hint(self) -> None:
        if self._places_service.is_configured():
            self.setToolTip("Start typing to get Google Maps address suggestions.")
            return
        self.setToolTip("Set a Google Maps API key in Settings to enable address autocomplete.")


class AddressAutocompleteDelegate(QStyledItemDelegate):
    def __init__(self, places_service: GooglePlacesService, parent=None) -> None:
        super().__init__(parent)
        self._places_service = places_service

    def createEditor(self, parent, option, index):  # noqa: N802
        editor = AddressAutocompleteLineEdit(self._places_service, parent)
        editor.editingFinished.connect(self._commit_and_close_editor)
        return editor

    def setEditorData(self, editor, index):  # noqa: N802
        editor.setText(index.data(Qt.EditRole) or "")

    def setModelData(self, editor, model, index):  # noqa: N802
        model.setData(index, editor.text(), Qt.EditRole)

    def updateEditorGeometry(self, editor, option, index):  # noqa: N802
        editor.setGeometry(option.rect)

    def _commit_and_close_editor(self) -> None:
        editor = self.sender()
        if editor is None:
            return
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
