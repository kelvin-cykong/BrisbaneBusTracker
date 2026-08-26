"""
Translink Leaflet live bus tracker.

Run:
    python3 files/translink_leaflet_app.py

Then open:
    http://127.0.0.1:8060
"""

from __future__ import annotations

import json
import mimetypes
import ssl
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from google.transit import gtfs_realtime_pb2

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
WEB_ROOT = ROOT / "files" / "html"
OPEN_DATA_URL = "https://translink.com.au/about-translink/open-data"
GTFS_RT_BUS_URL = (
    "https://gtfsrt.api.translink.com.au/api/realtime/SEQ/VehiclePositions/Bus"
)
HOST = "127.0.0.1"
PORT = 8060


def fetch_live_buses() -> dict:
    request = Request(
        GTFS_RT_BUS_URL,
        headers={
            "User-Agent": "QLD-Transport-OpenData-Leaflet-Demo/1.0",
            "Accept": "application/x-protobuf,application/octet-stream,*/*",
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read()
    except URLError as exc:
        if not isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise

        fallback_context = ssl._create_unverified_context()
        with urlopen(request, timeout=15, context=fallback_context) as response:
            payload = response.read()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)

    vehicles = []
    routes = set()
    directions = set()

    for entity in feed.entity:
        if not entity.HasField("vehicle"):
            continue

        vehicle = entity.vehicle
        position = vehicle.position
        trip = vehicle.trip

        if not position.latitude or not position.longitude:
            continue

        route_id = trip.route_id
        direction_id = str(trip.direction_id) if trip.HasField("direction_id") else ""
        timestamp = (
            datetime.fromtimestamp(vehicle.timestamp, timezone.utc).isoformat()
            if vehicle.timestamp
            else ""
        )
        route = str(route_id).split("-")[0]
        if route:
            routes.add(route)
        if direction_id:
            directions.add(direction_id)

        stop_id = vehicle.stop_id if vehicle.HasField("stop_id") else None
        stop_name = stops_df[stops_df.stop_id == stop_id].stop_name.iloc[0] if stop_id else None

        trip_headsign = tripID_df[tripID_df.trip_id == trip.trip_id].trip_headsign.iloc[0] if trip.trip_id else None

        vehicles.append(
            {
                "id": vehicle.vehicle.id or entity.id,
                "label": vehicle.vehicle.label or vehicle.vehicle.id or entity.id,
                "routeId": route_id,
                "route": route,
                "tripId": trip.trip_id,
                "directionId": direction_id,
                "latitude": position.latitude,
                "longitude": position.longitude,
                "current_stop_sequence": vehicle.current_stop_sequence if vehicle.current_stop_sequence else None,
                "current_status": vehicle.current_status, #STOPPED AT = 1, IN_TRANSIT_TO = 2
                "stop_id": stop_id,
                "stop_name": stop_name,
                "trip_headsign": trip_headsign,
                "timestamp": timestamp,
            }
        )

    return {
        "source": OPEN_DATA_URL,
        "feed": GTFS_RT_BUS_URL,
        "fetchedAt": datetime.now(timezone.utc).isoformat(),
        "vehicleCount": len(vehicles),
        "routes": sorted(routes, key=route_sort_key),
        "directions": sorted(directions),
        "vehicles": vehicles,
    }


def route_sort_key(route: str) -> tuple[int, int | str]:
    return (0, int(route)) if route.isdigit() else (1, route)


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path in ("", "/"):
            path = "/index.html"

        requested = (WEB_ROOT / path.lstrip("/")).resolve()
        if not requested.is_relative_to(WEB_ROOT) or not requested.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self) -> None:
        path = urlparse(self.path).path

        if path == "/api/vehicles":
            self.handle_vehicles()
            return

        if path in ("", "/"):
            path = "/index.html"

        self.serve_static(path)

    def handle_vehicles(self) -> None:
        try:
            payload = fetch_live_buses()
            self.send_json(200, payload)
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            self.send_json(
                502,
                {
                    "error": "Unable to fetch or parse Translink GTFS-RT bus data.",
                    "detail": str(exc),
                    "source": OPEN_DATA_URL,
                    "feed": GTFS_RT_BUS_URL,
                },
            )

    def serve_static(self, path: str) -> None:
        requested = (WEB_ROOT / path.lstrip("/")).resolve()
        if not requested.is_relative_to(WEB_ROOT) or not requested.is_file():
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(requested.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(requested.read_bytes())

    def send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    stops_df = pd.read_csv(ROOT / "files" / "data" / "SEQ_GTFS" / "stops.txt")
    tripID_df = pd.read_csv(ROOT / "files" / "data" / "SEQ_GTFS" / "trips.txt")
    print(f"Loaded datasets from Translink Static Data")
    print(f"Translink Leaflet tracker running at http://{HOST}:{PORT}")
    print(f"Open data page: {OPEN_DATA_URL}")
    print(f"Bus feed: {GTFS_RT_BUS_URL}")
    server.serve_forever()
