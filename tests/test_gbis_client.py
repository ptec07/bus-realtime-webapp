from app.gbis_client import (
    GbisClient,
    load_service_key,
    normalize_arrival_item,
    normalize_route_list,
    normalize_station_list,
)
import os


def test_get_recommended_stations_returns_only_live_candidates():
    class FakeClient(GbisClient):
        def __init__(self):
            pass

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "기점", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "중간", "station_seq": 2, "x": 127.2, "y": 37.2},
                {"station_id": "3", "station_name": "종점", "station_seq": 3, "x": 127.3, "y": 37.3},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            if station_id == "2":
                return {
                    "route_id": route_id,
                    "station_id": station_id,
                    "sta_order": sta_order,
                    "flag": "PASS",
                    "predict_time_min": 4,
                    "location_no": 1,
                    "plate_no": "경기74아3248",
                    "current_station_name": "중간",
                    "remain_seat_count": 8,
                    "result_message": "정상적으로 처리되었습니다.",
                    "buses": [
                        {
                            "vehicle_id": "bus-1",
                            "plate_no": "경기74아3248",
                            "predict_time_min": 4,
                            "location_no": 1,
                            "current_station_name": "중간",
                            "remain_seat_count": 8,
                        }
                    ],
                }
            return None

    client = FakeClient()

    assert client.get_recommended_stations("222000107", limit=2) == [
        {
            "station_id": "2",
            "station_name": "중간",
            "station_seq": 2,
            "x": 127.2,
            "y": 37.2,
            "arrival": {
                "route_id": "222000107",
                "station_id": "2",
                "sta_order": 2,
                "flag": "PASS",
                "predict_time_min": 4,
                "location_no": 1,
                "plate_no": "경기74아3248",
                "current_station_name": "중간",
                "remain_seat_count": 8,
                "result_message": "정상적으로 처리되었습니다.",
                "buses": [
                    {
                        "vehicle_id": "bus-1",
                        "plate_no": "경기74아3248",
                        "predict_time_min": 4,
                        "location_no": 1,
                        "current_station_name": "중간",
                        "remain_seat_count": 8,
                    }
                ],
            },
        }
    ]


def test_get_recommended_stations_skips_api_errors_instead_of_raising():
    class FakeClient(GbisClient):
        def __init__(self):
            pass

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "기점", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "중간", "station_seq": 2, "x": 127.2, "y": 37.2},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            raise RuntimeError("429")

    client = FakeClient()

    assert client.get_recommended_stations("222000107", limit=2) == []


def test_get_route_live_buses_skips_api_errors_instead_of_raising():
    class FakeClient(GbisClient):
        def __init__(self):
            pass

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "기점", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "중간", "station_seq": 2, "x": 127.2, "y": 37.2},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            raise RuntimeError("429")

    client = FakeClient()

    assert client.get_route_live_buses("222000107") == []


def test_get_recommended_stations_stops_after_scan_budget():
    class FakeClient(GbisClient):
        def __init__(self):
            self.calls = []
            self.max_station_scans = 3

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "A", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "B", "station_seq": 2, "x": 127.2, "y": 37.2},
                {"station_id": "3", "station_name": "C", "station_seq": 3, "x": 127.3, "y": 37.3},
                {"station_id": "4", "station_name": "D", "station_seq": 4, "x": 127.4, "y": 37.4},
                {"station_id": "5", "station_name": "E", "station_seq": 5, "x": 127.5, "y": 37.5},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            self.calls.append(station_id)
            return None

    client = FakeClient()

    assert client.get_recommended_stations("222000107", limit=3) == []
    assert client.calls == ["1", "2", "3"]


def test_get_route_live_buses_stops_after_scan_budget():
    class FakeClient(GbisClient):
        def __init__(self):
            self.calls = []
            self.max_station_scans = 2

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "A", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "B", "station_seq": 2, "x": 127.2, "y": 37.2},
                {"station_id": "3", "station_name": "C", "station_seq": 3, "x": 127.3, "y": 37.3},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            self.calls.append(station_id)
            return None

    client = FakeClient()

    assert client.get_route_live_buses("222000107") == []
    assert client.calls == ["1", "2"]


def test_get_route_live_snapshot_scans_stations_once_for_buses_and_recommendations():
    class FakeClient(GbisClient):
        def __init__(self):
            self.calls = []
            self.max_station_scans = 4

        def get_route_stations(self, route_id: str):
            return [
                {"station_id": "1", "station_name": "A", "station_seq": 1, "x": 127.1, "y": 37.1},
                {"station_id": "2", "station_name": "B", "station_seq": 2, "x": 127.2, "y": 37.2},
                {"station_id": "3", "station_name": "C", "station_seq": 3, "x": 127.3, "y": 37.3},
            ]

        def get_arrival(self, route_id: str, station_id: str, sta_order: int):
            self.calls.append(station_id)
            if station_id == "2":
                return {
                    "route_id": route_id,
                    "station_id": station_id,
                    "sta_order": sta_order,
                    "flag": "RUN",
                    "predict_time_min": 2,
                    "location_no": 1,
                    "plate_no": "경기70아1234",
                    "current_station_name": "B",
                    "remain_seat_count": 12,
                    "result_message": "정상적으로 처리되었습니다.",
                    "buses": [
                        {
                            "vehicle_id": "bus-1",
                            "plate_no": "경기70아1234",
                            "predict_time_min": 2,
                            "location_no": 1,
                            "current_station_name": "B",
                            "remain_seat_count": 12,
                        }
                    ],
                }
            return None

    client = FakeClient()

    snapshot = client.get_route_live_snapshot("222000107", recommendation_limit=2)

    assert snapshot["route_id"] == "222000107"
    assert len(snapshot["buses"]) == 1
    assert snapshot["recommendations"][0]["station_id"] == "2"
    assert client.calls == ["1", "2", "3"]


