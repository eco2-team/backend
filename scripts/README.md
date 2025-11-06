# Scripts 디렉토리 구조

> Kubernetes 클러스터 관리를 위한 스크립트 모음

---

## 📁 디렉토리 구조

```
scripts/
├── cluster/          # 클러스터 빌드, 재구축, 초기화
├── deployment/       # 애플리케이션 배포
├── diagnostics/      # 진단, 검사, 모니터링
├── maintenance/      # 유지보수, 수정, 정리
├── testing/          # 테스트 관련
└── utilities/        # 유틸리티, 헬퍼
```

---

## 🔧 Cluster (클러스터 관리)

클러스터 전체 생명주기 관리

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `auto-rebuild.sh` | 클러스터 완전 재구축 (cleanup → build) | `bash cluster/auto-rebuild.sh` |
| `build-cluster.sh` | 클러스터 처음부터 구축 | `bash cluster/build-cluster.sh` |
| `quick-rebuild.sh` | 빠른 재구축 (Kubernetes만) | `bash cluster/quick-rebuild.sh` |
| `rebuild-cluster.sh` | 클러스터 재구축 | `bash cluster/rebuild-cluster.sh` |
| `reset-cluster.sh` | 클러스터 초기화 | `bash cluster/reset-cluster.sh` |
| `reset-node.sh` | 특정 노드 초기화 | `bash cluster/reset-node.sh <NODE_IP>` |

**주요 사용 시나리오**:
- 🆕 **첫 구축**: `build-cluster.sh`
- 🔄 **완전 재구축**: `auto-rebuild.sh`
- ⚡ **빠른 재시작**: `quick-rebuild.sh`

---

## 🚀 Deployment (배포)

애플리케이션 및 테스트 서버 배포

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `deploy-fastapi-test.sh` | FastAPI 테스트 서버 배포 | `bash deployment/deploy-fastapi-test.sh <MASTER_IP> ubuntu` |
| `provision.sh` | 인프라 프로비저닝 | `bash deployment/provision.sh` |

**FastAPI 테스트 서버**:
- PostgreSQL, Redis, RabbitMQ 연결 테스트
- ALB를 통한 외부 접근
- 내부 통신 검증

---

## 🔍 Diagnostics (진단)

클러스터 및 서비스 상태 진단

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| **`diagnose-postgresql.sh`** | PostgreSQL 종합 진단 (8단계) | `bash diagnostics/diagnose-postgresql.sh <MASTER_IP> ubuntu` |
| **`diagnose-redis.sh`** | Redis 종합 진단 (8단계) | `bash diagnostics/diagnose-redis.sh <MASTER_IP> ubuntu` |
| `check-cluster-health.sh` | 클러스터 전체 상태 확인 | `bash diagnostics/check-cluster-health.sh` |
| `check-etcd-health.sh` | etcd 상태 확인 | `bash diagnostics/check-etcd-health.sh` |
| `check-monitoring-status.sh` | 모니터링 상태 확인 | `bash diagnostics/check-monitoring-status.sh` |
| `diagnose-pods-remote.sh` | 원격 Pod 진단 | `bash diagnostics/diagnose-pods-remote.sh <MASTER_IP>` |
| `remote-health-check.sh` | 원격 헬스 체크 | `bash diagnostics/remote-health-check.sh <MASTER_IP>` |
| `run-diagnosis-on-master.sh` | Master 노드 진단 실행 | `bash diagnostics/run-diagnosis-on-master.sh <MASTER_IP>` |
| `verify-cluster-status.sh` | 클러스터 상태 검증 | `bash diagnostics/verify-cluster-status.sh` |

### PostgreSQL 진단 (`diagnose-postgresql.sh`)

**8단계 종합 진단**:
1. ✅ 기본 정보 수집 (Namespace, StatefulSet, Pod, Service, Secret, PVC)
2. ✅ Pod 상태 상세 분석 (Status, Events, Node 배치, Restart 횟수)
3. ✅ 리소스 사용량 (CPU/Memory, Node 리소스)
4. ✅ Storage 상태 (PVC, PV, StorageClass)
5. ✅ 연결 테스트 (psql, 데이터베이스 목록, Service DNS)
6. ✅ 로그 확인 (현재 로그, 이전 로그)
7. ✅ 문제 진단 (자동 문제 감지)
8. ✅ 진단 요약 (상태, 권장 조치)

**사용 예시**:
```bash
bash scripts/diagnostics/diagnose-postgresql.sh 52.79.238.50 ubuntu
```

**출력 예시**:
```
🟢 상태: 정상 (Running & Connectable)

연결 정보:
  Host: postgres.default.svc.cluster.local
  Port: 5432
  Database: sesacthon
  Username: admin
```

---

### Redis 진단 (`diagnose-redis.sh`)

**8단계 종합 진단**:
1. ✅ 기본 정보 수집 (Namespace, Deployment, Pod, Service, ConfigMap)
2. ✅ Pod 상태 상세 분석 (Status, Events, Node 배치, Restart 횟수)
3. ✅ 리소스 사용량 (CPU/Memory)
4. ✅ Redis 연결 및 정보 (PING, INFO, 메모리, 통계, 키 통계)
5. ✅ 읽기/쓰기 테스트 (SET/GET/DEL, Service DNS)
6. ✅ 로그 확인 (현재 로그, 이전 로그)
7. ✅ 문제 진단 (자동 문제 감지)
8. ✅ 진단 요약 (상태, 권장 조치)

