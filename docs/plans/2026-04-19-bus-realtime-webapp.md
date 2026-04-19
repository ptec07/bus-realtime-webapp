# Bus Realtime Webapp Implementation Plan

> **For Hermes:** implement in strict TDD order. No production code before a failing test.

**Goal:** 노선번호와 정류장을 검색해서 실시간 버스 도착정보를 확인할 수 있는 웹앱을 만든다.

**Architecture:** FastAPI 백엔드가 경기도 버스 OpenAPI를 프록시하고, 단일 HTML/JS 프런트엔드가 노선 검색 → 정류장 선택 → 실시간 조회 흐름을 제공한다. 서비스 키는 하드코딩하지 않고 환경변수 또는 `~/.hermes/.env` fallback에서 읽는다.

**Tech Stack:** Python 3.11, FastAPI, Jinja2, pytest, httpx TestClient, vanilla JavaScript.

---

### Task 1: 프로젝트 골격 생성
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/gbis_client.py`
- Create: `app/templates/index.html`
- Create: `tests/test_gbis_client.py`
- Create: `tests/test_app.py`
- Create: `requirements.txt`
- Create: `README.md`

### Task 2: API 클라이언트 테스트 먼저 작성
- route 검색 결과 정규화 테스트
- station 목록 정규화 테스트
- arrival 응답 정규화 테스트
- no-result / empty 응답 처리 테스트

### Task 3: 최소 API 클라이언트 구현
- `search_routes()`
- `get_route_stations()`
- `get_arrival()`
- env key loading with `~/.hermes/.env` fallback

### Task 4: FastAPI 엔드포인트 테스트 먼저 작성
- `/` HTML 반환
- `/api/routes` 검증
- `/api/routes/{route_id}/stations`
- `/api/arrival`
- 필수 파라미터 누락 시 400

### Task 5: FastAPI 앱 구현
- 템플릿 렌더
- API client dependency
- JSON endpoint 응답 형식 통일

### Task 6: 프런트엔드 구현
- 노선번호 검색 입력
- 검색 결과 목록
- 정류장 이름 필터 + 좌표/지도 링크 표시
- 정류장 클릭 시 실시간 도착정보 표시

### Task 7: 문서화 및 실행 검증
- README에 실행 방법 작성
- pytest 실행
- uvicorn 서버 기동 확인
