# 🎯 Self-Managed Kubernetes 선택 배경

> **EKS 대신 kubeadm을 선택한 이유**  
> **날짜**: 2025-10-31

## 📋 의사결정 요약

### 최종 선택

```
✅ Self-Managed Kubernetes (kubeadm)
❌ AWS EKS
```

---

## 👨‍💻 의사결정 배경

### 팀 역량 및 도구

**우리가 가진 것:**

```
1. 엔터프라이즈 클라우드 플랫폼 개발 경험 (9개월)
   ✅ 대규모 AWS 인프라 설계 및 구축
   ✅ Kubernetes 프로덕션 운영 경험
   ✅ IaC (Terraform/Ansible) 전문성
   ✅ 엔터프라이즈급 트러블슈팅 능력
   ✅ Multi-tenant 아키텍처 설계

2. AI 도구 활용 (Cursor + Claude 4.5 Sonnet)
   ✅ Terraform 모듈 자동 생성
   ✅ Ansible Playbook 작성 (75개 작업)
   ✅ 복잡한 설정 디버깅
   ✅ 문서화 자동화 (70+ 문서)
   
   생산성:
   - Terraform 작성: 3시간 → 30분
   - Ansible 작업: 1주일 → 1일
   - 문서화: 2일 → 4시간
   → 총 개발 시간: 80% 단축

3. 코드 기반 인프라 관리
   ✅ Git으로 모든 인프라 버전 관리
   ✅ 완전 자동화 (./scripts/auto-rebuild.sh)
   ✅ 재현 가능한 배포 (40-50분)
   ✅ 코드 리뷰 가능
```

**이것이 가능한 이유:**

```
Self-Managed K8s = 복잡도 ↑

하지만,
+ 클라우드 경험
+ AI 도구 (Claude 4.5 MAX)
+ IaC 자동화
━━━━━━━━━━━━━━━━━━━━━
= 관리 가능한 복잡도

EKS의 편의성 < 역량
→ Self-Managed 선택이 합리적!
```

### 실무 적용 사례

```
9개월 엔터프라이즈 경험 활용:
1. 클라우드 인프라 설계
   - Multi-AZ 고가용성 아키텍처
   - VPC, Security Groups, IAM 정책
   - 모범 사례 기반 설계
   
2. Kubernetes 운영 노하우
   - CNI 선택 및 최적화 (Calico VXLAN)
   - StatefulSet 운영 (PostgreSQL, RabbitMQ)
   - Resource 관리 및 Auto Scaling
   
3. IaC 전문성
   - Terraform 모듈화 및 재사용
   - Ansible Playbook 75개 작업 자동화
   - Git 기반 인프라 관리
   
4. AI 도구 활용 시너지
   - 경험 + AI = 최적 조합
   - 복잡한 문제 20-40분 내 해결
   - 문서화 및 자동화 가속화

평균 해결 시간:
- 경험 없이 AI만: 1-2시간 (시행착오)
- 경험 + AI 도구: 20-40분
→ 엔터프라이즈 경험이 핵심!
```

---

## 💰 비용 비교

### EKS

```
Control Plane: $73/월 (고정)
Worker Nodes: $238/월 (13-node 동일 구성)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총: $311/월

장점:
✅ 관리형 Control Plane
✅ 자동 업그레이드
✅ AWS 통합
✅ 고가용성 내장

단점:
⚠️ 비용 높음 (+$73/월)
⚠️ 학습 기회 적음
⚠️ 커스터마이징 제한
```

### Self-Managed (선택) - 13-Node 최적화

```
13-Node 구성 (v0.6.0):
- Master: 1 × t3.large (2 vCPU) = $60
- API: 6 × t3.micro/small (1 vCPU) = $58
- Worker: 2 × t3.small (1 vCPU) = $30
- Infra: 4 × t3.small/medium (1-2 vCPU) = $90
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
총: $238/월

vCPU: 15 (16 한도 내)
메모리: 38GB

장점:
✅ 비용 절감 (-$73/월, 23% 절감)
✅ 완전한 제어
✅ 깊은 학습 기회
✅ 커스터마이징 자유
✅ 13-Node 마이크로서비스 아키텍처
✅ WAL 패턴 구현

단점:
⚠️ 수동 관리 필요
⚠️ 업그레이드 직접 수행
⚠️ HA 직접 구성
```

---

## 🎓 학습 목적

### 해커톤

```
우리 상황:
- SeSAC 해커톤
- Kubernetes 깊이 이해 필요
- 팀 역량 향상

Self-Managed로 얻는 것:
✅ kubeadm 마스터
✅ etcd 직접 관리
✅ CNI 선택 및 설정 (Calico VXLAN)
✅ Control Plane 트러블슈팅
✅ 보안 그룹 설계
✅ 네트워크 디버깅
✅ 엔터프라이즈 노하우 적용

→ 9개월 실무 경험 + 프로젝트 경험
→ Kubernetes 전문성 심화
```

---

## ⚙️ 기술적 이유

### 1. 완전한 제어

