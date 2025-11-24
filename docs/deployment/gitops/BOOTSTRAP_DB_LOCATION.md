# Bootstrap_DB - Location Zero Waste Data

`domains/location/jobs/import_zero_waste_locations.py` 스크립트를 이용해 제로웨이스트 지도 CSV 데이터를 Postgres에 적재하는 절차를 정리했습니다.  
Auth 서비스 사용자 스키마 생성 로직과 동일하게 **스키마 보장 → 테이블 생성 → UPSERT** 순서로 동작합니다.

---

## 1. 데이터 원본

| 항목 | 설명 |
|------|------|
| CSV 파일 | `domains/location/제로웨이스트 지도 데이터.csv` (UTF-8, 헤더 포함) |
| 컬럼 | `folderId, seq, favoriteType, color, memo, display1, display2, x, y, lon, lat, key, createdAt, updatedAt` |
| 주기 | 필요 시 최신본으로 교체 후 재실행 (UPSERT) |

---

## 2. 스키마 / 테이블

스크립트는 실행 시 자동으로 `location` 스키마와 `location_zero_waste_sites` 테이블을 생성합니다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `seq` | `bigint` | **PK**, CSV `seq` |
| `folder_id` | `bigint` | CSV `folderId` |
| `favorite_type` | `varchar(16)` | CSV `favoriteType` |
| `color` | `int` | CSV `color` |
| `memo` / `display1` / `display2` | `text` | 설명 필드 |
| `x`, `y`, `lon`, `lat` | `float` | TM 좌표 및 위경도 |
| `place_key` | `varchar(64)` | CSV `key` |
| `created_at`, `updated_at` | `timestamp with time zone` | CSV 일시 (`YYYY-MM-DD HH:MM:SS`) |

`ON CONFLICT (seq) DO UPDATE` 로 동작하여 기존 레코드는 최신 값으로 덮어씁니다.

---

## 3. 환경 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `LOCATION_DATABASE_URL` | 우선 사용되는 DB 연결 문자열 (`postgresql+asyncpg://user:pass@host:5432/location`) | `postgresql+asyncpg://mango:pw@dev-postgres:5432/location` |
| `DATABASE_URL` | `LOCATION_DATABASE_URL` 미설정 시 fallback | 동일 |

※ CI/배포 환경에서는 `LOCATION_DATABASE_URL` 환경 변수로 location 전용 DB/스키마를 지정하세요.

---

## 4. 실행 방법 (수동)

```bash
cd /Users/mango/workspace/SeSACTHON/backend
export LOCATION_DATABASE_URL="postgresql+asyncpg://user:pw@localhost:5432/location"

python -m domains.location.jobs.import_zero_waste_locations \
  --csv-path domains/location/제로웨이스트\ 지도\ 데이터.csv \
  --batch-size 500
```

실행 결과:
```
Imported 352 rows from /.../제로웨이스트 지도 데이터.csv into location_zero_waste_sites
```

### 주요 옵션
- `--csv-path` : CSV 다른 버전을 지정할 때 사용
- `--database-url` : 환경 변수 대신 CLI에서 직접 연결 문자열 지정
- `--batch-size` : 대량 데이터 처리 시 Insert batch 크기 (기본 200)

---

## 5. 자동화/배포 연계

1. **Repository 내 저장**  
   - CSV 최신본을 `domains/location/제로웨이스트 지도 데이터.csv` 위치에 갱신
   - 위 스크립트 실행 후 `location_zero_waste_sites` 를 최신 상태로 맞춤

2. **GitHub Actions / Cron**  
   - 추후 필요 시 `python -m domains.location.jobs.import_zero_waste_locations` 명령을 포함하는 Workflow를 만들어 주기적으로 실행 가능
   - K8s CronJob으로도 쉽게 전환 가능 (컨테이너 이미지에서 동일 명령 호출)

3. **서비스 참조**  
   - Location API가 향후 DB 데이터를 직접 조회할 경우, 해당 테이블을 기준으로 Repository/Service 계층을 구성하면 됩니다.

---

## 6. 문제 해결

| 증상 | 조치 |
|------|------|
| `Set LOCATION_DATABASE_URL or DATABASE_URL` 오류 | 환경 변수 또는 `--database-url` 옵션 확인 |
| `FileNotFoundError` | `--csv-path` 경로, 파일명(한글 포함) 확인 |
| `psycopg2.OperationalError` / 연결 실패 | DB 보안 그룹/포트/자격 증명 확인 |
| 일부 열이 비어 있음 | CSV 원본에 공백/빈 문자열인 경우 `NULL`로 저장됨 (설계 의도) |

---

## 7. 레퍼런스

- Job 스크립트: `domains/location/jobs/import_zero_waste_locations.py`
- CSV 원본: `domains/location/제로웨이스트 지도 데이터.csv`
- Auth 사용자 업서트 레퍼런스: `domains/auth/models/user.py`, `domains/auth/repositories/user_repository.py`


