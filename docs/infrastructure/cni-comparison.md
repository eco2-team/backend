# 🌐 CNI 플러그인 비교 및 선택

> **최종 결정**: Calico (Flannel에서 변경)  
> **날짜**: 2025-10-31  
> **이유**: 안정성 문제

## 📋 변경 이력

### 기존: Flannel

```
문제점:
❌ 불안정 (재시작 반복)
❌ CNI 브리지 충돌 (cni0)
❌ Pod 네트워크 실패
❌ CrashLoopBackOff 빈번

에러:
"cni0 already has an IP address different from 10.244.1.1/24"
```

### 변경: Calico

```
장점:
✅ 프로덕션 검증 (대규모 클러스터)
✅ 안정성 우수
✅ 네트워크 정책 지원
✅ 성능 우수
✅ Kubernetes 공식 CNI

사용:
- 대부분의 엔터프라이즈
- Google GKE, Azure AKS 기본 CNI
```

---

## 📊 CNI 비교

| CNI | 안정성 | 성능 | 네트워크 정책 | 사용 사례 |
|-----|--------|------|--------------|----------|
| **Flannel** | ⭐⭐ | ⭐⭐⭐ | ❌ | 소규모, 테스트 |
| **Calico** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ✅ | 프로덕션, 대규모 |
| **Cilium** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ | eBPF, 고성능 |
| **Weave Net** | ⭐⭐⭐ | ⭐⭐⭐ | ✅ | 간단한 설정 |

---

## ⚙️ Calico 설정

### Pod Network CIDR

```
기존 (Flannel):
pod_network_cidr: "10.244.0.0/16"

변경 (Calico):
pod_network_cidr: "192.168.0.0/16"

이유:
- Calico 기본값
- 더 넓은 IP 대역
- 대규모 클러스터 지원
```

### 설치 방법

```yaml
# Ansible playbook
- name: Calico CNI 설치
  command: kubectl apply -f https://raw.githubusercontent.com/projectcalico/calico/v3.26.4/manifests/calico.yaml

# 대기 로직
- 30초 pause
- DaemonSet 확인 (60회 재시도, 10초 간격)
- 최대 10분 대기
```

---

## 🔍 Calico 구성 요소

```
Deployment:
├─ calico-kube-controllers (1 replica)

DaemonSet:
├─ calico-node (모든 노드)

생성되는 것:
├─ CRDs (NetworkPolicy 등)
├─ ServiceAccount, RBAC
├─ ConfigMap
└─ Service
```

---

## 📈 성능 비교

### Flannel

```
구조:
- VXLAN 오버레이
- 간단한 L3 네트워크
- 상태 없음 (stateless)

성능:
- 네트워크 오버헤드: 약 5-10%
- 소규모에 적합
```

### Calico

```
구조:
- BGP 라우팅 (기본)
- IP-in-IP 또는 VXLAN (선택)
- L3 네트워크

성능:
- 네트워크 오버헤드: 약 2-5%
- 대규모 최적화
- 네트워크 정책 엔진
```

---

## 🛡️ Calico 추가 기능

### Network Policy

```yaml
# Pod 간 통신 제어
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

**Flannel**: 지원 안 함 ❌  
**Calico**: 완벽 지원 ✅

### IP Pool 관리

```bash
# IP 대역 동적 관리
kubectl get ippool

# 특정 Namespace별 IP 대역 분리 가능
```

---

## 💰 비용

```
Flannel: $0 (오픈소스)
Calico: $0 (오픈소스)

리소스 사용:
Flannel: 낮음 (메모리 ~50MB/노드)
Calico: 중간 (메모리 ~150MB/노드)

→ 비용 차이 없음
→ 리소스 차이 미미
```

---

## 🎯 결론

### 최종 선택: Calico

```
이유:
✅ 안정성 (가장 중요!)
✅ 프로덕션 검증
✅ 네트워크 정책
✅ 성능
✅ 커뮤니티 지원

적용:
- Terraform: pod_network_cidr 변경
- Ansible: Calico YAML 적용
- 테스트: 안정성 확인
```

**Calico로 안정적인 클러스터 운영!** ✅

---

**작성일**: 2025-10-31  
**상태**: ✅ 적용 완료

