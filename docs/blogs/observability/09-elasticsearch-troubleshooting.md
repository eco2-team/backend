# Elasticsearch 트러블슈팅

> ECO2 Elasticsearch 클러스터 운영 중 발생한 이슈와 해결 방법

---

## 📋 현재 클러스터 구성

| 항목 | 값 |
|------|-----|
| **버전** | 8.11.0 |
| **노드 수** | 1 (Single Node) |
| **노드 타입** | t3.large (2 vCPU, 8GB RAM) |
| **JVM Heap** | 4GB (-Xms4g -Xmx4g) |
| **Pod Limit** | 5Gi |
| **스토리지** | 100GB gp3 |
| **관리 방식** | ECK Operator 2.11.0 |

---

## 📋 목차

1. [클러스터 Health Yellow](#1-클러스터-health-yellow)
2. [노드 메모리 부족 (84%)](#2-노드-메모리-부족-84)
3. [Fluent Bit Retry 과다](#3-fluent-bit-retry-과다)
4. [ECK 예약 설정 충돌](#4-eck-예약-설정-충돌)
5. [discovery.type 설정 충돌](#5-discoverytype-설정-충돌)
6. [StorageClass 미스매치](#6-storageclass-미스매치)

---

## 1. 클러스터 Health Yellow

### 증상

```bash
$ kubectl get elasticsearch -n logging
NAME        HEALTH   NODES   VERSION   PHASE   AGE
eco2-logs   yellow   1       8.11.0    Ready   8h
```

### 원인

- **단일 노드 클러스터**에서 replica shard를 할당할 수 없음
- Elasticsearch는 기본적으로 `number_of_replicas: 1` 설정
- replica를 할당할 다른 노드가 없으므로 unassigned shard 발생

### 해결

**옵션 1: 무시 (권장 - 개발/스테이징)**

단일 노드 환경에서 yellow는 정상. 데이터 손실 위험만 인지하면 됨.

**옵션 2: replica 비활성화**

```yaml
# workloads/logging/base/stack-config-policy.yaml
apiVersion: stackconfigpolicy.k8s.elastic.co/v1alpha1
kind: StackConfigPolicy
spec:
  elasticsearch:
    indexTemplates:
      composableIndexTemplates:
        logs-template:
          template:
            settings:
              number_of_replicas: 0  # replica 비활성화
```

**옵션 3: 노드 추가 (프로덕션)**

```yaml
# workloads/logging/base/elasticsearch.yaml
spec:
  nodeSets:
  - name: default
    count: 3  # 3노드로 확장
```

### 현재 상태

- **결정**: Yellow 상태 유지 (개발 환경이므로 허용)
- **프로덕션 전환 시**: 3노드 클러스터로 확장 필요

---

## 2. 노드 메모리 부족 (84%)

### 증상

```bash
$ kubectl top node k8s-logging
NAME          CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%   
k8s-logging   123m         6%     6498Mi          84%       
```

### 원인

| 구성요소 | 메모리 사용 |
|----------|------------|
| ES JVM Heap | 4GB |
| ES 오버헤드 | ~1GB |
| Kubelet/OS | ~1GB |
| 여유 공간 | ~2GB |
| **합계** | ~8GB (t3.large 한계) |

### 영향

- GC (Garbage Collection) 빈번 발생
- 인덱싱 속도 저하
- Fluent Bit 요청 타임아웃 → retry 증가

### 해결

**옵션 1: 노드 스케일업 (권장)**

```hcl
# terraform/main.tf
module "logging" {
  instance_type = "t3.xlarge"  # 8GB → 16GB
}
```

**옵션 2: JVM Heap 축소**

```yaml
# workloads/logging/base/elasticsearch.yaml
spec:
  nodeSets:
  - name: default
    podTemplate:
      spec:
        containers:
        - name: elasticsearch
          env:
          - name: ES_JAVA_OPTS
            value: "-Xms2g -Xmx2g"  # 4GB → 2GB
          resources:
            limits:
              memory: 3Gi  # 5Gi → 3Gi
            requests:
              memory: 3Gi
```

### 현재 상태

- **노드**: t3.large (8GB) - 부족
- **권장 조치**: t3.xlarge (16GB)로 스케일업

---

## 3. Fluent Bit Retry 과다

### 증상

```log
[2025/12/17 12:43:58] [ info] flush chunk succeeded at retry 9
[2025/12/17 12:44:43] [ info] flush chunk succeeded at retry 12
[2025/12/17 12:45:24] [ info] flush chunk succeeded at retry 10
```

- 정상: retry 0~1에서 성공
- 문제: retry 9~12 → ES 응답 지연

### 원인

```
Fluent Bit → ES 요청
                ↓
          ES 메모리 84%
                ↓
          GC 발생 (Stop-the-World)
                ↓
          요청 타임아웃
                ↓
          Fluent Bit retry
```

### 해결

[2. 노드 메모리 부족](#2-노드-메모리-부족-84) 참조

### 모니터링 명령어

```bash
# Fluent Bit 로그에서 retry 확인
kubectl logs -n logging daemonset/fluent-bit --tail=100 | grep retry

# ES 클러스터 상태
kubectl get elasticsearch -n logging

# 노드 리소스
kubectl top node k8s-logging
```

---

## 4. ECK 예약 설정 충돌

### 증상

```log
java.lang.IllegalArgumentException: unknown setting [xpack.security.enabled]
```

또는

```log
java.lang.IllegalArgumentException: unknown setting [cluster.name]
```

### 원인

ECK Operator가 자동 관리하는 설정을 수동으로 지정하면 충돌 발생

**ECK 예약 설정 목록:**
- `cluster.name`
- `discovery.seed_hosts`
- `cluster.initial_master_nodes`
- `xpack.security.*`
- `network.host`
- `node.name`

### 해결

```yaml
# ❌ 잘못된 설정
spec:
  nodeSets:
  - config:
      cluster.name: my-cluster        # ECK가 관리
      xpack.security.enabled: true    # ECK가 관리

# ✅ 올바른 설정
spec:
  nodeSets:
  - config:
      # ECK 예약 설정 제거
      node.store.allow_mmap: false
```

### 커밋 이력

- `b5fe87b6` fix(eck): ECK 예약 설정 제거 (cluster.name, xpack.security.*)

---

## 5. discovery.type 설정 충돌

### 증상

```log
IllegalArgumentException: [discovery.type] is forbidden
```

### 원인

ECK 2.x에서 `discovery.type: single-node`가 deprecate됨.
단일 노드는 ECK가 자동으로 감지하여 처리.

### 해결

```yaml
# ❌ 잘못된 설정
spec:
  nodeSets:
  - config:
      discovery.type: single-node  # 제거!

# ✅ 올바른 설정
spec:
  nodeSets:
  - name: default
    count: 1  # count=1이면 ECK가 자동으로 single-node 처리
```

### 커밋 이력

- `fdb3c360` fix(elasticsearch): discovery.type 설정 제거 - ECK 호환성
- `e2d96c95` fix(elasticsearch): ECK single-node 자동 설정 충돌 해결

---

## 6. StorageClass 미스매치

### 증상

```log
pod has unbound immediate PersistentVolumeClaims
```

### 원인

존재하지 않는 StorageClass 참조

```yaml
# ❌ 잘못된 설정
spec:
  volumeClaimTemplates:
  - spec:
      storageClassName: gp3-storage  # 존재하지 않음
```

### 해결

```bash
# 사용 가능한 StorageClass 확인
kubectl get storageclass

# 올바른 이름으로 수정
```

```yaml
# ✅ 올바른 설정
spec:
  volumeClaimTemplates:
  - spec:
      storageClassName: gp3  # 실제 존재하는 이름
```

### 커밋 이력

- `e04f948d` fix(eck): StorageClass gp3-storage → gp3 수정

---

## 🔧 유용한 디버깅 명령어

### 클러스터 상태

```bash
# ES 상태 확인
kubectl get elasticsearch -n logging

# 상세 상태
kubectl describe elasticsearch eco2-logs -n logging | grep -A10 'Status:'

# ES Pod 로그
kubectl logs -n logging eco2-logs-es-default-0 -c elasticsearch --tail=100
```

### 인덱스 상태

```bash
# ES Pod 내부에서 실행
kubectl exec -it -n logging eco2-logs-es-default-0 -- \
  curl -s -k -u elastic:$ES_PASSWORD https://localhost:9200/_cat/indices?v
```

### 샤드 할당 문제

```bash
# Unassigned shards 확인
kubectl exec -it -n logging eco2-logs-es-default-0 -- \
  curl -s -k -u elastic:$ES_PASSWORD https://localhost:9200/_cat/shards?v | grep UNASSIGNED

# 할당 실패 이유
kubectl exec -it -n logging eco2-logs-es-default-0 -- \
  curl -s -k -u elastic:$ES_PASSWORD 'https://localhost:9200/_cluster/allocation/explain?pretty'
```

### 노드 리소스

```bash
# 노드 메모리/CPU
kubectl top node k8s-logging

# Pod 리소스
kubectl top pod -n logging
```

---

## 📊 권장 프로덕션 구성

| 항목 | 개발 (현재) | 프로덕션 (권장) |
|------|------------|----------------|
| **노드 수** | 1 | 3 |
| **인스턴스** | t3.large (8GB) | t3.xlarge (16GB) |
| **JVM Heap** | 4GB | 8GB |
| **Replicas** | 0 | 1 |
| **Health** | Yellow | Green |
| **스토리지** | 100GB | 500GB |

---

## 📝 관련 문서

- [01-efk-stack-setup.md](./01-efk-stack-setup.md) - EFK 스택 구축
- [07-index-lifecycle.md](./07-index-lifecycle.md) - ILM 정책
- [08-troubleshooting.md](./08-troubleshooting.md) - 일반 트러블슈팅