def test_normalize_route_list_returns_simplified_routes():
    payload = {
        "response": {
            "msgHeader": {"resultCode": 0, "resultMessage": "정상적으로 처리되었습니다."},
            "msgBody": {
                "busRouteList": [
                    {
                        "routeId": 222000107,
                        "routeName": 1001,
                        "startStationName": "청학리",
                        "endStationName": "잠실광역환승센터",
                        "adminName": "경기도 남양주시",
                        "regionName": "구리,남양주,서울",
                    }
                ]
            },
        }
    }

    assert normalize_route_list(payload) == [
        {
            "route_id": "222000107",
            "route_name": "1001",
            "start_station": "청학리",
            "end_station": "잠실광역환승센터",
            "admin_name": "경기도 남양주시",
            "region_name": "구리,남양주,서울",
        }
    ]


def test_normalize_station_list_returns_sequence_and_coordinates():
    payload = {
        "response": {
            "msgHeader": {"resultCode": 0},
            "msgBody": {
                "busRouteStationList": [
                    {
                        "stationId": 222001626,
                        "stationName": "청학리",
                        "stationSeq": 1,
                        "x": 127.111,
                        "y": 37.701,
                    }
                ]
            },
        }
    }

    assert normalize_station_list(payload) == [
        {
            "station_id": "222001626",
            "station_name": "청학리",
            "station_seq": 1,
            "x": 127.111,
            "y": 37.701,
            "turn_seq": 0,
            "turn_yn": "N",
        }
    ]


def test_normalize_arrival_item_returns_clean_status_fields():
    payload = {
        "response": {
            "msgHeader": {"resultCode": 0, "resultMessage": "정상적으로 처리되었습니다."},
            "msgBody": {
                "busArrivalItem": {
                    "routeId": 222000107,
                    "routeName": 1001,
                    "stationId": 222001626,
                    "staOrder": 1,
                    "flag": "RUN",
                    "predictTime1": 6,
                    "locationNo1": 3,
                    "plateNo1": "경기70아1234",
                    "stationNm1": "별내면사무소.에코랜드입구",
                    "remainSeatCnt1": 12,
                }
            },
        }
    }

    assert normalize_arrival_item(payload) == {
        "route_id": "222000107",
        "route_name": "1001",
        "station_id": "222001626",
        "sta_order": 1,
        "flag": "RUN",
        "predict_time_min": 6,
        "location_no": 3,
        "plate_no": "경기70아1234",
        "current_station_name": "별내면사무소.에코랜드입구",
        "remain_seat_count": 12,
        "result_message": "정상적으로 처리되었습니다.",
        "buses": [
            {
                "vehicle_id": "",
                "plate_no": "경기70아1234",
                "predict_time_min": 6,
                "location_no": 3,
                "current_station_name": "별내면사무소.에코랜드입구",
                "remain_seat_count": 12,
            }
        ],
    }


def test_normalize_arrival_item_collects_multiple_live_buses():
    payload = {
        "response": {
            "msgHeader": {"resultCode": 0, "resultMessage": "정상적으로 처리되었습니다."},
            "msgBody": {
                "busArrivalItem": {
                    "routeId": 222000107,
                    "routeName": 1001,
                    "stationId": 222001626,
                    "staOrder": 5,
                    "flag": "RUN",
                    "predictTime1": 2,
                    "predictTime2": 7,
                    "locationNo1": 1,
                    "locationNo2": 4,
                    "plateNo1": "경기70아1234",
                    "plateNo2": "경기70아5678",
                    "stationNm1": "별내면사무소.에코랜드입구",
                    "stationNm2": "주공2.3단지.농협.새마을금고",
                    "remainSeatCnt1": 12,
                    "remainSeatCnt2": 5,
                    "vehId1": "bus-1",
                    "vehId2": "bus-2",
                }
            },
        }
    }

    assert normalize_arrival_item(payload)["buses"] == [
        {
            "vehicle_id": "bus-1",
            "plate_no": "경기70아1234",
            "predict_time_min": 2,
            "location_no": 1,
            "current_station_name": "별내면사무소.에코랜드입구",
            "remain_seat_count": 12,
        },
        {
            "vehicle_id": "bus-2",
            "plate_no": "경기70아5678",
            "predict_time_min": 7,
            "location_no": 4,
            "current_station_name": "주공2.3단지.농협.새마을금고",
            "remain_seat_count": 5,
        },
    ]


def test_normalize_arrival_item_returns_none_when_api_has_no_result():
    payload = {
        "response": {
            "msgHeader": {"resultCode": 4, "resultMessage": "결과가 존재하지 않습니다."}
        }
    }

    assert normalize_arrival_item(payload) is None


def test_load_service_key_prefers_non_public_gbis_env(monkeypatch, tmp_path):
    monkeypatch.setenv("GBIS_SERVICE_KEY", "gbis-key")
    monkeypatch.delenv("PUBLIC_DATA_SERVICE_KEY", raising=False)
    monkeypatch.setattr("app.gbis_client.Path.home", lambda: tmp_path)

    assert load_service_key() == "gbis-key"
