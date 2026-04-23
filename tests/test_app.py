from fastapi.testclient import TestClient
import os

from app.main import create_app


class StubClient:
    def search_routes(self, query: str):
        return [{
            "route_id": "222000107",
            "route_name": query,
            "start_station": "청학리",
            "end_station": "잠실광역환승센터",
            "admin_name": "경기도 남양주시",
            "region_name": "구리,남양주,서울",
        }]

    def get_route_stations(self, route_id: str):
        return [
            {
                "station_id": "222001626",
                "station_name": "청학리",
                "station_seq": 1,
                "x": 127.111,
                "y": 37.701,
                "turn_seq": 3,
                "turn_yn": "N",
            },
            {
                "station_id": "222001300",
                "station_name": "극동마이다스빌.다우에코빌",
                "station_seq": 2,
                "x": 127.114,
                "y": 37.708,
                "turn_seq": 3,
                "turn_yn": "N",
            },
            {
                "station_id": "222000624",
                "station_name": "회차지",
                "station_seq": 3,
                "x": 127.116,
                "y": 37.707,
                "turn_seq": 3,
                "turn_yn": "Y",
            },
            {
                "station_id": "222000625",
                "station_name": "상행복귀1",
                "station_seq": 4,
                "x": 127.118,
                "y": 37.706,
                "turn_seq": 3,
                "turn_yn": "N",
            },
        ]

    def get_recommended_stations(self, route_id: str, limit: int = 3):
        return [{
            "station_id": "277103211",
            "station_name": "퇴계원IC진입(경유)",
            "station_seq": 33,
            "x": 127.133,
            "y": 37.642,
            "arrival": {
                "route_id": route_id,
                "station_id": "277103211",
                "sta_order": 33,
                "flag": "PASS",
                "predict_time_min": 2,
                "location_no": 1,
                "plate_no": "경기74아3248",
                "current_station_name": "별내동주민센터입구.우미린아파",
                "remain_seat_count": 41,
                "result_message": "정상적으로 처리되었습니다.",
            },
        }][:limit]

    def get_arrival(self, route_id: str, station_id: str, sta_order: int):
        return {
            "route_id": route_id,
            "station_id": station_id,
            "sta_order": sta_order,
            "flag": "RUN",
            "predict_time_min": 6,
            "location_no": 3,
            "plate_no": "경기70아1234",
            "current_station_name": "별내면사무소.에코랜드입구",
            "remain_seat_count": 12,
            "result_message": "정상적으로 처리되었습니다.",
            "buses": [
                {
                    "vehicle_id": "bus-1",
                    "plate_no": "경기70아1234",
                    "predict_time_min": 6,
                    "location_no": 3,
                    "current_station_name": "별내면사무소.에코랜드입구",
                    "remain_seat_count": 12,
                },
                {
                    "vehicle_id": "bus-2",
                    "plate_no": "경기70아5678",
                    "predict_time_min": 2,
                    "location_no": 1,
                    "current_station_name": "극동마이다스빌.다우에코빌",
                    "remain_seat_count": 5,
                },
            ],
        }

    def get_route_live_buses(self, route_id: str):
        return [
            {
                "vehicle_id": "bus-1",
                "plate_no": "경기70아1234",
                "predict_time_min": 6,
                "location_no": 3,
                "current_station_name": "별내면사무소.에코랜드입구",
                "remain_seat_count": 12,
                "station_seq": 1,
                "station_id": "222001626",
                "direction": "상행",
            },
            {
                "vehicle_id": "bus-2",
                "plate_no": "경기70아5678",
                "predict_time_min": 2,
                "location_no": 1,
                "current_station_name": "극동마이다스빌.다우에코빌",
                "remain_seat_count": 5,
                "station_seq": 2,
                "station_id": "222001300",
                "direction": "상행",
            },
        ]


def make_client():
    app = create_app(client=StubClient())
    return TestClient(app)


def test_index_page_renders_route_timeline_ui_without_map():
    response = make_client().get("/")

    assert response.status_code == 200
    assert "실시간 버스정보" in response.text
    assert "노선번호" in response.text
    assert "노선 타임라인" in response.text
    assert "route-query-clear" in response.text
    assert 'id="route-timeline"' in response.text
    assert 'id="map"' not in response.text
    assert "leaflet" not in response.text.lower()
    assert "현재 버스 위치를 찾으면 정류장 사이에 표시해줄게." not in response.text
    assert "정류장명 하단에 계산된" not in response.text


def test_index_page_contains_timeline_and_refresh_scripts():
    response = make_client().get("/")

    assert response.status_code == 200
    assert "computeTimelineState" in response.text
    assert "renderTimeline" in response.text
    assert "renderBusMarker" in response.text
    assert "loadLiveBuses" in response.text
    assert "clearRouteQuery" in response.text
    assert "Promise.allSettled" in response.text
    assert "renderTimeline();" in response.text
    assert "window.location.reload()" in response.text
    assert "loadRouteTimeline" in response.text


def test_routes_api_returns_route_matches():
    response = make_client().get("/api/routes", params={"query": "1001"})

    assert response.status_code == 200
    assert response.json()[0]["route_id"] == "222000107"


def test_routes_api_requires_query():
    response = make_client().get("/api/routes")

    assert response.status_code == 400


def test_route_stations_api_returns_station_list():
    response = make_client().get("/api/routes/222000107/stations")

    assert response.status_code == 200
    assert response.json()[0]["station_name"] == "청학리"


def test_recommended_stations_api_returns_live_station_candidates():
    response = make_client().get("/api/routes/222000107/recommended-stations")

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["station_name"] == "퇴계원IC진입(경유)"
    assert payload[0]["arrival"]["location_no"] == 1


def test_route_live_buses_api_returns_multiple_running_buses():
    response = make_client().get("/api/routes/222000107/live-buses")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert payload[0]["plate_no"] == "경기70아1234"
    assert payload[1]["plate_no"] == "경기70아5678"


def test_arrival_api_returns_live_bus_payload():
    response = make_client().get(
        "/api/arrival",
        params={"route_id": "222000107", "station_id": "222001626", "sta_order": 1},
    )

    assert response.status_code == 200
    assert response.json()["flag"] == "RUN"
    assert response.json()["predict_time_min"] == 6


def test_arrival_api_requires_all_params():
    response = make_client().get("/api/arrival", params={"route_id": "222000107"})

    assert response.status_code == 400


def test_index_page_renders_without_eager_service_key_lookup(monkeypatch, tmp_path):
    monkeypatch.delenv("PUBLIC_DATA_SERVICE_KEY", raising=False)
    monkeypatch.setattr(os, "getenv", lambda key, default=None: None)
    monkeypatch.setattr("app.gbis_client.Path.home", lambda: tmp_path)

    response = TestClient(create_app(client=False)).get("/")

    assert response.status_code == 200
    assert "실시간 버스정보" in response.text
