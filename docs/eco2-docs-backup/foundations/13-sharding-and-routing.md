# Sharding & Routing: 분산 데이터 파티셔닝과 라우팅

> [← 인덱스](./00-index.md) | [← 12. Consensus Algorithms](./12-consensus-algorithms.md)

> 분산 시스템에서 데이터를 여러 노드에 분산(Sharding)하고,
> 요청을 올바른 노드로 라우팅(Routing)하는 기술.
> Eco²에서는 Redis Streams 샤딩과 Istio Consistent Hash를 사용합니다.

---

## 공식 자료 (1차 지식생산자)

### 핵심 논문

| 논문 | 저자 | 발표 | 핵심 내용 |
|------|------|------|---------|
| **[Consistent Hashing and Random Trees](https://www.cs.princeton.edu/courses/archive/fall09/cos518/papers/chash.pdf)** | Karger et al. (MIT) | STOC 1997 | Consistent Hashing 원본 논문 |
| **[Dynamo: Amazon's Highly Available Key-value Store](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf)** | DeCandia et al. | SOSP 2007 | Virtual Nodes, Quorum, 실제 적용 |
| **[Jump Consistent Hash](https://arxiv.org/abs/1406.2294)** | Lamping, Veach (Google) | 2014 | O(1) 메모리, 균등 분포 |
| **[The Tail at Scale](https://research.google/pubs/pub40801/)** | Jeff Dean, Luiz Barroso | CACM 2013 | Fanout 시스템 지연 시간 문제 |

### 공식 문서

| 기술 | 문서 | 핵심 내용 |
|------|------|---------|
| **Redis Streams** | [redis.io/docs/data-types/streams](https://redis.io/docs/latest/develop/data-types/streams/) | Consumer Groups, XREADGROUP |
| **Redis XREADGROUP** | [redis.io/commands/xreadgroup](https://redis.io/docs/latest/commands/xreadgroup/) | Consumer Group 읽기 명령어 |
| **Envoy Ring Hash LB** | [envoyproxy.io](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers#ring-hash) | Ketama 알고리즘 |
| **Istio Destination Rule** | [istio.io](https://istio.io/latest/docs/reference/config/networking/destination-rule/#LoadBalancerSettings-ConsistentHashLB) | consistentHash 설정 |
| **Kafka Consumer Group** | [kafka.apache.org](https://kafka.apache.org/documentation/#consumerconfigs_partition.assignment.strategy) | Partition Assignment 전략 |

### 참고 서적

| 자료 | 저자 | 핵심 내용 |
|------|------|---------|
| **[The Log](https://engineering.linkedin.com/distributed-systems/log-what-every-software-engineer-should-know-about-real-time-datas-unifying)** | Jay Kreps (LinkedIn) | Log-based 메시징의 이론적 기초 |
| **Designing Data-Intensive Applications** | Martin Kleppmann | Ch.6 Partitioning - 샤딩, 리밸런싱, 라우팅 |

---

## 1. Consistent Hashing (일관된 해싱)

> Karger et al. (MIT, 1997)
> "노드 추가/제거 시 최소한의 데이터만 재배치"

### 1.1 기본 개념

```
┌─────────────────────────────────────────────────────────────────┐
│                    Consistent Hashing의 필요성                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  문제: 단순 해시 (hash(key) % N)                                │
│  ───────────────────────────────                                │
│  • N=4 → N=5로 노드 추가 시                                     │
│  • 대부분의 키가 다른 노드로 재배치됨                            │
│  • 캐시 미스 폭발, 성능 저하                                    │
│                                                                  │
│  해결: Consistent Hashing                                       │
│  ─────────────────────────                                       │
│  • 해시 공간을 원(Ring)으로 표현                                │
│  • 노드 추가/제거 시 인접한 키만 재배치                          │
│  • 평균 K/N개의 키만 이동 (K=총 키 수, N=노드 수)                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 해시 링 (Hash Ring)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hash Ring 구조                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                         0 (= 2^32)                              │
│                           ●                                      │
│                      ╱         ╲                                │
│                   ╱               ╲                             │
│                ●                     ●                          │
│             Node A                  Node B                      │
│            (hash=0.25)             (hash=0.5)                   │
│               │                       │                         │
│               │   ← key1 (0.3)        │                         │
│               │   ← key2 (0.35)       │                         │
│               │                       │   ← key3 (0.6)          │
│               │                       │   ← key4 (0.7)          │
│                ╲                     ╱                          │
│                   ╲               ╱                             │
│                      ╲         ╱                                │
│                           ●                                      │
│                        Node C                                   │
│                       (hash=0.75)                               │
│                           │                                      │
│                           │   ← key5 (0.8)                      │
│                           │   ← key6 (0.9)                      │
│                                                                  │
│  규칙: 키는 시계방향으로 가장 가까운 노드에 저장                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 Virtual Nodes (가상 노드)

> Amazon Dynamo (2007)에서 도입

```
┌─────────────────────────────────────────────────────────────────┐
│                    Virtual Nodes                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  문제: 물리 노드만 사용 시                                       │
│  ─────────────────────────                                       │
│  • 노드 간 부하 불균형 (해시 분포에 따라)                        │
│  • 노드 장애 시 하나의 노드가 모든 부하를 받음                   │
│                                                                  │
│  해결: Virtual Nodes (VNodes)                                   │
│  ───────────────────────────                                     │
│  • 각 물리 노드를 여러 가상 노드로 표현                          │
│  • 링에 더 균등하게 분포                                        │
│                                                                  │
│           0                                                      │
│           ●                                                      │
│      A1 ●   ● B1                                                │
│                                                                  │
│    C2 ●         ● A2                                            │
│                                                                  │
│      B2 ●   ● C1                                                │
│           ●                                                      │
│          A3                                                      │
│                                                                  │
│  Node A → {A1, A2, A3} (3개의 가상 노드)                        │
│  Node B → {B1, B2}                                              │
│  Node C → {C1, C2}                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 노드 추가/제거

```
┌─────────────────────────────────────────────────────────────────┐
│                    노드 추가 시 재배치                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Before: Node A, B, C                                           │
│                                                                  │
│       ┌────────┐       ┌────────┐       ┌────────┐             │
│       │ Node A │       │ Node B │       │ Node C │             │
│       │ keys:  │       │ keys:  │       │ keys:  │             │
│       │ 1,2,3  │       │ 4,5,6  │       │ 7,8,9  │             │
│       └────────┘       └────────┘       └────────┘             │
│                                                                  │
│  After: Node D 추가 (A와 B 사이)                                │
│                                                                  │
│       ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐          │
│       │ Node A │  │ Node D │  │ Node B │  │ Node C │          │
│       │ keys:  │  │ keys:  │  │ keys:  │  │ keys:  │          │
│       │ 1,2    │  │ 3      │  │ 4,5,6  │  │ 7,8,9  │          │
│       └────────┘  └────────┘  └────────┘  └────────┘          │
│            │           ▲                                        │
│            └───────────┘                                        │
│           key 3만 이동 (1개/9개 = 11%)                          │
│                                                                  │
│  단순 해시 (hash % N):                                          │
│  • N=3 → N=4 변경 시 대부분의 키 재배치 (약 75%)                │
│                                                                  │
│  Consistent Hashing:                                            │
│  • 평균 K/N개만 재배치 (K=총 키 수)                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.5 구현 예시

```python
import hashlib
from bisect import bisect_right

class ConsistentHash:
    def __init__(self, nodes: list[str], virtual_nodes: int = 150):
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []
        self.virtual_nodes = virtual_nodes
        
        for node in nodes:
            self.add_node(node)
    
    def _hash(self, key: str) -> int:
        """MD5 해시를 정수로 변환"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def add_node(self, node: str) -> None:
        """노드 추가 (가상 노드 포함)"""
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_val = self._hash(virtual_key)
            self.ring[hash_val] = node
            self.sorted_keys.append(hash_val)
        self.sorted_keys.sort()
    
    def remove_node(self, node: str) -> None:
        """노드 제거"""
        for i in range(self.virtual_nodes):
            virtual_key = f"{node}:{i}"
            hash_val = self._hash(virtual_key)
            del self.ring[hash_val]
            self.sorted_keys.remove(hash_val)
    
    def get_node(self, key: str) -> str:
        """키가 속한 노드 반환"""
        if not self.ring:
            raise ValueError("No nodes available")
        
        hash_val = self._hash(key)
        idx = bisect_right(self.sorted_keys, hash_val)
        
        # 링의 끝을 넘어가면 처음으로
        if idx == len(self.sorted_keys):
            idx = 0
        
        return self.ring[self.sorted_keys[idx]]


# 사용 예시
ch = ConsistentHash(["shard-0", "shard-1", "shard-2", "shard-3"])
shard = ch.get_node("job_id_abc123")  # → "shard-2"
```

---

## 2. Redis Streams Consumer Groups

> Redis 5.0+ (2018)
> Kafka Consumer Group의 Redis 버전

### 2.1 Consumer Group 개념

```
┌─────────────────────────────────────────────────────────────────┐
│                    Consumer Group 구조                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Stream: scan:events                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  1-0  │  2-0  │  3-0  │  4-0  │  5-0  │  6-0  │ ...    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                          │                                       │
│                          ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Consumer Group: sse-consumers                           │   │
│  │                                                          │   │
│  │  last_delivered_id: 4-0                                  │   │
│  │                                                          │   │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐        │   │
│  │  │ Consumer A │  │ Consumer B │  │ Consumer C │        │   │
│  │  │ pending:   │  │ pending:   │  │ pending:   │        │   │
│  │  │ [1-0, 2-0] │  │ [3-0]      │  │ [4-0]      │        │   │
│  │  └────────────┘  └────────────┘  └────────────┘        │   │
│  │                                                          │   │
│  │  PEL (Pending Entry List):                               │   │
│  │  • 1-0 → Consumer A (delivered, not ACKed)              │   │
│  │  • 2-0 → Consumer A                                      │   │
│  │  • 3-0 → Consumer B                                      │   │
│  │  • 4-0 → Consumer C                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 명령어

```redis
# Consumer Group 생성
XGROUP CREATE scan:events sse-consumers $ MKSTREAM

# Consumer Group으로 읽기 (미전달 항목만)
XREADGROUP GROUP sse-consumers consumer-a 
    COUNT 10 BLOCK 5000 
    STREAMS scan:events >

# 특수 ID:
#   > : 아직 전달되지 않은 새 메시지만
#   0 : 내 pending 목록의 처음부터

# 처리 완료 확인
XACK scan:events sse-consumers 1735123456789-0

# Pending 목록 조회
XPENDING scan:events sse-consumers

# 오래된 pending 항목 다른 consumer에게 재할당
XCLAIM scan:events sse-consumers consumer-b 60000 1735123456789-0
```

### 2.3 Kafka vs Redis Streams 비교

```
┌─────────────────────────────────────────────────────────────────┐
│                    Kafka vs Redis Streams                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  특성              │ Kafka                │ Redis Streams        │
│  ──────────────────┼──────────────────────┼────────────────────  │
│  파티셔닝          │ Topic → Partitions   │ 단일 Stream          │
│                    │ (수평 확장)          │ (Cluster로 샤딩)     │
│                    │                      │                      │
│  Consumer 할당     │ 자동 리밸런싱        │ 수동 (XREADGROUP)    │
│                    │ Coordinator가 관리   │ 앱에서 직접 관리     │
│                    │                      │                      │
│  Partition:Consumer│ 1:1 (한 파티션은     │ N:M (한 메시지는     │
│                    │ 한 consumer만)       │ 한 consumer만)       │
│                    │                      │                      │
│  리밸런싱          │ CooperativeSticky    │ 없음 (수동 구현)     │
│                    │ (KIP-429)            │                      │
│                    │                      │                      │
│  Offset 관리       │ Consumer Group       │ PEL (Pending Entry   │
│                    │ Offset               │ List)                │
│                    │                      │                      │
│  메시지 순서       │ 파티션 내 보장       │ Stream 내 보장       │
│                    │                      │                      │
│  적합 용도         │ 대용량 이벤트        │ 실시간 이벤트        │
│                    │ 스트리밍             │ 소규모~중규모        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 Redis Streams의 한계: 자동 리밸런싱 없음

```
┌─────────────────────────────────────────────────────────────────┐
│  Kafka: 자동 리밸런싱                                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Consumer 추가 시:                                              │
│  ┌────────┐  ┌────────┐       ┌────────┐  ┌────────┐  ┌────┐ │
│  │  P0    │  │  P1    │   →   │  P0    │  │  P1    │  │ P2 │ │
│  │  C1    │  │  C1    │       │  C1    │  │  C2    │  │ C2 │ │
│  └────────┘  └────────┘       └────────┘  └────────┘  └────┘ │
│                                                                  │
│  Coordinator가 자동으로 파티션을 재할당                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Redis Streams: 수동 관리 필요                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Consumer 추가 시:                                              │
│  • 기존 Consumer들이 읽는 Stream에 변화 없음                    │
│  • 새 Consumer는 새 메시지만 받음                               │
│  • 부하 분산을 위해 앱에서 직접 로직 구현 필요                  │
│                                                                  │
│  해결책:                                                         │
│  1) 여러 Stream으로 수동 샤딩 (scan:events:0, scan:events:1)    │
│  2) 앱에서 shard ↔ consumer 할당 로직 구현                      │
│  3) 외부 coordinator (Kubernetes Lease 등) 사용                 │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Service Mesh Consistent Hash Routing

> Envoy Proxy의 Ring Hash LB를 Istio에서 활용
> 특정 키(header, cookie, query param)를 기준으로 동일한 Pod로 라우팅

### 3.1 Envoy Ring Hash LB

```
┌─────────────────────────────────────────────────────────────────┐
│                    Envoy Ring Hash LB                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  알고리즘: Ketama (Consistent Hashing 구현체)                   │
│                                                                  │
│  동작 원리:                                                      │
│  1. 각 upstream host를 해시 링에 배치                           │
│  2. 요청의 hash key (header, cookie 등)를 해시                  │
│  3. 링에서 시계방향으로 가장 가까운 host 선택                   │
│                                                                  │
│          Hash Ring                                               │
│              ●                                                   │
│         ╱         ╲                                             │
│       ●             ●                                           │
│    pod-0          pod-1                                         │
│       │             │                                            │
│       │  ← job_id=abc (hash=0.3)                                │
│       │                                                          │
│       ●             ●                                           │
│    pod-3          pod-2                                         │
│         ╲         ╱                                             │
│              ●                                                   │
│                                                                  │
│  → job_id=abc 요청은 항상 pod-0으로 라우팅                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Istio DestinationRule 설정

```yaml
# Istio DestinationRule: job_id 기반 Consistent Hash
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: sse-gateway-consistent-hash
  namespace: sse-consumer
spec:
  host: sse-gateway.sse-consumer.svc.cluster.local
  trafficPolicy:
    loadBalancer:
      consistentHash:
        # 옵션 1: Query Parameter 기반
        httpQueryParameterName: "job_id"
        
        # 옵션 2: Header 기반
        # httpHeaderName: "x-job-id"
        
        # 옵션 3: Cookie 기반
        # httpCookie:
        #   name: "session-id"
        #   ttl: 3600s

    connectionPool:
      http:
        h2UpgradePolicy: UPGRADE  # SSE를 위한 HTTP/2
```

### 3.3 Ring Hash 설정 튜닝

```yaml
# Envoy 직접 설정 시 (Istio EnvoyFilter)
apiVersion: networking.istio.io/v1alpha3
kind: EnvoyFilter
metadata:
  name: sse-gateway-ring-hash-config
  namespace: sse-consumer
spec:
  workloadSelector:
    labels:
      app: sse-gateway
  configPatches:
  - applyTo: CLUSTER
    match:
      context: SIDECAR_OUTBOUND
      cluster:
        name: "outbound|80||sse-gateway.sse-consumer.svc.cluster.local"
    patch:
      operation: MERGE
      value:
        lb_policy: RING_HASH
        ring_hash_lb_config:
          minimum_ring_size: 1024    # 링 크기 (균등 분포)
          maximum_ring_size: 8388608 # 최대 링 크기
          hash_function: XX_HASH     # 해시 함수 (기본: XX_HASH)
```

### 3.4 Consistent Hash의 한계

```
┌─────────────────────────────────────────────────────────────────┐
│                    Consistent Hash Routing 한계                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Pod 추가/제거 시 일부 키 재배치                             │
│     • Consistent Hash라도 약간의 재배치는 발생                  │
│     • 기존 SSE 연결이 끊길 수 있음                              │
│                                                                  │
│  2. Pod가 없을 때 요청 실패                                     │
│     • 특정 shard 담당 Pod가 모두 죽으면 해당 키 요청 실패       │
│                                                                  │
│  3. 불균등 부하                                                  │
│     • 특정 job_id가 많은 요청을 받으면 해당 Pod에 부하 집중     │
│     • Virtual Nodes로 완화 가능하지만 완벽하지 않음             │
│                                                                  │
│  해결책:                                                         │
│  • Pod 수를 shard 수보다 많게 유지                              │
│  • Fallback: 담당 Pod 없으면 다른 Pod로 라우팅                  │
│  • HPA: 부하에 따라 Pod 자동 확장                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Pub/Sub Fanout 패턴

> 하나의 메시지를 여러 수신자에게 전달하는 패턴

### 4.1 Fan-in / Fan-out 개념

```
┌─────────────────────────────────────────────────────────────────┐
│                    Fan-in / Fan-out                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Fan-in (수집):                                                 │
│  ─────────────                                                   │
│  ┌────────┐                                                      │
│  │ Source │──┐                                                  │
│  └────────┘  │                                                  │
│  ┌────────┐  │    ┌───────────┐                                │
│  │ Source │──┼───▶│ Aggregator│                                │
│  └────────┘  │    └───────────┘                                │
│  ┌────────┐  │                                                  │
│  │ Source │──┘                                                  │
│  └────────┘                                                      │
│                                                                  │
│  Fan-out (분배):                                                │
│  ──────────────                                                  │
│                     ┌────────┐                                  │
│               ┌────▶│  Sink  │                                  │
│  ┌─────────┐  │     └────────┘                                  │
│  │ Source  │──┼────▶┌────────┐                                  │
│  └─────────┘  │     │  Sink  │                                  │
│               │     └────────┘                                  │
│               └────▶┌────────┐                                  │
│                     │  Sink  │                                  │
│                     └────────┘                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 The Tail at Scale (Google, 2013)

> Jeff Dean, Luiz Barroso
> "Fan-out 시스템에서 지연 시간의 롱테일 문제"

```
┌─────────────────────────────────────────────────────────────────┐
│                    Tail Latency 증폭                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  문제: Fan-out 시 가장 느린 응답이 전체 지연 결정                │
│  ────────────────────────────────────────────────                │
│                                                                  │
│  단일 서버 p99 = 10ms                                           │
│                                                                  │
│  Fan-out 100개 서버:                                            │
│  • 1 - (0.99)^100 = 63% 확률로 최소 1개가 p99 이상              │
│  • 전체 요청의 p50이 단일 서버의 p99와 비슷해짐                  │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐│
│  │            Latency Distribution                             ││
│  │                                                             ││
│  │  단일 서버:  ████████████████░░░░░░░░░░░░░░░░░░░░░         ││
│  │                           p50    p99                        ││
│  │                                                             ││
│  │  100x Fan-out: ░░░░░░░░░░░░░░░░████████████████████████    ││
│  │                                p50              p99         ││
│  │                                                             ││
│  └────────────────────────────────────────────────────────────┘│
│                                                                  │
│  해결책:                                                         │
│  1. Hedged Requests: 여러 replica에 동시 요청, 첫 응답 사용     │
│  2. Tied Requests: 큐에서 대기 시간이 긴 요청 취소             │
│  3. Micro-partitioning: 더 많은 작은 파티션                     │
│  4. Selective Replication: 핫 데이터만 추가 복제                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 SSE-Gateway Fanout 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    Eco² SSE-Gateway Fanout                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  현재 구조:                                                      │
│  ───────────                                                     │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  scan-worker (Producer)                                  │   │
│  │                                                          │   │
│  │  job_id → hash(job_id) % 4 → shard 0~3                  │   │
│  │                                                          │   │
│  │  XADD scan:events:{shard} * stage vision status done    │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Redis Streams                                           │   │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────┐ │   │
│  │  │ shard:0    │ │ shard:1    │ │ shard:2    │ │ :3   │ │   │
│  │  └────────────┘ └────────────┘ └────────────┘ └──────┘ │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  sse-gateway (Consumer)                                  │   │
│  │                                                          │   │
│  │  Pod-0: XREAD shard:0                                   │   │
│  │  Pod-1: XREAD shard:1  ← 현재 문제: 각 Pod가 1개만 읽음 │   │
│  │  Pod-2: XREAD shard:2                                   │   │
│  │  Pod-3: XREAD shard:3                                   │   │
│  │                                                          │   │
│  │  문제: job_id가 shard:2에 있는데 클라이언트가 Pod-0에   │   │
│  │        연결되면 이벤트를 영원히 못 받음                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 해결책: 라우팅 일관성

```
┌─────────────────────────────────────────────────────────────────┐
│                    해결책: Consistent Hash Routing               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Istio Consistent Hash로 SSE 요청 라우팅:                    │
│     job_id=abc → hash(abc) → Pod-2                             │
│                                                                  │
│  2. Pod-2는 shard:2만 구독 (Producer와 일치)                   │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Client                                                  │   │
│  │  GET /stream?job_id=abc                                  │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Istio (Envoy) - consistentHash.httpQueryParameterName  │   │
│  │                                                          │   │
│  │  job_id=abc → hash(abc) % 4 = 2 → Pod-2                 │   │
│  └──────────────────────────┬──────────────────────────────┘   │
│                             │                                    │
│                             ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Pod-2                                                   │   │
│  │  • XREAD scan:events:2 (자신의 shard만)                 │   │
│  │  • job_id=abc 이벤트 SSE로 전달                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  핵심: Producer의 shard 선택 = Routing의 shard 선택             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. Eco² 적용: 샤딩 + 라우팅 통합 설계

### 5.1 현재 문제

```
Producer (scan-worker):  hash(job_id) % 4 → shard 0~3에 발행
Consumer (sse-gateway):  각 Pod가 자기 shard만 읽음
Routing (Istio):         Round Robin (랜덤 Pod로 라우팅)

→ job_id가 shard:2에 있는데 클라이언트가 Pod-0에 연결되면 누락
```

### 5.2 단기 해결책

```yaml
# 옵션 A: 모든 shard 구독 (가장 빠른 해결)
# sse-gateway가 모든 shard를 XREAD
# 자신에게 연결된 클라이언트의 job_id만 필터링하여 전달

async def subscribe_all_shards(job_id: str):
    # 모든 shard를 순회하며 해당 job_id 이벤트 찾기
    shard = hash(job_id) % SHARD_COUNT
    stream_key = f"scan:events:{shard}"
    
    # 이 job의 shard만 읽기 (효율적)
    async for event in xread(stream_key, job_id):
        yield event
```

### 5.3 장기 해결책

```yaml
# Istio Consistent Hash 설정
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: sse-gateway-job-routing
  namespace: sse-consumer
spec:
  host: sse-gateway.sse-consumer.svc.cluster.local
  trafficPolicy:
    loadBalancer:
      consistentHash:
        httpQueryParameterName: "job_id"  # job_id로 라우팅

---
# sse-gateway ConfigMap: shard 할당
# Pod index와 shard 매핑 (수동 관리)
apiVersion: v1
kind: ConfigMap
metadata:
  name: sse-gateway-shard-config
  namespace: sse-consumer
data:
  # Pod 수와 shard 수가 같으면 1:1 매핑
  # Pod 수가 적으면 한 Pod가 여러 shard 담당
  shard_mapping: |
    pod-0: [0, 1]
    pod-1: [2, 3]
```

### 5.4 아키텍처 비교

```
┌─────────────────────────────────────────────────────────────────┐
│  Before (문제 상황)                                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Client ──▶ Istio (RoundRobin) ──▶ Pod-0 ──XREAD──▶ shard:0     │
│                                                                  │
│  scan-worker ──XADD──▶ shard:2 (job_id=abc)                     │
│                                                                  │
│  → Client는 Pod-0에 연결, 이벤트는 shard:2에 있음               │
│  → 영원히 이벤트를 못 받음                                       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  After (해결)                                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Client ──▶ Istio (consistentHash) ──▶ Pod-2 ──XREAD──▶ shard:2 │
│             hash(job_id=abc) = 2                                │
│                                                                  │
│  scan-worker ──XADD──▶ shard:2 (job_id=abc)                     │
│               hash(job_id=abc) = 2                              │
│                                                                  │
│  → Client와 이벤트가 같은 shard로 라우팅됨                      │
│  → 정상적으로 이벤트 수신                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 관련 문서

### Foundations

- [07-redis-streams.md](./07-redis-streams.md) - Redis Streams 기초
- [12-consensus-algorithms.md](./12-consensus-algorithms.md) - 분산 합의 (Quorum, Raft)

### Workloads

- [workloads/redis/](../../workloads/redis/) - Redis Sentinel 설정
- [workloads/routing/](../../workloads/routing/) - Istio 라우팅 설정

### 외부 자료

- [Consistent Hashing Paper](https://www.cs.princeton.edu/courses/archive/fall09/cos518/papers/chash.pdf) - MIT 원본 논문
- [Amazon Dynamo Paper](https://www.allthingsdistributed.com/files/amazon-dynamo-sosp2007.pdf) - Virtual Nodes
- [Envoy Ring Hash](https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/load_balancers#ring-hash) - 공식 문서
- [Istio Destination Rule](https://istio.io/latest/docs/reference/config/networking/destination-rule/) - consistentHash 설정

---

## 버전 정보

- 작성일: 2025-12-27
- Redis 버전: 7.0+
- Istio 버전: 1.20+
- 적용 대상: Eco² SSE-Gateway, scan-worker

