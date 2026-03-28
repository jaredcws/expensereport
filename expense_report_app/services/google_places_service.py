from __future__ import annotations

import json
from uuid import uuid4

from PySide6.QtCore import QByteArray, QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class GooglePlacesService(QObject):
    suggestions_ready = Signal(str, list)
    request_failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api_key = ""
        self._manager = QNetworkAccessManager(self)
        self._pending_queries: dict[QNetworkReply, str] = {}
        self._session_token = uuid4().hex

    def set_api_key(self, api_key: str) -> None:
        cleaned = api_key.strip()
        if cleaned == self._api_key:
            return
        self._api_key = cleaned
        self.reset_session_token()

    def reset_session_token(self) -> None:
        self._session_token = uuid4().hex

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def autocomplete(self, query: str) -> None:
        normalized_query = query.strip()
        if len(normalized_query) < 3 or not self.is_configured():
            self.suggestions_ready.emit(normalized_query, [])
            return

        request = QNetworkRequest(QUrl("https://places.googleapis.com/v1/places:autocomplete"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"X-Goog-Api-Key", self._api_key.encode("utf-8"))
        request.setRawHeader(b"X-Goog-FieldMask", b"suggestions.placePrediction.text.text")

        payload = {
            "input": normalized_query,
            "includeQueryPredictions": False,
            "languageCode": "en",
            "sessionToken": self._session_token,
        }
        reply = self._manager.post(
            request,
            QByteArray(json.dumps(payload).encode("utf-8")),
        )
        self._pending_queries[reply] = normalized_query
        reply.finished.connect(lambda reply=reply: self._handle_reply(reply))

    def _handle_reply(self, reply: QNetworkReply) -> None:
        query = self._pending_queries.pop(reply, "")
        try:
            if reply.error() != QNetworkReply.NoError:
                message = bytes(reply.readAll()).decode("utf-8", errors="ignore") or reply.errorString()
                self.request_failed.emit(query, message)
                self.suggestions_ready.emit(query, [])
                return

            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            suggestions: list[str] = []
            seen: set[str] = set()
            for item in payload.get("suggestions", []):
                text = (
                    item.get("placePrediction", {})
                    .get("text", {})
                    .get("text", "")
                    .strip()
                )
                if not text or text in seen:
                    continue
                seen.add(text)
                suggestions.append(text)
            self.suggestions_ready.emit(query, suggestions)
        finally:
            reply.deleteLater()
