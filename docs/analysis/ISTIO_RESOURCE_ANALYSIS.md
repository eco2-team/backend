# Istio 도입 리소스 분석

## 현재 클러스터 스펙

| 노드 | 인스턴스 타입 | vCPU | 메모리 | 역할 |
|------|-------------|------|--------|------|
| **Master** | t3.large | 2 | 8GB | Control Plane, Prometheus, ArgoCD |
| **Worker-1** | t3.medium | 2 | 4GB | FastAPI (Sync API) |
| **Worker-2** | t3.medium | 2 | 4GB | Celery Workers (Async) |
| **Storage** | t3.large | 2 | 8GB | RabbitMQ, Redis, PostgreSQL |
| **합계** | - | **8 cores** | **24GB** | - |

## 현재 배포된 애플리케이션 리소스

### Master 노드
- **Kubernetes Control Plane**: ~500m CPU, ~1.5GB 메모리 (예상)
- **Prometheus**: ~500m CPU, ~2GB 메모리 (retention 7d 기준)
- **Grafana**: ~100m CPU, ~500MB 메모리
- **ArgoCD**: ~200m CPU, ~500MB 메모리
- **시스템 오버헤드**: ~200m CPU, ~1GB 메모리
- **예상 사용량**: ~1.5 CPU, ~5.5GB 메모리 / **여유**: ~0.5 CPU, ~2.5GB 메모리

### Worker-1 노드 (FastAPI Pods)
- **애플리케이션 Pods**: 미확정 (FastAPI Pods 예상)
- **시스템 오버헤드**: ~200m CPU, ~500MB 메모리
- **예상 사용량**: ~1 CPU, ~2GB 메모리 / **여유**: ~1 CPU, ~2GB 메모리

### Worker-2 노드 (Celery Workers)
- **Celery Worker Pods**: 미확정
- **시스템 오버헤드**: ~200m CPU, ~500MB 메모리
- **예상 사용량**: ~1 CPU, ~2GB 메모리 / **여유**: ~1 CPU, ~2GB 메모리

### Storage 노드
- **RabbitMQ**: 500m CPU, 1GB 메모리 (request) / 2000m CPU, 2GB 메모리 (limit)
- **Redis**: 200m CPU, 1GB 메모리 (request) / 1000m CPU, 2GB 메모리 (limit)
- **PostgreSQL**: 미확정 (예상 500m CPU, 1GB 메모리)
- **시스템 오버헤드**: ~200m CPU, ~500MB 메모리
- **예상 사용량**: ~1.4 CPU, ~3.5GB 메모리 / **여유**: ~0.6 CPU, ~4.5GB 메모리

## Istio 리소스 요구사항

### Control Plane (istiod)
- **CPU**: 500m-1000m (일반), 2000m+ (대규모)
- **메모리**: 1GB-2GB (일반), 4GB+ (대규모)
- **배치**: Master 노드 또는 별도 네임스페이스 (모든 노드 접근 가능)

### Data Plane (Envoy Sidecar)
각 Pod마다 추가되는 리소스:
- **CPU**: 50m-100m (일반), 200m+ (고부하)
- **메모리**: 50MB-150MB (일반), 500MB+ (고부하)

## 시나리오별 리소스 분석

### 시나리오 1: 전체 Istio 주입 (권장하지 않음)
모든 Pod에 Sidecar 주입:
- Control Plane: 1000m CPU, 2GB 메모리 (Master)
- Sidecar × N Pods: 50m-100m CPU, 50-150MB 메모리 per Pod

**예상 Pod 수**:
- Master: ~10 Pods (Prometheus, Grafana, ArgoCD 등)
- Worker-1: ~5-10 Pods (FastAPI)
- Worker-2: ~5-10 Pods (Celery)
- Storage: ~3-5 Pods (RabbitMQ, Redis, PostgreSQL)

**총 예상 Sidecar 리소스** (25 Pods 기준):
- CPU: 25 × 75m = ~1.875 CPU
- 메모리: 25 × 100MB = ~2.5GB

### 시나리오 2: 선택적 주입 (권장)
애플리케이션 Pod만 주입, 시스템 Pod 제외:
- Worker-1 FastAPI Pods만 주입: ~5-10 Sidecars
- Worker-2 Celery Pods만 주입: ~5-10 Sidecars

