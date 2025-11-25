# Location API 배포 체크리스트

## 1. 서비스 개요
- **Base Path**: `/api/v1/location`
- **Swagger UI**: `/api/v1/location/docs`
- **ReDoc**: `/api/v1/location/redoc`
- **OpenAPI JSON**: `/api/v1/location/openapi.json`
- **Metrics**: `/api/v1/location/metrics`
- **Health Check**: `/health`

## 2. 사전 준비
- [ ] `location` namespace 및 `location-secret`(ExternalSecret) 동기화
- [ ] PostgreSQL Helm (Bitnami) 및 Redis 클러스터 정상 동작
- [ ] `location-db-bootstrap` Job이 cube/earthdistance 확장과 `location` 스키마를 생성하도록 설정
- [ ] Docker Hub Pull Secret (`dockerhub-secret`) 준비

## 3. 배포 순서 (Argo CD 기준)
1. `dev-postgresql` / `prod-postgresql` Application 동기화 (이미 동작 중이라면 건너뜀)
2. `dev-ingresses` / `prod-ingresses` ApplicationSet에 `location` 인그레스가 포함되었는지 확인
3. `dev-apis` / `prod-apis` ApplicationSet 동기화 → 다음 Job이 순차 실행
   - `location-db-bootstrap`
   - `location-normalized-import`
4. `location-api` Deployment 롤아웃 완료 대기

## 4. 배포 후 검증
- [ ] `kubectl get jobs -n location` 로 모든 Job이 `Completed` 상태인지 확인
- [ ] `kubectl get ingress -n location location-ingress`
- [ ] `/health` → 200
- [ ] `/api/v1/location/docs` 페이지 로딩 확인
- [ ] `/api/v1/location/metrics` 인증 후 호출 시 정상 응답
- [ ] 실제 API (`/api/v1/location/locations/centers`)로 샘플 쿼리 실행

## 5. 문제 해결
- **확장 설치 실패**: `kubectl logs job/location-db-bootstrap` 확인 후, 필요 시 `kubectl delete job/location-db-bootstrap -n location`
- **Secret 누락**: `kubectl describe externalsecret/location-secret -n location` 로 동기화 상태 확인
- **Ingress 라우팅 이슈**: `kubectl describe ingress location-ingress -n location` 및 ALB TargetGroup 상태 확인

## 6. 참고 문서
- `workloads/domains/location/README.md`
- `docs/development/location/LOCAL_TEST_SETUP.md`
- `docs/data/POSTGRESQL_HELM_SETUP.md`

