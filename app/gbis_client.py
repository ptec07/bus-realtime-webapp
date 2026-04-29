from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROUTE_BASE_URL = "https://apis.data.go.kr/6410000/busrouteservice/v2"
ARRIVAL_BASE_URL = "https://apis.data.go.kr/6410000/busarrivalservice/v2"
LOCATION_BASE_URL = "https://apis.data.go.kr/6410000/buslocationservice/v2"


class GbisApiError(RuntimeError):
    pass


class GbisClient:
    def __init__(self, service_key: str | None = None, timeout: int = 20, max_station_scans: int = 12, scan_chunk_size: int = 3, average_speed_kmh: float = 30.0):
        self.service_key = service_key or load_service_key()
        self.timeout = timeout
        self.max_station_scans = max_station_scans
        self.scan_chunk_size = scan_chunk_size
        self.average_speed_kmh = average_speed_kmh
        self._route_scan_offsets: dict[str, int] = {}
        self._route_last_snapshot: dict[str, dict[str, Any]] = {}

    def _ensure_live_snapshot_state(self) -> None:
        if not hasattr(self, "scan_chunk_size"):
            self.scan_chunk_size = 3
        if not hasattr(self, "average_speed_kmh"):
            self.average_speed_kmh = 30.0
        if not hasattr(self, "_route_scan_offsets"):
            self._route_scan_offsets = {}
        if not hasattr(self, "_route_last_snapshot"):
            self._route_last_snapshot = {}
        if not hasattr(self, "arrival_cache_ttl"):
            self.arrival_cache_ttl = 30
        if not hasattr(self, "_arrival_cache"):
            self._arrival_cache = {}

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

    def get_bus_location_list(self, route_id: str) -> list[dict[str, Any]]:
        payload = self._get_json(
            f"{LOCATION_BASE_URL}/getBusLocationListv2",
            {"serviceKey": self.service_key, "routeId": route_id, "format": "json"},
        )
        return normalize_bus_location_list(payload)

    def get_route_live_snapshot(self, route_id: str, recommendation_limit: int = 3) -> dict[str, Any]:
        self._ensure_live_snapshot_state()
        stations = self.get_route_stations(route_id)
        station_lookup = {str(station["station_id"]): station for station in stations}

        try:
            direct_locations = self.get_bus_location_list(route_id)
        except Exception:
            direct_locations = []

        if direct_locations:
            stations_by_seq = {int(station["station_seq"]): station for station in stations}
            live_buses = [
                enrich_direct_bus_location(location, station_lookup) for location in direct_locations
            ]
            for bus in live_buses[: max(recommendation_limit, 3)]:
                try:
                    arrival = self.get_arrival(route_id, bus["station_id"], bus["station_seq"])
                except Exception:
                    arrival = None
                enrich_bus_with_arrival(bus, arrival)
                if bus.get("predict_time_min") is None:
                    fallback_eta = estimate_direct_bus_eta_minutes(
                        stations,
                        current_station_seq=int(bus.get("station_seq") or 0),
                        target_station_seq=min(len(stations), int(bus.get("station_seq") or 0) + 1),
                        average_speed_kmh=getattr(self, "average_speed_kmh", 30.0),
                    )
                    if fallback_eta is not None:
                        bus["predict_time_min"] = fallback_eta
                        bus["location_no"] = 1
                        bus["eta_source"] = "estimated"
            recommendations = [
                build_direct_location_recommendation(
                    bus,
                    station_lookup,
                    stations_by_seq,
                    average_speed_kmh=getattr(self, "average_speed_kmh", 30.0),
                )
                for bus in live_buses[:recommendation_limit]
            ]
            snapshot = {
                "route_id": route_id,
                "buses": live_buses,
                "recommendations": [item for item in recommendations if item],
                "timeline_eta_by_seq": build_timeline_eta_by_seq(
                    stations,
                    live_buses,
                    average_speed_kmh=getattr(self, "average_speed_kmh", 30.0),
                ),
            }
            self._route_last_snapshot[route_id] = snapshot
            return snapshot

        recommendations: list[dict[str, Any]] = []
        live_buses: dict[str, dict[str, Any]] = {}
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
        snapshot["timeline_eta_by_seq"] = build_timeline_eta_by_seq(
            stations,
            snapshot["buses"],
            average_speed_kmh=getattr(self, "average_speed_kmh", 30.0),
        )
        if snapshot["buses"] or snapshot["recommendations"]:
            self._route_last_snapshot[route_id] = snapshot
            return snapshot
        return self._route_last_snapshot.get(route_id, snapshot)

    def get_arrival(self, route_id: str, station_id: str, sta_order: int) -> dict[str, Any] | None:
        self._ensure_live_snapshot_state()
        cache_key = (str(route_id), str(station_id), int(sta_order))
        now = time.time()
        cached = self._arrival_cache.get(cache_key)
        ttl = getattr(self, "arrival_cache_ttl", 30)
        if cached and now - cached["timestamp"] <= ttl:
            return cached["data"]
        try:
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
            arrival = normalize_arrival_item(payload)
        except Exception:
            return cached["data"] if cached else None
        self._arrival_cache[cache_key] = {"timestamp": now, "data": arrival}
        return arrival

    def get_live_or_estimated_arrival(self, route_id: str, station_id: str, sta_order: int) -> dict[str, Any] | None:
        arrival = self.get_arrival(route_id, station_id, sta_order)
        if arrival:
            return arrival

        stations = self.get_route_stations(route_id)
        direct_locations = self.get_bus_location_list(route_id)
        estimate = estimate_arrival_from_direct_locations(
            route_id=route_id,
            station_id=station_id,
            sta_order=sta_order,
            stations=stations,
            direct_locations=direct_locations,
            average_speed_kmh=getattr(self, "average_speed_kmh", 30.0),
        )
        return estimate

    def _get_json(self, base_url: str, params: dict[str, str]) -> dict[str, Any]:
        request = Request(f"{base_url}?{urlencode(params)}", headers={"Accept": "application/json"})
        with urlopen(request, timeout=self.timeout) as response:
            return json.load(response)