**사용 예시**:
```bash
bash scripts/diagnostics/diagnose-redis.sh 52.79.238.50 ubuntu
```

**출력 예시**:
```
🟢 상태: 정상 (Running & PONG)

연결 정보:
  Host: redis.default.svc.cluster.local
  Port: 6379
  Protocol: redis://
```

---

## 🔧 Maintenance (유지보수)

클러스터 유지보수 및 문제 해결

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `cleanup.sh` | 리소스 정리 | `bash maintenance/cleanup.sh` |
| `destroy.sh` | 클러스터 삭제 | `bash maintenance/destroy.sh` |
| `destroy-with-cleanup.sh` | 완전 삭제 (AWS 리소스 포함) | `bash maintenance/destroy-with-cleanup.sh` |
| `fix-node-labels.sh` | 노드 레이블 수정 | `bash maintenance/fix-node-labels.sh <MASTER_IP> ubuntu` |
| `fix-rabbitmq-redis.sh` | RabbitMQ/Redis 수정 | `bash maintenance/fix-rabbitmq-redis.sh` |
| `fix-rabbitmq-secret.sh` | RabbitMQ Secret 수정 | `bash maintenance/fix-rabbitmq-secret.sh` |
| `switch-to-vpc-cni.sh` | VPC CNI로 전환 | `bash maintenance/switch-to-vpc-cni.sh` |

**주요 사용 시나리오**:
- 🏷️ **노드 레이블 문제**: `fix-node-labels.sh`
- 🗑️ **완전 정리**: `destroy-with-cleanup.sh`
- 🔧 **서비스 수정**: `fix-rabbitmq-redis.sh`

---

## 🧪 Testing (테스트)

테스트 관련 스크립트

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `cleanup-test-pod.sh` | 테스트 Pod 정리 | `bash testing/cleanup-test-pod.sh` |

---

## 🛠️ Utilities (유틸리티)

범용 헬퍼 스크립트

| 스크립트 | 설명 | 사용법 |
|---------|------|--------|
| `connect-ssh.sh` | SSH 연결 | `bash utilities/connect-ssh.sh <NODE_IP>` |
| `detect-changes.sh` | 변경 사항 감지 | `bash utilities/detect-changes.sh` |
| `get-instances.sh` | EC2 인스턴스 정보 조회 | `bash utilities/get-instances.sh` |

---

## 📊 스크립트 선택 가이드

### 상황별 추천 스크립트

#### 🆕 **첫 클러스터 구축**
```bash
bash scripts/cluster/build-cluster.sh
```

#### 🔍 **PostgreSQL 문제 발생 시**
```bash
# 1. 진단
bash scripts/diagnostics/diagnose-postgresql.sh <MASTER_IP> ubuntu

# 2. 노드 레이블 확인 (Pending 시)
bash scripts/maintenance/fix-node-labels.sh <MASTER_IP> ubuntu
```

#### 🔍 **Redis 문제 발생 시**
```bash
# 1. 진단
bash scripts/diagnostics/diagnose-redis.sh <MASTER_IP> ubuntu

# 2. 서비스 수정 (필요 시)
bash scripts/maintenance/fix-rabbitmq-redis.sh
```

#### 🔄 **클러스터 재구축**
```bash
# 완전 재구축 (AWS 리소스 포함)
bash scripts/cluster/auto-rebuild.sh

# 또는 빠른 재구축 (Kubernetes만)
bash scripts/cluster/quick-rebuild.sh
```

#### 🧪 **통신 테스트**
```bash
bash scripts/deployment/deploy-fastapi-test.sh <MASTER_IP> ubuntu
```

#### 🗑️ **완전 정리**
```bash
bash scripts/maintenance/destroy-with-cleanup.sh
```

---

## 🎯 빠른 참조

### PostgreSQL 진단
```bash
bash scripts/diagnostics/diagnose-postgresql.sh 52.79.238.50 ubuntu
```

### Redis 진단
```bash
bash scripts/diagnostics/diagnose-redis.sh 52.79.238.50 ubuntu
```

### 노드 레이블 수정
```bash
bash scripts/maintenance/fix-node-labels.sh 52.79.238.50 ubuntu
```

### 클러스터 전체 상태
```bash
bash scripts/diagnostics/check-cluster-health.sh
```

### FastAPI 테스트 서버
```bash
bash scripts/deployment/deploy-fastapi-test.sh 52.79.238.50 ubuntu
```

---

## 📝 참고 문서

- **PostgreSQL 문제 해결**: `docs/troubleshooting/POSTGRESQL_SCHEDULING_ERROR.md`
- **FastAPI 테스트 가이드**: `docs/testing/FASTAPI_TEST_GUIDE.md`
- **클러스터 재구축**: `docs/REBUILD_GUIDE.md`
- **전체 문서**: `docs/README.md`

---

**마지막 업데이트**: 2025-11-04

