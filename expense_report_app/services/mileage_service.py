from __future__ import annotations

from urllib.parse import urlencode


def build_google_maps_directions_url(origin: str, destination: str, round_trip: bool = False) -> str:
    params = {
        "api": "1",
        "origin": origin,
        "destination": destination,
        "travelmode": "driving",
    }
    if round_trip:
        params["destination"] = origin
        params["waypoints"] = destination
    query = urlencode(params)
    return f"https://www.google.com/maps/dir/?{query}"


def build_mileage_description(origin: str, destination: str, round_trip: bool) -> str:
    route = f"{origin} to {destination}"
    if round_trip:
        return f"Business mileage - {route} (round trip)"
    return f"Business mileage - {route}"