def load_service_key() -> str:
    for env_name in ("GBIS_SERVICE_KEY", "PUBLIC_DATA_SERVICE_KEY"):
        env_key = os.getenv(env_name)
        if env_key:
            return sanitize_service_key(env_key)

    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("GBIS_SERVICE_KEY=") or line.startswith("PUBLIC_DATA_SERVICE_KEY="):
                return sanitize_service_key(line.split("=", 1)[1])

    raise GbisApiError("GBIS_SERVICE_KEY 또는 PUBLIC_DATA_SERVICE_KEY를 찾지 못했습니다.")


def _header(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("response", {}).get("msgHeader", {})


def sanitize_service_key(raw: str) -> str:
    key = str(raw).strip().strip('"').strip("'")
    if key.endswith('.') and key[:-1].isalnum():
        key = key[:-1]
    return key


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


def normalize_bus_location_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("response", {}).get("msgBody", {}).get("busLocationList", [])
    if isinstance(items, dict):
        items = [items]
    return [item for item in items if item]


def enrich_direct_bus_location(location: dict[str, Any], station_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    station_id = str(location.get("stationId", ""))
    station = station_lookup.get(station_id, {})
    station_name = station.get("station_name") or location.get("stationName") or station_id
    station_seq = int(location.get("stationSeq") or station.get("station_seq") or 0)
    return {
        "route_id": str(location.get("routeId", "")),
        "vehicle_id": str(location.get("vehId", "")),
        "plate_no": str(location.get("plateNo", "")),
        "predict_time_min": None,
        "location_no": 0,
        "current_station_name": station_name,
        "remain_seat_count": int(location.get("remainSeatCnt")) if location.get("remainSeatCnt") not in (None, "") else None,
        "station_id": station_id,
        "station_seq": station_seq,
        "station_name": station_name,
        "low_plate": location.get("lowPlate"),
        "plate_type": location.get("plateType"),
        "state_cd": location.get("stateCd"),
    }


def enrich_bus_with_arrival(bus: dict[str, Any], arrival: dict[str, Any] | None) -> None:
    if not arrival:
        return
    matched = None
    for candidate in arrival.get("buses", []):
        same_vehicle = bus.get("vehicle_id") and str(candidate.get("vehicle_id", "")) == str(bus.get("vehicle_id"))
        same_plate = bus.get("plate_no") and str(candidate.get("plate_no", "")) == str(bus.get("plate_no"))
        if same_vehicle or same_plate:
            matched = candidate
            break
    primary = matched or (arrival.get("buses") or [{}])[0]
    if primary.get("predict_time_min") is not None:
        bus["predict_time_min"] = primary.get("predict_time_min")
    if primary.get("location_no") is not None:
        bus["location_no"] = primary.get("location_no")
    if primary.get("current_station_name"):
        bus["current_station_name"] = primary.get("current_station_name")
    if primary.get("remain_seat_count") is not None:
        bus["remain_seat_count"] = primary.get("remain_seat_count")
    bus["eta_source"] = "arrival"


def build_direct_location_recommendation(
    bus: dict[str, Any],
    station_lookup: dict[str, dict[str, Any]],
    stations_by_seq: dict[int, dict[str, Any]],
    average_speed_kmh: float = 30.0,
) -> dict[str, Any] | None:
    current_seq = int(bus.get("station_seq") or 0)
    if current_seq <= 0:
        return None

    has_actual_arrival = bus.get("eta_source") == "arrival"
    max_seq = max(stations_by_seq) if stations_by_seq else current_seq
    target_seq = current_seq if has_actual_arrival else min(max_seq, current_seq + 2)
    if target_seq <= current_seq:
        target_seq = current_seq
    station = stations_by_seq.get(target_seq) or station_lookup.get(str(bus.get("station_id")), {})
    if not station:
        return None

    eta_minutes = bus.get("predict_time_min") if has_actual_arrival else estimate_direct_bus_eta_minutes(
        list(stations_by_seq.values()),
        current_station_seq=current_seq,
        target_station_seq=target_seq,
        average_speed_kmh=average_speed_kmh,
    )
    location_no = int(bus.get("location_no") or 0) if has_actual_arrival else max(0, target_seq - current_seq)
    if eta_minutes is None and bus.get("predict_time_min") is not None:
        eta_minutes = int(bus.get("predict_time_min"))
    if location_no == 0 and bus.get("location_no") not in (None, ""):
        location_no = int(bus.get("location_no") or 0)

    return {
        **station,
        "arrival": {
            "route_id": str(bus.get("route_id", "")),
            "station_id": str(station.get("station_id", "")),
            "sta_order": int(station.get("station_seq") or target_seq),
            "flag": "RUN" if has_actual_arrival else ("ESTIMATE" if eta_minutes is not None else "RUN"),
            "predict_time_min": eta_minutes,
            "location_no": location_no,
            "plate_no": bus.get("plate_no", ""),
            "current_station_name": bus.get("current_station_name", ""),
            "remain_seat_count": bus.get("remain_seat_count"),
            "result_message": "정상적으로 처리되었습니다." if has_actual_arrival else ("실시간 위치 기반 추정치" if eta_minutes is not None else "버스위치정보 직접조회"),
            "buses": [
                {
                    "vehicle_id": bus.get("vehicle_id", ""),
                    "plate_no": bus.get("plate_no", ""),
                    "predict_time_min": eta_minutes,
                    "location_no": location_no,
                    "current_station_name": bus.get("current_station_name", ""),
                    "remain_seat_count": bus.get("remain_seat_count"),
                }
            ],
        },
    }


def estimate_arrival_from_direct_locations(
    route_id: str,
    station_id: str,
    sta_order: int,
    stations: list[dict[str, Any]],
    direct_locations: list[dict[str, Any]],
    average_speed_kmh: float = 30.0,
) -> dict[str, Any] | None:
    candidate_buses: list[tuple[int, dict[str, Any]]] = []
    station_lookup = {str(station["station_id"]): station for station in stations}
    for location in direct_locations:
        bus = enrich_direct_bus_location(location, station_lookup)
        current_seq = int(bus.get("station_seq") or 0)
        delta = int(sta_order) - current_seq
        if delta < 0:
            continue
        candidate_buses.append((delta, bus))

    if not candidate_buses:
        return None

    candidate_buses.sort(key=lambda item: (item[0], str(item[1].get("plate_no") or "")))
    location_no, bus = candidate_buses[0]
    eta_minutes = estimate_direct_bus_eta_minutes(
        stations,
        current_station_seq=int(bus.get("station_seq") or 0),
        target_station_seq=int(sta_order),
        average_speed_kmh=average_speed_kmh,
    )
    return {
        "route_id": str(route_id),
        "route_name": "",
        "station_id": str(station_id),
        "sta_order": int(sta_order),
        "flag": "ESTIMATE",
        "predict_time_min": eta_minutes,
        "location_no": location_no,
        "plate_no": bus.get("plate_no", ""),
        "current_station_name": bus.get("current_station_name", ""),
        "remain_seat_count": bus.get("remain_seat_count"),
        "result_message": "실시간 위치 기반 추정치",
        "buses": [
            {
                "vehicle_id": bus.get("vehicle_id", ""),
                "plate_no": bus.get("plate_no", ""),
                "predict_time_min": eta_minutes,
                "location_no": location_no,
                "current_station_name": bus.get("current_station_name", ""),
                "remain_seat_count": bus.get("remain_seat_count"),
            }
        ],
    }


def estimate_direct_bus_eta_minutes(
    stations: list[dict[str, Any]],
    current_station_seq: int,
    target_station_seq: int,
    average_speed_kmh: float = 30.0,
) -> int | None:
    if target_station_seq <= current_station_seq:
        return 0

    cumulative = build_cumulative_distance_km_by_seq(stations)
    start_km = cumulative.get(int(current_station_seq))
    end_km = cumulative.get(int(target_station_seq))
    if start_km is None or end_km is None or end_km <= start_km:
        return max(1, target_station_seq - current_station_seq)

    speed = max(float(average_speed_kmh or 0), 1.0)
    minutes = ((end_km - start_km) / speed) * 60.0
    return max(1, round(minutes))


def build_timeline_eta_by_seq(
    stations: list[dict[str, Any]],
    live_buses: list[dict[str, Any]],
    average_speed_kmh: float = 30.0,
) -> dict[str, int]:
    timeline: dict[str, int] = {}
    for bus in live_buses:
        current_seq = derive_bus_current_station_seq(stations, bus)
        if current_seq is None:
            continue
        for station in stations:
            target_seq = int(station.get("station_seq") or 0)
            if target_seq < current_seq:
                continue
            eta = estimate_timeline_eta_for_bus(
                stations,
                bus,
                current_station_seq=current_seq,
                target_station_seq=target_seq,
                average_speed_kmh=average_speed_kmh,
            )
            if eta is None:
                continue
            key = str(target_seq)
            if key not in timeline or eta < timeline[key]:
                timeline[key] = eta
    return timeline


def estimate_timeline_eta_for_bus(
    stations: list[dict[str, Any]],
    bus: dict[str, Any],
    current_station_seq: int,
    target_station_seq: int,
    average_speed_kmh: float = 30.0,
) -> int | None:
    anchor_seq = int(bus.get("station_seq") or 0)
    anchor_eta = bus.get("predict_time_min")
    if bus.get("eta_source") == "arrival" and anchor_seq > 0 and anchor_eta not in (None, ""):
        anchor_eta = int(anchor_eta)
        if target_station_seq == anchor_seq:
            return anchor_eta
        if target_station_seq > anchor_seq:
            tail_eta = estimate_direct_bus_eta_minutes(
                stations,
                current_station_seq=anchor_seq,
                target_station_seq=target_station_seq,
                average_speed_kmh=average_speed_kmh,
            )
            if tail_eta is None:
                return anchor_eta
            return anchor_eta + tail_eta

        full_anchor_eta = estimate_direct_bus_eta_minutes(
            stations,
            current_station_seq=current_station_seq,
            target_station_seq=anchor_seq,
            average_speed_kmh=average_speed_kmh,
        )
        partial_eta = estimate_direct_bus_eta_minutes(
            stations,
            current_station_seq=current_station_seq,
            target_station_seq=target_station_seq,
            average_speed_kmh=average_speed_kmh,
        )
        if full_anchor_eta and partial_eta is not None:
            scaled_eta = anchor_eta * (partial_eta / full_anchor_eta)
            return max(0, round(scaled_eta))

    return estimate_direct_bus_eta_minutes(
        stations,
        current_station_seq=current_station_seq,
        target_station_seq=target_station_seq,
        average_speed_kmh=average_speed_kmh,
    )


def derive_bus_current_station_seq(stations: list[dict[str, Any]], bus: dict[str, Any]) -> int | None:
    station_name = str(bus.get("current_station_name") or "").strip()
    if station_name:
        for station in stations:
            if str(station.get("station_name") or "").strip() == station_name:
                return int(station.get("station_seq") or 0)

    seq = int(bus.get("station_seq") or 0)
    if not seq:
        return None
    if bus.get("eta_source") == "arrival" and bus.get("location_no") not in (None, ""):
        guessed = seq - int(bus.get("location_no") or 0)
        return guessed if guessed > 0 else seq
    return seq


def build_cumulative_distance_km_by_seq(stations: list[dict[str, Any]]) -> dict[int, float]:
    sorted_stations = sorted(stations, key=lambda station: int(station.get("station_seq") or 0))
    cumulative: dict[int, float] = {}
    previous: dict[str, Any] | None = None
    total_km = 0.0
    for station in sorted_stations:
        seq = int(station.get("station_seq") or 0)
        if previous is not None:
            total_km += station_distance_km(previous, station)
        cumulative[seq] = total_km
        previous = station
    return cumulative


def station_distance_km(a: dict[str, Any], b: dict[str, Any]) -> float:
    ax, ay = a.get("x"), a.get("y")
    bx, by = b.get("x"), b.get("y")
    if ax in (None, "") or ay in (None, "") or bx in (None, "") or by in (None, ""):
        return 0.0
    return haversine_km(float(ay), float(ax), float(by), float(bx))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import asin, cos, radians, sin, sqrt

    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)
    a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
    return 2 * radius_km * asin(sqrt(a))


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
