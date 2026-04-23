from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROUTE_BASE_URL = "https://apis.data.go.kr/6410000/busrouteservice/v2"
ARRIVAL_BASE_URL = "https://apis.data.go.kr/6410000/busarrivalservice/v2"


class GbisApiError(RuntimeError):
    pass


class GbisClient:
    def __init__(self, service_key: str | None = None, timeout: int = 20, max_station_scans: int = 12, scan_chunk_size: int = 3):
        self.service_key = service_key or load_service_key()
        self.timeout = timeout
        self.max_station_scans = max_station_scans
        self.scan_chunk_size = scan_chunk_size
        self._route_scan_offsets: dict[str, int] = {}
        self._route_last_snapshot: dict[str, dict[str, Any]] = {}

    def _ensure_live_snapshot_state(self) -> None:
        if not hasattr(self, "scan_chunk_size"):
            self.scan_chunk_size = 3
        if not hasattr(self, "_route_scan_offsets"):
            self._route_scan_offsets = {}
        if not hasattr(self, "_route_last_snapshot"):
            self._route_last_snapshot = {}

    def search_routes(self, query: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"{ROUTE_BASE_URL}/getBusRouteListv2",
            {"serviceKey": self.service_key, "keyword": query, "format": "json"},
        )
        return normalize_route_list(payload)

    def get_route_stations(self, route_id: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"{ROUTE_BASE_URL}/getBusRouteStationListv2",
            {"serviceKey": self.service_key, "routeId": route_id, "format": "json"},
        )
        return normalize_station_list(payload)

    def get_recommended_stations(self, route_id: str, limit: int = 3) -> list[dict[str, Any]]:
        return self.get_route_live_snapshot(route_id, recommendation_limit=limit)["recommendations"]

    def get_route_live_buses(self, route_id: str) -> list[dict[str, Any]]:
        return self.get_route_live_snapshot(route_id)["buses"]

    def get_route_live_snapshot(self, route_id: str, recommendation_limit: int = 3) -> dict[str, Any]:
        self._ensure_live_snapshot_state()
        recommendations: list[dict[str, Any]] = []
        live_buses: dict[str, dict[str, Any]] = {}
        stations = self.get_route_stations(route_id)
        station_limit = min(len(stations), getattr(self, "max_station_scans", 12))
        if station_limit <= 0:
            snapshot = {"route_id": route_id, "buses": [], "recommendations": []}
            self._route_last_snapshot[route_id] = snapshot
            return snapshot

        scan_size = max(1, min(getattr(self, "scan_chunk_size", 3), station_limit))
        start_index = self._route_scan_offsets.get(route_id, 0) % station_limit
        indices = [((start_index + offset) % station_limit) for offset in range(scan_size)]
        self._route_scan_offsets[route_id] = (start_index + scan_size) % station_limit

        for index in indices:
            station = stations[index]
            try:
                arrival = self.get_arrival(route_id, station["station_id"], station["station_seq"])
            except Exception:
                continue
            if not arrival:
                continue
            if has_live_position(arrival) and len(recommendations) < recommendation_limit:
                recommendations.append({**station, "arrival": arrival})
            for bus in arrival.get("buses", []):
                bus_key = str(bus.get("vehicle_id") or bus.get("plate_no") or f"{station['station_id']}:{bus.get('current_station_name', '')}")
                if bus_key in live_buses:
                    continue
                live_buses[bus_key] = {
                    **bus,
                    "station_id": station["station_id"],
                    "station_seq": station["station_seq"],
                    "station_name": station["station_name"],
                }
        snapshot = {
            "route_id": route_id,
            "buses": sorted(
                live_buses.values(),
                key=lambda bus: (
                    int(bus.get("station_seq") or 0),
                    int(bus.get("location_no") or 10**6),
                    str(bus.get("plate_no") or ""),
                ),
            ),
            "recommendations": recommendations,
        }
        if snapshot["buses"] or snapshot["recommendations"]:
            self._route_last_snapshot[route_id] = snapshot
            return snapshot
        return self._route_last_snapshot.get(route_id, snapshot)

    def get_arrival(self, route_id: str, station_id: str, sta_order: int) -> dict[str, Any] | None:
        payload = self._get_json(
            f"{ARRIVAL_BASE_URL}/getBusArrivalItemv2",
            {
                "serviceKey": self.service_key,
                "routeId": route_id,
                "stationId": station_id,
                "staOrder": str(sta_order),
                "format": "json",
            },
        )
        return normalize_arrival_item(payload)

    def _get_json(self, base_url: str, params: dict[str, str]) -> dict[str, Any]:
        request = Request(f"{base_url}?{urlencode(params)}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


def load_service_key() -> str:
    for env_name in ("GBIS_SERVICE_KEY", "PUBLIC_DATA_SERVICE_KEY"):
        env_key = os.getenv(env_name)
        if env_key:
            return env_key

    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GBIS_SERVICE_KEY=") or line.startswith("PUBLIC_DATA_SERVICE_KEY="):
                return line.split("=", 1)[1].strip()

    raise GbisApiError("GBIS_SERVICE_KEY 또는 PUBLIC_DATA_SERVICE_KEY를 찾지 못했습니다.")


def _header(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("response", {}).get("msgHeader", {})


def normalize_route_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("response", {}).get("msgBody", {}).get("busRouteList", [])
    return [
        {
            "route_id": str(item.get("routeId", "")),
            "route_name": str(item.get("routeName", "")),
            "start_station": item.get("startStationName", ""),
            "end_station": item.get("endStationName", ""),
            "admin_name": item.get("adminName", ""),
            "region_name": item.get("regionName", ""),
        }
        for item in items
    ]


def normalize_station_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("response", {}).get("msgBody", {}).get("busRouteStationList", [])
    return [
        {
            "station_id": str(item.get("stationId", "")),
            "station_name": item.get("stationName", ""),
            "station_seq": int(item.get("stationSeq", 0)),
            "x": item.get("x"),
            "y": item.get("y"),
            "turn_seq": int(item.get("turnSeq", 0) or 0),
            "turn_yn": str(item.get("turnYn", "N") or "N"),
        }
        for item in items
    ]


def has_live_position(arrival: dict[str, Any]) -> bool:
    return bool(arrival.get("buses") or arrival.get("location_no") is not None or arrival.get("current_station_name") or arrival.get("plate_no"))


def _normalize_bus_candidate(item: dict[str, Any], index: int) -> dict[str, Any] | None:
    plate_no = item.get(f"plateNo{index}") or ""
    current_station_name = item.get(f"stationNm{index}") or ""
    predict_time_min = item.get(f"predictTime{index}") or None
    location_no = item.get(f"locationNo{index}") or None
    remain_seat_count = item.get(f"remainSeatCnt{index}") or None
    vehicle_id = item.get(f"vehId{index}") or ""
    if not any([plate_no, current_station_name, predict_time_min, location_no, vehicle_id]):
        return None
    return {
        "vehicle_id": str(vehicle_id),
        "plate_no": str(plate_no),
        "predict_time_min": int(predict_time_min) if predict_time_min not in (None, "") else None,
        "location_no": int(location_no) if location_no not in (None, "") else None,
        "current_station_name": str(current_station_name),
        "remain_seat_count": int(remain_seat_count) if remain_seat_count not in (None, "") else None,
    }


def normalize_arrival_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    header = _header(payload)
    if int(header.get("resultCode", -1)) == 4:
        return None

    item = payload.get("response", {}).get("msgBody", {}).get("busArrivalItem", {})
    buses = [bus for bus in (_normalize_bus_candidate(item, 1), _normalize_bus_candidate(item, 2)) if bus]
    primary_bus = buses[0] if buses else {}
    return {
        "route_id": str(item.get("routeId", "")),
        "route_name": str(item.get("routeName", "")),
        "station_id": str(item.get("stationId", "")),
        "sta_order": int(item.get("staOrder", 0)),
        "flag": item.get("flag", ""),
        "predict_time_min": primary_bus.get("predict_time_min"),
        "location_no": primary_bus.get("location_no"),
        "plate_no": primary_bus.get("plate_no", ""),
        "current_station_name": primary_bus.get("current_station_name", ""),
        "remain_seat_count": primary_bus.get("remain_seat_count"),
        "result_message": header.get("resultMessage", ""),
        "buses": buses,
    }
