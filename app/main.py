from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

from app.gbis_client import GbisClient

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def create_app(client: GbisClient | None = None) -> FastAPI:
    app = FastAPI(title="Bus Realtime Webapp")
    gbis_client = client

    def get_client() -> GbisClient:
        nonlocal gbis_client
        if gbis_client is None:
            gbis_client = GbisClient()
        return gbis_client

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/routes")
    def search_routes(query: str | None = Query(default=None)):
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        return get_client().search_routes(query)

    @app.get("/api/routes/{route_id}/stations")
    def route_stations(route_id: str):
        return get_client().get_route_stations(route_id)

    @app.get("/api/routes/{route_id}/recommended-stations")
    def recommended_stations(route_id: str, limit: int = 3):
        return get_client().get_recommended_stations(route_id, limit=limit)

    @app.get("/api/routes/{route_id}/live-buses")
    def route_live_buses(route_id: str):
        return get_client().get_route_live_buses(route_id)

    @app.get("/api/routes/{route_id}/live-snapshot")
    def route_live_snapshot(route_id: str, recommendation_limit: int = 3):
        return get_client().get_route_live_snapshot(route_id, recommendation_limit=recommendation_limit)

    @app.get("/api/arrival")
    def arrival(route_id: str | None = None, station_id: str | None = None, sta_order: int | None = None):
        if not route_id or not station_id or sta_order is None:
            raise HTTPException(status_code=400, detail="route_id, station_id, sta_order are required")
        try:
            client = get_client()
            getter = getattr(client, "get_live_or_estimated_arrival", client.get_arrival)
            return getter(route_id, station_id, sta_order)
        except Exception:
            return None

    return app


app = create_app()
