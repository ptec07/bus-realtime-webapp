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
    def __init__(self, service_key: str | None = None, timeout: int = 20):
        self.service_key = service_key or load_service_key()
        self.timeout = timeout

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
        recommendations: list[dict[str, Any]] = []
        for station in self.get_route_stations(route_id):
            arrival = self.get_arrival(route_id, station["station_id"], station["station_seq"])
            if not arrival or not has_live_position(arrival):
                continue
            recommendations.append({**station, "arrival": arrival})
            if len(recommendations) >= limit:
                break
        return recommendations

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
        }
        for item in items
    ]


def has_live_position(arrival: dict[str, Any]) -> bool:
    return bool(
        arrival.get("location_no") is not None
        or arrival.get("current_station_name")
        or arrival.get("plate_no")
    )


def normalize_arrival_item(payload: dict[str, Any]) -> dict[str, Any] | None:
    header = _header(payload)
    if int(header.get("resultCode", -1)) == 4:
        return None

    item = payload.get("response", {}).get("msgBody", {}).get("busArrivalItem", {})
    return {
        "route_id": str(item.get("routeId", "")),
        "route_name": str(item.get("routeName", "")),
        "station_id": str(item.get("stationId", "")),
        "sta_order": int(item.get("staOrder", 0)),
        "flag": item.get("flag", ""),
        "predict_time_min": item.get("predictTime1") or None,
        "location_no": item.get("locationNo1") or None,
        "plate_no": item.get("plateNo1") or "",
        "current_station_name": item.get("stationNm1") or "",
        "remain_seat_count": item.get("remainSeatCnt1") or None,
        "result_message": header.get("resultMessage", ""),
    }
