from __future__ import annotations

import json
from uuid import uuid4

from PySide6.QtCore import QByteArray, QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest


class GoogleRoutesService(QObject):
    mileage_ready = Signal(str, float)
    request_failed = Signal(str, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._api_key = ""
        self._manager = QNetworkAccessManager(self)
        self._pending_requests: dict[QNetworkReply, str] = {}

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key.strip()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def compute_mileage(self, origin: str, destination: str, round_trip: bool) -> str:
        request_id = uuid4().hex
        cleaned_origin = origin.strip()
        cleaned_destination = destination.strip()

        if not cleaned_origin or not cleaned_destination or not self.is_configured():
            self.request_failed.emit(request_id, "Google Maps API key is not configured for route calculation.")
            return request_id

        request = QNetworkRequest(QUrl("https://routes.googleapis.com/directions/v2:computeRoutes"))
        request.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
        request.setRawHeader(b"X-Goog-Api-Key", self._api_key.encode("utf-8"))
        request.setRawHeader(b"X-Goog-FieldMask", b"routes.distanceMeters")

        body = {
            "origin": {"address": cleaned_origin},
            "destination": {"address": cleaned_origin if round_trip else cleaned_destination},
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "computeAlternativeRoutes": False,
            "languageCode": "en-US",
            "regionCode": "US",
            "units": "IMPERIAL",
        }
        if round_trip:
            body["intermediates"] = [{"address": cleaned_destination}]

        reply = self._manager.post(
            request,
            QByteArray(json.dumps(body).encode("utf-8")),
        )
        self._pending_requests[reply] = request_id
        reply.finished.connect(lambda reply=reply: self._handle_reply(reply))
        return request_id

    def _handle_reply(self, reply: QNetworkReply) -> None:
        request_id = self._pending_requests.pop(reply, "")
        try:
            if reply.error() != QNetworkReply.NoError:
                message = self._parse_error_message(reply)
                self.request_failed.emit(request_id, message)
                return

            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            routes = payload.get("routes", [])
            if not routes:
                self.request_failed.emit(request_id, "No route returned by Google Maps.")
                return

            distance_meters = float(routes[0].get("distanceMeters", 0))
            miles = distance_meters / 1609.344
            self.mileage_ready.emit(request_id, miles)
        finally:
            reply.deleteLater()

    def _parse_error_message(self, reply: QNetworkReply) -> str:
        raw_message = bytes(reply.readAll()).decode("utf-8", errors="ignore").strip()
        if not raw_message:
            return reply.errorString()

        try:
            payload = json.loads(raw_message)
        except json.JSONDecodeError:
            return raw_message

        error = payload.get("error", {})
        message = str(error.get("message", "")).strip()
        details = error.get("details", [])
        activation_url = ""
        service_title = "Google Maps"

        for detail in details:
            metadata = detail.get("metadata", {})
            if metadata.get("activationUrl"):
                activation_url = metadata["activationUrl"]
            if metadata.get("serviceTitle"):
                service_title = metadata["serviceTitle"]

        if activation_url and activation_url not in message:
            if message:
                return f"{message} Enable {service_title} here: {activation_url}"
            return f"Enable {service_title} here: {activation_url}"

        return message or raw_message
