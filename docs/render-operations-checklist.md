# Render 운영 체크리스트

## 대상
- 서비스명: `bus-realtime-webapp`
- 저장소: `https://github.com/ptec07/bus-realtime-webapp`
- 운영 URL: `https://bus-realtime-webapp.onrender.com`
- Runtime: Python
- Branch: `main`

## 필수 환경변수
### Render
- `PUBLIC_DATA_SERVICE_KEY`

확인 포인트:
- 값이 비어 있지 않은가
- 경기도 버스 OpenAPI에서 실제로 유효한 키인가
- 키를 재발급했다면 Render 값도 함께 갱신했는가

## Render 서비스 설정값
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/`
- Auto Deploy: `yes`
- Repo: `ptec07/bus-realtime-webapp`
- Branch: `main`

## 배포 전 체크
1. 로컬 코드 변경 범위를 확인한다.
2. 테스트를 실행한다.
   ```bash
   cd /home/ptec07/.hermes/hermes-agent/workforce/bus-realtime-webapp
   source /home/ptec07/.hermes/hermes-agent/venv/bin/activate
   pytest tests/ -q
   ```
3. 운영에 필요한 문서/설정도 같이 반영됐는지 확인한다.
4. 실수로 민감값이 커밋에 포함되지 않았는지 확인한다.

## 배포 후 체크
### 1) 홈 응답
```bash
curl -fsS https://bus-realtime-webapp.onrender.com/ | grep '실시간 버스정보'
```

### 2) 노선 검색
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/routes?query=1001'
```

### 3) 추천 정류장 응답
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/routes/222000107/recommended-stations?limit=3'
```

### 4) 단일 도착 정보
```bash
curl -fsS 'https://bus-realtime-webapp.onrender.com/api/arrival?route_id=222000107&station_id=222001626&sta_order=1'
```

## 장애 점검 포인트
### 홈은 뜨는데 API가 실패할 때
- `PUBLIC_DATA_SERVICE_KEY` 누락 여부
- 키 만료/오타 여부
- 외부 공공 API 응답 상태 확인

### 추천 정류장이 비어 있을 때
- 추천 API는 실시간 위치가 잡힌 정류장만 반환한다.
- 특정 시점에는 버스 위치 데이터가 비어 있을 수 있다.
- 이 경우 일반 정류장 목록과 단일 `/api/arrival` 응답도 같이 확인한다.

### Render 배포는 성공했는데 최신 코드가 안 보일 때
- Render 서비스가 GitHub `main`에 연결되어 있는지 확인
- 최근 deploy가 실제 최신 commit SHA를 가리키는지 확인
- Auto Deploy가 꺼져 있지 않은지 확인
- 필요하면 수동 redeploy 실행

## 운영 중 자주 볼 값
- Render dashboard URL
- 최근 deploy 상태: `build_in_progress`, `update_in_progress`, `live`, `build_failed`
- GitHub 최신 commit SHA
- 추천 정류장 API의 실제 응답 본문

## 보안 메모
- GitHub 토큰, Render API 키, 공공데이터 서비스키는 채팅/커밋/문서에 평문 저장하지 않는다.
- 이미 노출된 토큰은 폐기 후 재발급한다.
