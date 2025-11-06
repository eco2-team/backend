# 📋 버전 관리 가이드

> **목적**: 프로젝트 버전 관리 전략 및 릴리스 프로세스 정의

---

## 📌 버전 체계 (Semantic Versioning)

### 기본 형식

```
MAJOR.MINOR.PATCH
```

- **MAJOR**: 아키텍처 변경 또는 breaking changes
- **MINOR**: 새로운 기능/단계 완료 (backward compatible)
- **PATCH**: 문서 개선, 버그 수정, 마이너 업데이트

### 버전 범위 정의

```
0.x.y  → 초기 개발 단계 (Pre-Production)
1.x.y  → 프로덕션 릴리스 (Production-Ready)
2.x.y  → 메이저 아키텍처 변경
```

---

## 🎯 현재 버전 전략

### v0.x.y - 초기 개발 단계

**특징:**
- ✅ Breaking changes 자유롭게 허용
- ✅ 실험적 기능 테스트 가능
- ✅ 빠른 반복 개발
- ⚠️ 프로덕션 사용 불가

**버전 히스토리:**

| 버전 | 날짜 | 마일스톤 | 상태 |
|------|------|----------|------|
| v0.1.0 | 2025-11-01 | 인프라 프로비저닝 | ✅ 완료 |
| v0.2.0 | 2025-11-03 | Kubernetes 플랫폼 구축 | ✅ 완료 |
| v0.3.0 | 2025-11-04 | 인프라 자동화 & 모니터링 | ✅ 완료 |
| v0.4.0 | 2025-11-05 | GitOps 인프라 구축 | ✅ 완료 |
| v0.4.1 | 2025-11-06 | GitOps 파이프라인 문서화 | ✅ 완료 |
| v0.5.0 | 2025-11-06 | 13-Node 마이크로서비스 아키텍처 | ✅ 완료 |
| v0.6.0 | 예정 | Worker Local SQLite WAL | 🔄 진행 중 |
| v0.7.0 | 예정 | 모니터링 & 알림 강화 | ⏳ 계획 중 |
| v0.8.0 | 예정 | 고급 배포 전략 (Canary) | ⏳ 계획 중 |
| v0.9.0 | 예정 | 성능 최적화 & 보안 강화 | ⏳ 계획 중 |

### v1.0.0 - 첫 프로덕션 릴리스

**조건:**
- ✅ 모든 마이크로서비스 배포 완료
- ✅ CI/CD 파이프라인 안정화
- ✅ 모니터링 & 알림 시스템 구축
- ✅ 로드 테스트 완료
- ✅ 보안 감사 완료
- ✅ 문서화 100% 완료
- ✅ 프로덕션 체크리스트 통과

**릴리스 노트 예시:**

```markdown
# v1.0.0 - 프로덕션 릴리스 (2025-XX-XX)

## 🎉 주요 기능

- ✅ ♻️ 이코에코(Eco²) 서비스 정식 배포
- ✅ 7-Node Kubernetes 클러스터 운영
- ✅ GitOps 기반 자동 배포 파이프라인
- ✅ 무중단 배포 (Rolling Update)
- ✅ 실시간 모니터링 & 알림

## 📊 시스템 스펙

- 처리량: 1,000 RPS
- 응답 시간: p95 < 200ms
- 가용성: 99.9% SLA
- 동시 사용자: 10,000+

## 🔒 보안

- SSL/TLS 암호화 (ACM)
- 네트워크 정책 (Calico)
- 이미지 취약점 스캔
- Secret 관리 (K8s Secrets)

## 📚 문서

- 아키텍처 문서: ✅
- API 문서: ✅
- 운영 가이드: ✅
- 트러블슈팅: ✅
```

---

## 🚀 릴리스 프로세스

### 1. MINOR 버전 업데이트 (v0.x.0)

**조건:**
- 새로운 Phase 완료
- 주요 기능 추가
- 인프라 변경

**프로세스:**