```
kubeadm:
- Control Plane 접근 가능
- etcd 직접 관리
- API Server 설정 변경
- Scheduler 정책 조정
- 모든 로그 접근

EKS:
- Control Plane 블랙박스
- 제한된 설정만 가능
- AWS 정책 따라야 함
```

### 2. 커스터마이징

```
우리가 한 것:
✅ Calico VXLAN (BGP 완전 비활성화)
✅ control-plane-endpoint (HA 준비)
✅ kubeadm init phase addon (kube-proxy)
✅ etcd 백업 자동화
✅ block/rescue 에러 처리
✅ 엔터프라이즈 모범 사례 적용

EKS였다면:
→ 대부분 불가능하거나 제한적
```

### 3. 문제 해결 능력 향상

```
엔터프라이즈 경험으로 해결:
- Multi-AZ 네트워킹 설계
- Calico CNI 최적화 (VXLAN)
- StatefulSet HA 구성
- Security Groups 설계
- ALB Controller 통합
- etcd 백업 전략
- Resource 최적화
- Monitoring & Alerting

EKS:
→ 대부분 추상화 (깊은 이해 불가)
```

---

## 🎯 13-Node Microservices Architecture 진화

### 진화 과정

```
Phase 1: 초기 설계 (3-node)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Master + Worker 2개
모든 서비스 혼재
비용: $105/월

문제:
❌ 리소스 경합
❌ 역할 불명확
❌ 확장성 제한

Phase 2: 스펙 최적화 (3-node, t3.large)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모든 노드 t3.large (8GB)
Prometheus 안정성 확보
비용: $240/월

문제:
⚠️ 비용 증가
⚠️ 과도한 스펙 (일부)

Phase 3: Instagram 패턴 적용 (4-node)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
역할별 노드 분리:
1. Master (Control + Monitor)
2. Worker-1 (Application)
3. Worker-2 (Async Workers)
4. Storage (Stateful)

비용: $180/월

Phase 4: 13-Node Microservices (최종) ⭐⭐⭐
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API 도메인별 분리 + WAL 패턴:
1. Master (Control Plane)
2. API × 6 (도메인별 독립)
3. Worker × 2 (Storage, AI)
4. Infrastructure × 4 (RabbitMQ, PostgreSQL, Redis, Monitoring)

비용: $238/월 (최적화)
vCPU: 15 (16 한도 내)
```

### 최종 13-Node 아키텍처

```
Tier 1: Control Plane (Master)
- kube-apiserver, scheduler, controller
- etcd
- 고가용성 준비

Tier 2: API Layer (6 nodes)
- Waste Analysis API
- Auth API
- Userinfo API
- Location API
- Recycle-Info API
- Chat-LLM API
→ 도메인별 독립 스케일링

Tier 3: Worker Layer (2 nodes)
- Storage Worker (S3 업로드)
- AI Worker (이미지 분석, LLM)
→ 로컬 SQLite WAL + PostgreSQL 동기화

Tier 4: Infrastructure (4 nodes)
- RabbitMQ (메시지 큐)
- PostgreSQL (중앙 DB, 스키마 분리)
- Redis (캐시/세션)
- Monitoring (Prometheus + Grafana)

장점:
✅ 명확한 역할 분리 (Robin 패턴)
✅ 도메인별 독립 스케일링
✅ WAL 패턴으로 성능 최적화
✅ 비용 최적화 (15 vCPU)
✅ 프로덕션 준비
```

---

## 📚 참고한 패턴

### Instagram Engineering

```
초기:
- Redis + Celery
- 비동기 처리 분리
- Worker Pool 전략

적용:
✅ Celery Worker 독립 Deployment
✅ Queue 우선순위 분리
✅ Worker 노드 분리
```

### Robin Storage

```
특징:
- Storage 격리
- Control Plane 안정성
- Stateful 서비스 별도 관리

적용:
✅ Storage 전용 노드
✅ RabbitMQ, PostgreSQL 격리
✅ etcd 백업 자동화
```

---

## 🎯 결과

### 달성한 것

```
✅ 비용 효율: $238/월 (EKS 대비 23% 절감)
✅ 학습 경험: 13-Node 마이크로서비스 아키텍처 구현
✅ 프로덕션급: 모범 사례 적용
✅ 확장 가능: 명확한 아키텍처
✅ 문서화: 70+ 문서
✅ 자동화: 12개 스크립트
✅ WAL 패턴: Worker Local SQLite + PostgreSQL 동기화

기술 역량:
- Kubernetes 내부 구조 이해
- 네트워크 디버깅 능력
- Infrastructure as Code 활용
- 프로덕션 운영 경험
- 마이크로서비스 설계
```

---

## 💡 언제 EKS로 전환?

```
전환 시점:
- 규모: 노드 20개 이상
- 팀: 운영팀 없음
- 비용: 관리 비용 > $73/월
- 요구사항: 99.95% SLA

현재는:
→ Self-Managed가 최적 ✅
→ 학습 + 비용 + 제어
```

---

**작성일**: 2025-10-31  
**결정**: Self-Managed Kubernetes (kubeadm)  
**비용**: $238/월 (13-Node 최적화, EKS 대비 -$73/월)

