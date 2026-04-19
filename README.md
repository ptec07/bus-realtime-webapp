# Bus Realtime Webapp

노선번호와 정류장을 검색해서 경기도 버스 실시간 도착정보를 조회하는 웹앱.

## 기능
- 노선번호 검색
- 노선별 정류장 목록 조회
- 정류장 이름 필터
- 정류장 좌표 표시
- 선택한 정류장의 실시간 도착정보 조회

## 실행
```bash
cd /home/ptec07/.hermes/hermes-agent/workforce/bus-realtime-webapp
source /home/ptec07/.hermes/hermes-agent/venv/bin/activate
uvicorn app.main:app --reload --port 8011
```

브라우저에서 `http://127.0.0.1:8011` 접속.

## 환경변수
우선순위:
1. `PUBLIC_DATA_SERVICE_KEY` 환경변수
2. `~/.hermes/.env` 안의 `PUBLIC_DATA_SERVICE_KEY`

## 테스트
```bash
cd /home/ptec07/.hermes/hermes-agent/workforce/bus-realtime-webapp
source /home/ptec07/.hermes/hermes-agent/venv/bin/activate
pytest tests/ -q
```

## Render 배포
이 앱은 `render.yaml` 기준으로 Render Web Service에 배포할 수 있다.

### Render 설정값
- Runtime: Python
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 환경변수: `PUBLIC_DATA_SERVICE_KEY`

### 배포 절차
1. Render에서 새 Web Service를 만든다.
2. 이 프로젝트 폴더를 기준으로 연결하거나, 같은 설정을 수동 입력한다.
3. `PUBLIC_DATA_SERVICE_KEY`를 Render 환경변수에 넣는다.
4. 배포 후 `/`, `/api/routes?query=1001`, `/api/arrival?...`를 확인한다.

Blueprint를 쓸 경우 프로젝트 루트의 `render.yaml`을 사용하면 된다.
