# Bootstrap_DB - Location Normalized Dataset

정규화된 CSV(`domains/location/data/location_common_dataset.csv.gz`)를 DB에 직접 업서트하는 절차를 정리했습니다.  
별도의 PVC나 Raw 테이블 없이 **정규화 CSV → `location_normalized_sites` 업서트** 단계만 수행합니다.

---

## 1. 데이터 원본

| 항목 | 설명 |
|------|------|
| 정규화 CSV | `domains/location/data/location_common_dataset.csv.gz` |
| 생성 스크립트 | `python -m domains.location.jobs.sync_common_dataset` (로컬에서 실행하여 CSV 갱신) |
| Raw 자료 | `domains/location/data/keco_recycle_compensation_sites.csv`, `domains/location/data/제로웨이스트 지도 데이터.csv` |

> Raw CSV가 갱신되면 `sync_common_dataset.py`를 다시 실행해 정규화 CSV를 만들고 커밋합니다.

---

## 2. 스키마 / 테이블

- 테이블: `location.location_normalized_sites`
- PK: `positn_sn`
- Unique: `(source, source_pk)`
- 좌표/운영시간/설명/메타데이터를 KECO 스키마에 맞춰 보관
- Job은 `ON CONFLICT` 업서트로 동작하여 반복 실행 시에도 안전합니다.

---

## 3. 환경 변수

| 변수 | 설명 |
|------|------|
| `LOCATION_DATABASE_URL` | `postgresql+asyncpg://user:pw@host:5432/location` |
| `DATABASE_URL` | 위 값이 없을 때 fallback |

---

## 4. 실행 방법 (수동)

```bash
cd /Users/mango/workspace/SeSACTHON/backend
export LOCATION_DATABASE_URL="postgresql+asyncpg://user:pw@localhost:5432/location"

python -m domains.location.jobs.import_common_locations \
  --csv-path domains/location/data/location_common_dataset.csv.gz \
  --batch-size 500
```

실행 결과:

```
Imported 760 normalized rows from domains/location/data/location_common_dataset.csv.gz
```

### 주요 옵션
- `--csv-path`: gzip/평문 CSV 모두 지원 (기본은 레포 내 정규화 파일)
- `--database-url`: CLI 인자로 DB 연결 문자열 지정
- `--batch-size`: Insert batch 크기 (기본 200)

---

## 5. 자동화/배포 연계

1. **CSV 갱신 플로우**
   - Raw CSV 최신본 반영 → `python -m domains.location.jobs.sync_common_dataset`
   - 결과 `location_common_dataset.csv.gz`를 커밋

2. **Kubernetes Job**
   - `workloads/domains/location/base/normalized-import-job.yaml` 이 위 스크립트를 실행해 DB에 업서트
   - Hook wave 10에서 실행되어 Deployment 전에 데이터가 준비됩니다.

3. **로컬 Docker Compose**
   - `normalized-import` 서비스가 동일 명령을 수행합니다.
   - 필요 시 `docker-compose -f domains/location/docker-compose.location-local.yml run --rm normalized-import`

---

## 6. 문제 해결

| 증상 | 조치 |
|------|------|
| `Set LOCATION_DATABASE_URL or DATABASE_URL` | 환경 변수 또는 `--database-url` 옵션 확인 |
| `CSV file not found` | 경로/파일명, gzip 여부 확인 |
| `psycopg2.OperationalError` | DB 접속 정보/보안그룹 확인 |
| 레코드 수 차이 | Raw CSV 업데이트 후 정규화 스크립트 재실행 |

---

## 7. 레퍼런스

- 정규화 생성 스크립트: `domains/location/jobs/sync_common_dataset.py`
- DB 업서트 스크립트: `domains/location/jobs/import_common_locations.py`
- Kubernetes Job: `workloads/domains/location/base/normalized-import-job.yaml`
- Docker Compose: `domains/location/docker-compose.location-local.yml`

