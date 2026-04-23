# Bus Realtime Webapp

노선번호와 정류장을 검색해서 경기도 버스 실시간 도착정보를 조회하는 웹앱.

## 기능
- 노선번호 검색
- 노선별 정류장 목록 조회
- 정류장 이름 필터
- 세로형 노선 타임라인 표시
- 정류장별 계산된 예상 도착시간 표시
- 정류장 사이 현재 버스 위치 아이콘 표시
- 선택한 정류장의 실시간 도착정보 조회
- 현재 차량 위치 기반 추천 정류장 3개 우선 표시

## 저장소 / 배포 구조
- GitHub 저장소: `https://github.com/ptec07/bus-realtime-webapp`
- 운영 URL: `https://bus-realtime-webapp.onrender.com`
- 배포 방식: **Render Web Service + GitHub `main` 자동 배포**
- Render 서비스명: `bus-realtime-webapp`

### 현재 운영 연결 상태
- Render는 `main` 브랜치 커밋을 기준으로 자동 배포한다.
- Python native runtime으로 동작한다.
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/`

## 로컬 실행
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

운영 배포(Render)에서는 반드시 Render 환경변수에 `PUBLIC_DATA_SERVICE_KEY`를 넣어야 한다.

## 테스트
```bash
cd /home/ptec07/.hermes/hermes-agent/workforce/bus-realtime-webapp
source /home/ptec07/.hermes/hermes-agent/venv/bin/activate
pytest tests/ -q
```

## Render 배포
- Render Blueprint 설정 파일: `render.yaml`
- 필수 환경변수: `PUBLIC_DATA_SERVICE_KEY`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 운영 URL: `https://bus-realtime-webapp.onrender.com`

## 배포 파일
### `render.yaml`
현재 저장소에는 Render Blueprint용 설정 파일이 포함돼 있다.

```yaml
services:
  - type: web
    name: bus-realtime-webapp
    runtime: python
    plan: free
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
    envVars:
      - key: PUBLIC_DATA_SERVICE_KEY
        sync: false
```

## GitHub + Render 운영 흐름
1. 로컬에서 수정
2. `pytest tests/ -q` 통과 확인
3. GitHub `main`에 push
4. Render가 `main` 커밋 기준 자동 배포
5. 운영 URL에서 실제 응답 확인

## 배포 후 최소 검증 체크
### 홈
```bash
curl -fsS https://bus-realtime-webapp.onrender.com/ | grep '실시간 버스정보'
```

### 노선 검색
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/routes?query=1001'
```

### 추천 정류장
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/routes/222000107/recommended-stations?limit=3'
```

### 단일 정류장 도착정보
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/arrival?route_id=222000107&station_id=222001626&sta_order=1'
```

## 운영 메모
- Vercel에서는 외부 API 인증 문제로 실시간 위치가 안정적이지 않았고, 현재 운영은 Render 기준이다.
- 추천 정류장 API는 현재 실시간 위치 정보가 있는 정류장만 최대 3개 반환한다.
- GitHub 저장소 연결 후에는 임시 Docker 이미지 레지스트리 배포 대신 GitHub 커밋 기반으로 관리한다.

## 운영 체크리스트 문서
상세 운영 체크리스트는 아래 문서 참고:
- `docs/render-operations-checklist.md`
