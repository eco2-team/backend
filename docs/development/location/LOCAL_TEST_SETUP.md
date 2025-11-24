# Location 도메인 로컬 테스트 가이드

## 1. 구성 요소

| 서비스 | 설명 | 포트 |
| --- | --- | --- |
| `db` | Postgres 16, `location/location` 계정 | Host `5434` → Container `5432` |
| `api` | `domains/location/Dockerfile` 기반 FastAPI | Host `8010` → Container `8000` |

`domains/location/docker-compose.location-local.yml` 에 정의되어 있습니다.

## 2. 실행

```bash
# 프로젝트 루트에서
docker compose -f domains/location/docker-compose.location-local.yml up --build -d

# 로그 확인 (선택)
docker compose -f domains/location/docker-compose.location-local.yml logs -f api
```

## 3. 데이터 적재

CSV 데이터를 Postgres에 넣어야 반경 검색 API가 동작합니다. Job 스크립트를 컨테이너에서 실행하세요.

```bash
docker compose -f domains/location/docker-compose.location-local.yml run --rm api \
  python -m domains.location.jobs.import_zero_waste_locations \
  --csv-path domains/location/제로웨이스트\ 지도\ 데이터.csv \
  --database-url postgresql+asyncpg://location:location@db:5432/location
```

## 4. API 확인

```
GET http://localhost:8010/api/v1/locations/centers?lat=37.5665&lon=126.9780&radius=5000
```

응답은 `LocationEntry[]` 형식이며 `category`, `distance_km` 등을 포함합니다.

## 5. 종료

```bash
docker compose -f domains/location/docker-compose.location-local.yml down
# 데이터 유지가 필요 없다면 volume 제거
docker compose -f domains/location/docker-compose.location-local.yml down -v
```

필요 시 `docker compose exec db psql -U location -d location` 으로 DB에 접속해 직접 데이터를 조회할 수 있습니다.

