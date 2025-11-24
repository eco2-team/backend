# Location 도메인 테스트 체크리스트

도커 컴포즈 기반 로컬 환경(`domains/location/docker-compose.location-local.yml`)을 기준으로 테스트합니다.

## 1. 환경 기동
- [ ] `docker compose -f domains/location/docker-compose.location-local.yml up --build -d`
- [ ] 컨테이너 상태 확인: `location-local-postgres`, `location-local-redis`, `location-local-api` 정상 동작

## 2. 데이터 적재
- [ ] CSV Import Job 실행  
  ```bash
  cd domains/location
  docker-compose -f docker-compose.location-local.yml run --rm api \
    python -m domains.location.jobs.import_zero_waste_locations \
    --csv-path domains/location/제로웨이스트\ 지도\ 데이터.csv \
    --database-url postgresql+asyncpg://location:location@db:5432/location
  ```
- [ ] `location.location_zero_waste_sites` 테이블 레코드 존재 여부 확인 (임의 쿼리 or 로그)

## 3. API 기능
- [ ] `GET /api/v1/locations/centers?lat=37.5665&lon=126.9780&radius=5000`  
  - 응답이 200이고 `LocationEntry` 배열 반환
  - `category`, `distance_km` 값 존재
- [ ] 반경 변경 테스트 (예: `radius=1000`, `radius=20000`) 시 결과 수 및 `distance_km` 상한이 반영되는지 확인
- [ ] `zoom` 파라미터만 전달했을 때 자동 반경/limit 적용 확인  
  (예: `GET ...?lat=37.5665&lon=126.9780&zoom=7`)
- [ ] `GET /api/v1/locations/metrics` (`/metrics` 엔드포인트 기준)  
  - `indexed_sites` 값이 CSV 건수와 일치

## 4. 캐싱/Redis
- [ ] Redis 컨테이너(포트 6381)에 접속해 `location:indexed_sites` 키가 생성되는지 확인 (`redis-cli -p 6381`)
- [ ] TTL 내 반복 호출 시 DB 로그/쿼리 수가 증가하지 않는지 확인
- [ ] Redis를 일시 중지 또는 비우고 재호출 시 DB에서 다시 카운트하는지 확인

## 5. 예외/엣지 케이스
- [ ] CSV 미적재 상태에서 API 호출 시 빈 배열 반환 (오류 없음)
- [ ] 잘못된 쿼리 파라미터(`lat` 범위 초과 등) 전달 시 FastAPI가 422를 반환하는지 확인
- [ ] 컨테이너 재시작 후에도 Compose 설정대로 자동 기동되는지 확인

## 6. 종료
- [ ] 테스트 완료 후 `cd domains/location && docker-compose -f docker-compose.location-local.yml down`
- [ ] 필요 시 `docker-compose -f docker-compose.location-local.yml down -v`