```bash
# 1. 작업 완료 확인
git checkout develop
git pull origin develop

# 2. 문서 업데이트
# - docs/README.md 버전 히스토리 업데이트
# - CHANGELOG.md 작성

# 3. 버전 태그 생성
git tag -a v0.5.0 -m "Release v0.5.0: Application Stack 배포 완료"
git push origin v0.5.0

# 4. main 브랜치로 머지
git checkout main
git merge develop
git push origin main
```

### 2. PATCH 버전 업데이트 (v0.x.y)

**조건:**
- 문서 개선
- 버그 수정
- 마이너 업데이트

**프로세스:**

```bash
# 1. 수정사항 커밋
git checkout docs-main
git add .
git commit -m "docs: 버전 관리 가이드 추가"

# 2. 버전 태그 생성
git tag -a v0.4.2 -m "Release v0.4.2: 버전 관리 가이드 추가"
git push origin v0.4.2
```

---

## 📝 버전별 체크리스트

### v0.5.0 체크리스트 (13-Node Microservices)

**인프라:**
- [x] 13-Node 클러스터 구성
  - [x] 1 Master Node (k8s-master)
  - [x] 6 API Nodes (도메인별 분리)
  - [x] 2 Worker Nodes (Storage/AI)
  - [x] 4 Infrastructure Nodes (RabbitMQ, PostgreSQL, Redis, Monitoring)
- [x] Terraform 자동화
  - [x] VPC, EC2, S3, CloudFront, ACM
  - [x] 13개 노드 정의
- [x] Ansible 자동화
  - [x] Kubernetes 클러스터 설정
  - [x] 노드 라벨링
  - [x] Calico CNI 설치

**배포:**
- [x] ArgoCD GitOps 설정
  - [x] Application 정의
  - [x] ApplicationSet (API/Worker)
- [x] Helm Charts 구성
  - [x] API 서비스 템플릿 (6개)
  - [x] Worker 서비스 템플릿 (2개)
  - [x] values-13nodes.yaml
- [x] GitHub Actions CI/CD
  - [x] Lint & Test
  - [x] Docker Build & Push (GHCR)
  - [x] 자동 배포 트리거

**애플리케이션:**
- [x] FastAPI 서비스 스켈레톤 (6개)
  - [x] waste-api
  - [x] auth-api
  - [x] userinfo-api
  - [x] location-api
  - [x] recycle-info-api
  - [x] chat-llm-api
- [x] Health Check 엔드포인트
  - [x] Liveness Probe
  - [x] Readiness Probe
- [x] Python 포맷팅 설정
  - [x] pyproject.toml, .flake8, .pylintrc
  - [x] Black, isort, pycodestyle

**문서:**
- [x] 13-Node 아키텍처 문서
- [x] WAL + Domain 통합 설계
- [x] Database 아키텍처 분석
- [x] Worker Layer 상세 설계
- [x] 배포 가이드
- [x] 문서 재정립 (33개 삭제, 11개 이동)

### v0.6.0 체크리스트 (Worker Local SQLite WAL)

**Worker WAL 구현:**
- [ ] app/wal.py (WAL 매니저)
  - [ ] SQLite 데이터베이스 초기화
  - [ ] WAL 모드 활성화
  - [ ] Task 기록/조회/삭제 API