**총 예상 Sidecar 리소스** (15 Pods 기준):
- CPU: 15 × 75m = ~1.125 CPU
- 메모리: 15 × 100MB = ~1.5GB

## 리소스 여유 분석

### Master 노드
- **현재 여유**: ~0.5 CPU, ~2.5GB 메모리
- **Istio Control Plane**: 1000m CPU, 2GB 메모리
- **결과**: ⚠️ **부족!** Control Plane만 추가해도 메모리 부족 가능성

### Worker-1 노드
- **현재 여유**: ~1 CPU, ~2GB 메모리
- **Sidecar (5-10 Pods)**: ~0.5-1 CPU, ~0.5-1GB 메모리
- **결과**: ✅ **가능하지만 여유 없음**

### Worker-2 노드
- **현재 여유**: ~1 CPU, ~2GB 메모리
- **Sidecar (5-10 Pods)**: ~0.5-1 CPU, ~0.5-1GB 메모리
- **결과**: ✅ **가능하지만 여유 없음**

### Storage 노드
- **현재 여유**: ~0.6 CPU, ~4.5GB 메모리
- **Sidecar (3 Pods)**: ~0.225 CPU, ~300MB 메모리
- **결과**: ✅ **가능**

## 권장사항

### ❌ **현재 스펙에서는 Istio 도입 비권장**

이유:
1. **Master 노드 리소스 부족**: Control Plane만 추가해도 메모리 한계
2. **Worker 노드 여유 부족**: Sidecar 추가 시 리소스 경쟁 심화
3. **성능 영향**: t3.medium 노드의 경우 CPU 버스트 제한으로 지연 증가 가능

### ✅ **대안 1: 리소스 업그레이드 후 도입**
```
Master: t3.large → t3.xlarge (4 vCPU, 16GB) +$60/월
Worker-1: t3.medium → t3.large (2 vCPU, 8GB) +$30/월
Worker-2: t3.medium → t3.large (2 vCPU, 8GB) +$30/월
Storage: t3.large 유지

총 추가 비용: +$120/월 (총 $305/월)
```

### ✅ **대안 2: 경량 서비스 메시 사용 (Linkerd)**
- **리소스**: Control Plane ~200m CPU, 300MB 메모리
- **Sidecar**: Pod당 ~50m CPU, 50MB 메모리
- **현재 스펙에서 가능**: ⚠️ 여전히 Master 노드 여유 부족 가능성

### ✅ **대안 3: 단계적 도입**
1. **현재**: Ingress Controller로 트래픽 관리 (이미 설치됨)
2. **Phase 1**: 애플리케이션만 선택적 주입 (Worker 노드만)
3. **Phase 2**: 리소스 업그레이드 후 전체 도입

### ✅ **대안 4: Istio Lite 모드**
- **minimal profile**: 최소 리소스로 설치
- **Control Plane**: ~500m CPU, 1GB 메모리
- **Sidecar**: Pod당 ~50m CPU, 50MB 메모리
- **현재 스펙에서 가능**: ⚠️ Master 노드 여유 부족 가능성 여전

## 결론 및 권장사항

### 현재 스펙 기준
- **Istio 도입**: ⚠️ **비권장** (Master 노드 리소스 부족)
- **대안 검토 필요**: Linkerd 또는 리소스 업그레이드

### 최소 요구사항 (Istio 도입 시)
- Master: t3.xlarge (16GB) 또는 Control Plane 전용 노드
- Worker: t3.large (8GB) 권장 (최소 t3.medium 유지 가능하나 여유 부족)

### 단기 권장사항
1. **현재 상태 유지**: Ingress Controller로 충분히 트래픽 관리 가능
2. **모니터링 강화**: Prometheus + Grafana로 충분
3. **리소스 업그레이드 후 도입**: 비즈니스 요구사항 명확화 후 결정

### 장기 고려사항
- 서비스 메시 필요성 검토 (mTLS, 트래픽 분할, 캐싱 등)
- 리소스 업그레이드 vs EKS 전환 비교
- Istio vs Linkerd 성능/리소스 비교

## 참고 자료
- [Istio Performance and Scalability](https://istio.io/latest/docs/ops/deployment/performance-and-scalability/)
- [Linkerd Resource Requirements](https://linkerd.io/2.14/tasks/install-helm/#resource-usage)
