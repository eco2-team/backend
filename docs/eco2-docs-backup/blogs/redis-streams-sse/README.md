# 이코에코(Eco²) Redis Streams for SSE 시리즈

> SSE 병목 해결을 위한 Redis Streams 기반 이벤트 소싱 아키텍처 도입 과정을 기록합니다.

## 시리즈 개요

Celery + RabbitMQ 기반 SSE(Server-Sent Events) 구현에서 발견된 **연결 폭발 문제**를 해결하기 위해 Redis Streams 기반 이벤트 소싱으로 전환한 과정을 다룹니다.

### 핵심 문제

```
50 VU 부하 테스트
    ↓
SSE 연결 16개
    ↓ × 21 연결/SSE (Celery Events)
RabbitMQ 341개 연결
    ↓
메모리 676Mi > 512Mi (Limit)
    ↓
503 no healthy upstream
```

### 해결 방안

```
❌ 기존: Client × RabbitMQ 연결 = 곱 폭발
✅ 변경: Client × Redis Streams 읽기 = Pod당 1개 (상수)
```

---

## 시리즈 목차

| # | 제목 | 상태 | 주요 내용 |
|---|------|------|----------|
| 0 | [아키텍처 및 마이그레이션안](./00-architecture-migration.md) | ✅ 완료 | 병목 분석, 해결 전략, 목표 아키텍처 |
| 1 | [리소스 프로비저닝](./01-provisioning.md) | ✅ 완료 | Terraform, Ansible, 3노드 클러스터 구축 |
| 2 | [선언적 배포 (GitOps)](./02-gitops-deployment.md) | ✅ 완료 | Spotahome Redis Operator, RedisFailover CR |
| 3 | [Application Layer 업데이트](./03-application-layer.md) | ✅ 완료 | Redis Streams 모듈, Worker 이벤트 발행, SSE 구독 |
| 4 | [Observability](./04-observability.md) | ✅ 완료 | ServiceMonitor, Grafana 대시보드, Alert Rules |

---

## 아키텍처 변경 요약

### Before: Celery Events (RabbitMQ)

```
┌─────────────────────────────────────────────────────────────────┐
│  Client ──SSE──→ scan-api ──→ Celery Events (RabbitMQ)          │
│                                      │                          │
│                    클라이언트 × RabbitMQ 연결 = 곱 폭발          │
└─────────────────────────────────────────────────────────────────┘
```

### After: Redis Streams

```
┌─────────────────────────────────────────────────────────────────┐
│  Client ──SSE──→ scan-api ──→ Redis Streams                     │
│                                      ▲                          │
│                              Worker ─┘                          │
│                    scan-api당 1개 연결 (상수)                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Redis 3-Node 클러스터

| 인스턴스 | 용도 | 정책 | 스토리지 |
|----------|------|------|----------|
| **auth-redis** | JWT Blacklist, OAuth State | noeviction | PVC (AOF) |
| **streams-redis** | SSE 이벤트 | noeviction | emptyDir |
| **cache-redis** | Celery Result, 도메인 캐시 | allkeys-lru | emptyDir |

---

## 기술 스택

| 구성 요소 | 기술 | 버전 |
|----------|------|------|
| Redis Operator | Spotahome Redis Operator | 3.3.1 |
| Redis | Redis (Sentinel HA) | 7.0+ |
| IaC | Terraform | 1.5+ |
| Configuration | Ansible | 2.15+ |
| GitOps | ArgoCD | 2.13+ |
| Observability | Prometheus + Grafana | - |

---

## 관련 문서

### 상세 문서 (async 시리즈)

- [#23 SSE 50 VU 병목 분석](../async/23-sse-bottleneck-analysis-50vu.md)
- [#24 Redis Streams SSE 전환](../async/24-redis-streams-sse-migration.md)
- [#25 Redis 3-Node 클러스터 프로비저닝](../async/25-redis-3node-cluster-provisioning.md)
- [#26 Spotahome Redis Operator 배포](../async/26-redis-operator-deployment.md)

### 인프라 참고

- [workloads/redis/README.md](../../../workloads/redis/README.md) - Redis 인프라 상세
- [scripts/provisioning/redis-nodes-add.md](../../../scripts/provisioning/redis-nodes-add.md) - 프로비저닝 명령어

---

## Commits & PRs

| PR | 제목 | 상태 |
|----|------|------|
| #225 | Redis 3-node Cluster + Redis Streams SSE Migration | ✅ Merged |
| #226 | Redis 3-node cluster observability | 🔄 In Review |

