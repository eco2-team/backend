# 🚀 Pull Request · v0.8.2 Location 개발 완료 및 배포

## 📋 변경 사항
- Location 서비스 쿠키 기반 인증 전환 및 KST 타임존 설정
- PostgreSQL cube/earthdistance 확장 자동 설치 로직 구현
- 운영시간 API 응답 구조 개선 (실시간 상태 판단)
- Kubernetes Job 기반 DB 부트스트랩 파이프라인 구성

## 🔧 상세 내용

### 1. 쿠키 기반 인증 전환 및 KST 타임존 설정
- `domains/location/security.py`: `build_access_token_dependency` 사용해 쿠키(`s_access`)에서 JWT 토큰 검증
- `domains/location/core/config.py`: `auth_disabled` 플래그 추가 (로컬 테스트용)
- `Dockerfile`: `TZ=Asia/Seoul` 환경변수 및 `tzdata` 패키지 설치
- `docker-compose.location-local.yml`: `LOCATION_AUTH_DISABLED` 환경변수 추가

### 2. PostgreSQL 확장 자동 설치
- `domains/location/database/extensions.py`: `ensure_geospatial_extensions()` 헬퍼 함수 추가
- `import_zero_waste_locations.py`, `import_keco_sites.py`, `import_common_locations.py`: 스키마 생성 전 `cube`, `earthdistance` 확장 자동 설치
- 지리 공간 쿼리(`ll_to_earth`, `earth_distance`) 정상 동작 보장

### 3. 운영시간 API 응답 구조 개선
- `schemas/location.py`: `operating_hours` 객체 추가 (`status`, `start`, `end`), 기존 `hours` 필드 제거
- `services/location.py`: KST 기준 당일 요일의 운영시간 파싱 및 현재 시각 기준 실시간 상태(`open`/`closed`) 판단
- `domain/entities.py`, `models/normalized_site.py`, `repositories/normalized_site_repository.py`: `clct_item_cn` 필드 추가
- 제로웨이스트 데이터: `operating_hours: null`
- KECO 데이터: 요일별 파싱 후 현재 시각 기준 상태 결정 (예: `{"status":"closed","start":"12:00","end":"18:00"}`)

### 4. Kubernetes Job 기반 DB 부트스트랩 파이프라인
- `workloads/domains/location/base/`: 4개 Job 매니페스트 추가
  - `keco-import-job.yaml` (sync-wave: -40)
  - `db-bootstrap-job.yaml` (sync-wave: -30)
  - `common-dataset-build-job.yaml` (sync-wave: -20)
  - `common-dataset-import-job.yaml` (sync-wave: -10)
- `common-dataset-pvc.yaml` (sync-wave: -35): 정규화 데이터셋 공유를 위한 PVC
- `README.md`: 부트스트랩 Job 순서 및 재실행 가이드 문서화
- ArgoCD sync-wave 설정으로 Deployment 이전 순차 실행 보장

## 🧪 테스트
```bash
# 로컬 테스트 (auth disabled)
cd domains/location
LOCATION_AUTH_DISABLED=true docker-compose -f docker-compose.location-local.yml up --build -d

# API 확인
curl "http://127.0.0.1:8010/health"
curl "http://127.0.0.1:8010/api/v1/locations/centers?lat=37.5665&lon=126.9780&radius=5000"

# 인증 활성화 테스트
docker-compose -f docker-compose.location-local.yml down
docker-compose -f docker-compose.location-local.yml up --build -d
curl -i "http://127.0.0.1:8010/api/v1/locations/centers?lat=37.5665&lon=126.9780&radius=1000"
# Expected: 401 Missing access token
```

## 🚀 배포 영향
- Location API 재배포 시 Docker Hub 리포지토리(`docker.io/mng990/eco2:location-api-latest`) 동일
- ArgoCD dev/prod 환경에서 sync 시 Job이 자동으로 순차 실행 → Deployment 롤아웃
- 신규 DB 환경: 초기 sync로 확장 설치 + 스키마 생성 + 데이터 적재 자동 완료
- 기존 DB 환경: Job 재실행 필요시 `kubectl delete job -n location <job-name>` 후 sync

## ✅ 체크리스트
- [x] feature/location-service 브랜치 4개 커밋으로 논리적 단위 분리
- [x] GitHub에 브랜치 push 완료
- [ ] GitHub PR 생성 후 리뷰 요청
- [ ] ArgoCD dev 환경 sync 및 Job 성공 확인
- [ ] API 엔드포인트 스모크 테스트 (health, centers)

## 📌 참고
- 관련 문서: `docs/development/location/DATA_PIPELINE.md`, `workloads/domains/location/README.md`
- 운영시간 응답 구조 변경으로 클라이언트(프론트엔드) 측 업데이트 필요