- [ ] workers/*.py (WAL 적용)
  - [ ] image-uploader
  - [ ] gpt5-analyzer
  - [ ] rule-retriever
  - [ ] response-generator
  - [ ] task-scheduler
- [ ] 장애 복구 로직
  - [ ] Worker 재시작 시 미완료 작업 재개
  - [ ] Exponential Backoff 재시도
  - [ ] Dead Letter Queue (DLQ)
- [ ] 모니터링
  - [ ] WAL 크기 메트릭
  - [ ] 복구 성공률 메트릭
  - [ ] Prometheus 통합

**Kubernetes 설정:**
- [ ] PersistentVolume (Worker Local Disk)
- [ ] PersistentVolumeClaim (WAL Storage)
- [ ] initContainer (WAL 복구)
- [ ] volumeMount (Worker Pods)

**테스트:**
- [ ] 단위 테스트 (WAL 매니저)
- [ ] 통합 테스트 (Worker + WAL)
- [ ] 장애 복구 시나리오 테스트
- [ ] 성능 테스트 (WAL 오버헤드)

**문서:**
- [ ] WAL 구현 가이드
- [ ] 장애 복구 절차
- [ ] 모니터링 대시보드 가이드

### v1.0.0 체크리스트 (프로덕션 릴리스)

**기능 완성도:**
- [ ] 모든 API 엔드포인트 구현
- [ ] 에러 핸들링 완료
- [ ] 입력 검증 완료
- [ ] 로깅 시스템 구축

**성능:**
- [ ] 로드 테스트 (1,000 RPS)
- [ ] 스트레스 테스트
- [ ] 메모리 누수 체크
- [ ] 데이터베이스 인덱싱

**보안:**
- [ ] 보안 감사 완료
- [ ] 취약점 스캔
- [ ] HTTPS 강제
- [ ] 인증/인가 검증

**모니터링:**
- [ ] Prometheus 메트릭 수집
- [ ] Grafana 대시보드
- [ ] 알림 규칙 설정
- [ ] 로그 수집 (ELK)

**문서:**
- [ ] API 문서 (OpenAPI)
- [ ] 운영 가이드
- [ ] 트러블슈팅 가이드
- [ ] 백업/복구 절차

**배포:**
- [ ] Blue-Green 배포 테스트
- [ ] 롤백 프로세스 검증
- [ ] 백업 전략 수립
- [ ] DR 계획 수립

---

## 🔖 태그 규칙

### Git 태그

```bash
# Annotated 태그 사용 (권장)
git tag -a v0.5.0 -m "Release v0.5.0: Application Stack 배포 완료"

# Lightweight 태그 (사용 금지)
git tag v0.5.0  # ❌
```

### 태그 메시지 형식

```
Release v{version}: {요약}

{상세 설명}

- Feature 1
- Feature 2
- Bug Fix 1

Closes #123, #456
```

### 예시

```bash
git tag -a v0.5.0 -m "Release v0.5.0: Application Stack 배포 완료

마이크로서비스 5개 배포 및 CI/CD 파이프라인 구축

- FastAPI 서비스 배포 (auth, users, waste, recycling, locations)
- Celery Workers 구성 (AI, Batch, API)
- GitHub Actions 워크플로우 5개 작성
- ArgoCD Application 5개 등록
- 서비스 간 통신 테스트 완료

Closes #15, #20, #25"
```

---

## 📊 버전 관리 도구

### 버전 확인

```bash
# 현재 버전 확인
git describe --tags --abbrev=0

# 버전 히스토리 확인
git tag -l -n1

# 특정 버전으로 체크아웃
git checkout v0.4.1
```

### 버전 비교

```bash
# 두 버전 간 차이 확인
git diff v0.4.0..v0.4.1

# 커밋 로그 확인
git log v0.4.0..v0.4.1 --oneline
```

---

## 🎯 Best Practices

1. **일관성 있는 버전 관리**
   - 모든 문서에 버전 명시
   - SemVer 규칙 준수
   - CHANGELOG.md 유지

2. **명확한 릴리스 노트**
   - 변경사항 요약
   - Breaking changes 강조
   - 마이그레이션 가이드 제공

3. **자동화**
   - CI/CD에서 버전 태그 활용
   - 릴리스 노트 자동 생성
   - 버전 검증 자동화

4. **문서화**
   - 각 버전별 체크리스트
   - 로드맵 공유
   - 의사결정 기록

---

## 📚 참고 문서

- [Semantic Versioning 2.0.0](https://semver.org/)
- [Git Tagging](https://git-scm.com/book/en/v2/Git-Basics-Tagging)
- [Keep a Changelog](https://keepachangelog.com/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

**문서 버전**: v0.4.1  
**최종 업데이트**: 2025-11-06  
**작성자**: Backend Team

