# Consensus Algorithms: 분산 합의 알고리즘

> [← 인덱스](./00-index.md) | [← 11. KEDA](./11-keda.md)

> 분산 시스템에서 여러 노드가 하나의 값에 동의하도록 하는 합의 알고리즘.
> Eco²에서는 Redis Sentinel (Quorum 기반)과 RabbitMQ Quorum Queue (Raft)를 사용합니다.

---

## 공식 자료 (1차 지식생산자)

### 핵심 논문

| 논문 | 저자 | 발표 | 핵심 내용 |
|------|------|------|---------|
| **[The Part-Time Parliament](https://lamport.azurewebsites.net/pubs/lamport-paxos.pdf)** | Leslie Lamport | ACM TOCS 1998 | Paxos 원본 논문 (그리스 의회 비유) |
| **[Paxos Made Simple](https://lamport.azurewebsites.net/pubs/paxos-simple.pdf)** | Leslie Lamport | 2001 | Paxos 알고리즘 간소화 설명 |
| **[Paxos Made Live](https://research.google/pubs/pub33002/)** | Chandra et al. (Google) | PODC 2007 | Chubby 구현 경험 (실제 적용) |
| **[In Search of an Understandable Consensus Algorithm](https://raft.github.io/raft.pdf)** | Diego Ongaro, John Ousterhout | USENIX ATC 2014 | Raft 합의 알고리즘 |
| **[Impossibility of Distributed Consensus with One Faulty Process](https://groups.csail.mit.edu/tds/papers/Lynch/jacm85.pdf)** | Fischer, Lynch, Paterson | JACM 1985 | FLP Impossibility (합의의 불가능성) |

### 공식 문서

| 기술 | 문서 | 핵심 내용 |
|------|------|---------|
| **Redis Sentinel** | [redis.io/docs/management/sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/) | Quorum 기반 장애 감지, 자동 Failover |
| **RabbitMQ Quorum Queues** | [rabbitmq.com/quorum-queues](https://www.rabbitmq.com/docs/quorum-queues) | Raft 기반 복제 큐 |
| **etcd (Raft)** | [etcd.io/docs/raft](https://etcd.io/docs/v3.5/learning/raft/) | Kubernetes가 사용하는 분산 KV 저장소 |

---

## 핵심 개념: 분산 합의 문제

### 1. 합의 문제 (Consensus Problem)

```
┌─────────────────────────────────────────────────────────────────┐
│                    분산 합의 문제                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  N개의 노드가 있을 때, 모든 노드가 동일한 값에 동의해야 함          │
│                                                                  │
│  요구사항:                                                       │
│  ─────────                                                       │
│  1. Agreement (동의): 모든 정상 노드는 같은 값을 결정              │
│  2. Validity (유효성): 결정된 값은 어떤 노드가 제안한 값            │
│  3. Termination (종료): 모든 정상 노드는 언젠가 결정에 도달        │
│                                                                  │
│  어려움:                                                         │
│  ───────                                                         │
│  - 네트워크 지연/분할                                             │
│  - 노드 장애 (crash, Byzantine)                                  │
│  - 비동기 시스템에서의 불가능성 (FLP)                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. FLP Impossibility (1985)

> **"비동기 분산 시스템에서 단 하나의 노드 장애도 허용하면서  
> 합의를 보장하는 결정론적 알고리즘은 존재하지 않는다."**

**의미:**
- 이론적으로 완벽한 합의는 불가능
- 실제 시스템은 **타임아웃**과 **확률적 보장**으로 우회

**해결 방법:**
1. **타임아웃 기반 장애 감지** (Redis Sentinel의 `down-after-milliseconds`)
2. **리더 선출** (Raft의 Term, 무작위 타이머)
3. **Quorum** (과반수 동의)

---

## Quorum: 과반수 동의 원칙

### 정의

```
Quorum = ⌊N/2⌋ + 1

예시:
- 3노드: Quorum = 2 (1노드 장애 허용)
- 5노드: Quorum = 3 (2노드 장애 허용)
- 7노드: Quorum = 4 (3노드 장애 허용)
```

### 왜 과반수인가?

```
┌─────────────────────────────────────────────────────────────────┐
│  Split-Brain 방지                                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  네트워크 분할 시나리오 (3노드):                                  │
│                                                                  │
│  ┌─────────┐         │         ┌─────────┐                      │
│  │  Node A │─────────│─────────│  Node C │                      │
│  └─────────┘         │         └─────────┘                      │
│       │              │ Network      │                           │
│       │              │ Partition    │                           │
│  ┌─────────┐         │              │                           │
│  │  Node B │         │              │                           │
│  └─────────┘                                                    │
│                                                                  │
│  Partition 1: A, B (2노드) → Quorum 충족 ✓ → 정상 동작           │
│  Partition 2: C (1노드)   → Quorum 미충족 ✗ → 읽기 전용          │
│                                                                  │
│  → 두 파티션이 동시에 쓰기를 허용하면 데이터 불일치 발생!           │
│  → Quorum은 항상 하나의 파티션만 쓰기 가능하도록 보장               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Paxos 합의 알고리즘

> Leslie Lamport (1989, 2001)
> 분산 합의의 원조 알고리즘, 모든 합의 알고리즘의 기초

### 1. 역사적 배경

```
┌─────────────────────────────────────────────────────────────────┐
│                    Paxos의 역사                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1989: Leslie Lamport, "The Part-Time Parliament" 논문 작성     │
│        → 그리스 Paxos 섬의 의회 비유로 설명                     │
│        → 너무 어려워서 학계에서 거부당함                         │
│                                                                  │
│  1998: 논문 최초 게재 (ACM TOCS)                                │
│        → 9년 만에 출판됨                                        │
│                                                                  │
│  2001: "Paxos Made Simple" 발표                                 │
│        → 비유 없이 직접적인 설명 시도                           │
│        → "The Paxos algorithm, when presented in plain English, │
│           is very simple."                                       │
│                                                                  │
│  현재: Google Chubby, Spanner, 모든 분산 합의 시스템의 기초     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 핵심 역할 (Roles)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Paxos 역할                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐                                                │
│  │  Proposer   │  값을 제안하는 노드                            │
│  │             │  • 클라이언트 요청을 받아 값을 제안             │
│  │             │  • Proposal Number (n)을 생성                  │
│  └─────────────┘                                                │
│         │                                                        │
│         │ Prepare(n) / Accept(n, v)                             │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │  Acceptor   │  제안을 수락/거부하는 노드                     │
│  │             │  • Promise: 더 높은 n만 수락하겠다는 약속       │
│  │             │  • Accept: 실제로 값을 수락                    │
│  │             │  • Quorum (과반수)의 수락이 필요               │
│  └─────────────┘                                                │
│         │                                                        │
│         │ Accepted(n, v)                                        │
│         ▼                                                        │
│  ┌─────────────┐                                                │
│  │  Learner    │  합의된 값을 학습하는 노드                     │
│  │             │  • 최종 결정된 값을 알게 됨                     │
│  │             │  • 클라이언트에 결과 반환                       │
│  └─────────────┘                                                │
│                                                                  │
│  참고: 실제 시스템에서는 한 노드가 여러 역할을 겸함              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Basic Paxos: 2-Phase Protocol

```
┌─────────────────────────────────────────────────────────────────┐
│                    Phase 1: Prepare (약속 요청)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Proposer                    Acceptors (A1, A2, A3)             │
│     │                           │    │    │                     │
│     │  1. Prepare(n=1)          │    │    │                     │
│     │──────────────────────────▶│    │    │                     │
│     │──────────────────────────────▶ │    │                     │
│     │─────────────────────────────────▶   │                     │
│     │                           │    │    │                     │
│     │  2. Promise(n=1)          │    │    │                     │
│     │◀──────────────────────────│    │    │                     │
│     │◀──────────────────────────────│    │                     │
│     │◀───────────────────────────────────│                     │
│     │                           │    │    │                     │
│                                                                  │
│  Acceptor 응답:                                                  │
│  • Promise: "n=1 이상의 제안만 수락하겠다"                      │
│  • 이미 수락한 값이 있으면 함께 반환 (n_accepted, v_accepted)   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                    Phase 2: Accept (수락 요청)                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Proposer                    Acceptors (A1, A2, A3)             │
│     │                           │    │    │                     │
│     │  3. Accept(n=1, v="X")    │    │    │                     │
│     │──────────────────────────▶│    │    │                     │
│     │──────────────────────────────▶ │    │                     │
│     │─────────────────────────────────▶   │                     │
│     │                           │    │    │                     │
│     │  4. Accepted(n=1, v="X")  │    │    │                     │
│     │◀──────────────────────────│    │    │  (Quorum = 2)       │
│     │◀──────────────────────────────│    │                     │
│     │                           │    │    │                     │
│     │                                                            │
│     │  5. 합의 완료! v="X"가 선택됨                             │
│     │     Learner들에게 알림                                     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Paxos 충돌 해결

```
┌─────────────────────────────────────────────────────────────────┐
│                    두 Proposer가 동시에 제안하면?                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Proposer P1        Acceptors         Proposer P2               │
│     │                  │                    │                   │
│     │ Prepare(n=1)     │                    │                   │
│     │─────────────────▶│                    │                   │
│     │                  │◀───────────────────│ Prepare(n=2)      │
│     │                  │                    │                   │
│     │◀─ Promise(n=1)   │                    │                   │
│     │                  │── Promise(n=2) ───▶│                   │
│     │                  │                    │                   │
│     │ Accept(n=1, "A") │                    │                   │
│     │─────────────────▶│                    │                   │
│     │                  │ ✗ 거부! (n=2 약속함)                   │
│     │◀── Rejected ─────│                    │                   │
│     │                  │                    │                   │
│     │                  │◀───────────────────│ Accept(n=2, "B")  │
│     │                  │── Accepted ────────▶│                   │
│     │                  │                    │                   │
│                                                                  │
│  결과: P2의 "B"가 선택됨                                        │
│  P1은 더 높은 n으로 재시도해야 함                               │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5. Multi-Paxos (연속 합의)

```
┌─────────────────────────────────────────────────────────────────┐
│                    Multi-Paxos                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Basic Paxos: 단일 값에 대한 합의                               │
│  Multi-Paxos: 연속적인 값들에 대한 합의 (로그 복제)             │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Log Slot:   [1]     [2]     [3]     [4]     ...        │   │
│  │  Value:      "A"     "B"     "C"     "D"                │   │
│  │              ▲       ▲       ▲       ▲                  │   │
│  │              │       │       │       │                  │   │
│  │           Paxos   Paxos   Paxos   Paxos                 │   │
│  │          Instance Instance Instance Instance            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  최적화: Leader 선출                                            │
│  ─────────────────────                                          │
│  • 한 Proposer가 계속 Leader 역할                               │
│  • Phase 1 (Prepare)를 한 번만 수행                             │
│  • Phase 2 (Accept)만 반복 → 성능 향상                         │
│                                                                  │
│  이것이 Raft의 핵심 아이디어로 발전                             │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6. Paxos의 어려움

```
┌─────────────────────────────────────────────────────────────────┐
│                    왜 Paxos가 어려운가?                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Livelock 가능성                                             │
│     • 두 Proposer가 번갈아 더 높은 n으로 Prepare               │
│     • 무한 경쟁 → 진행 불가                                     │
│     • 해결: 랜덤 백오프, Leader 선출                            │
│                                                                  │
│  2. 복잡한 상태 관리                                            │
│     • 각 Acceptor가 유지해야 할 상태:                           │
│       - 약속한 최고 n                                           │
│       - 수락한 (n, v) 쌍                                        │
│     • 재시작 시 복구 필요                                       │
│                                                                  │
│  3. 구현의 모호함                                               │
│     • 논문이 너무 추상적                                        │
│     • "실제로 어떻게 구현하지?" 에 대한 답이 없음               │
│     • Leader 선출, 멤버십 변경 등 미다룸                        │
│                                                                  │
│  4. 학습 곡선                                                   │
│     • Google: "There are significant gaps between the          │
│       description of the Paxos algorithm and the needs         │
│       of a real-world system"                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 7. Paxos vs Raft

```
┌─────────────────────────────────────────────────────────────────┐
│                    Paxos vs Raft 비교                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  특성              │ Paxos              │ Raft                  │
│  ──────────────────┼────────────────────┼─────────────────────  │
│  Leader            │ 선택적 (최적화)     │ 필수 (핵심 개념)      │
│                    │                    │                       │
│  로그 복제         │ 별도 정의 필요      │ 기본 제공             │
│                    │                    │                       │
│  멤버십 변경       │ 미정의             │ Joint Consensus       │
│                    │                    │                       │
│  이해 난이도       │ 매우 어려움         │ 상대적으로 쉬움       │
│                    │                    │                       │
│  구현 복잡도       │ 높음               │ 중간                  │
│                    │                    │                       │
│  실제 적용         │ Google (Chubby,    │ etcd, Consul,         │
│                    │ Spanner)           │ CockroachDB           │
│                    │                    │                       │
│  성능              │ 이론적으로 동등     │ 이론적으로 동등       │
│                                                                  │
│  Raft 논문 인용:                                                │
│  "Raft is equivalent to Multi-Paxos in terms of correctness    │
│   and performance, but it is much easier to understand."        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Raft 합의 알고리즘

> Diego Ongaro & John Ousterhout (Stanford, 2014)
> "Paxos보다 이해하기 쉬운 합의 알고리즘"

### 1. 핵심 구성요소

```
┌─────────────────────────────────────────────────────────────────┐
│                    Raft 구성요소                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  노드 상태:                                                      │
│  ──────────                                                      │
│  • Leader: 클라이언트 요청 처리, 로그 복제                        │
│  • Follower: Leader의 로그를 수신하고 복제                       │
│  • Candidate: Leader 선출 중인 상태                              │
│                                                                  │
│  핵심 개념:                                                      │
│  ──────────                                                      │
│  • Term: 논리적 시간 단위 (Leader 임기)                          │
│  • Log: 명령 시퀀스 (append-only)                                │
│  • Commit: Quorum에 복제된 로그 엔트리                           │
│                                                                  │
│  RPC:                                                            │
│  ────                                                            │
│  • RequestVote: Leader 선출                                      │
│  • AppendEntries: 로그 복제 / Heartbeat                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Leader Election

```
┌─────────────────────────────────────────────────────────────────┐
│                    Leader Election 흐름                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 초기 상태: 모든 노드는 Follower                              │
│                                                                  │
│     ┌──────────┐  ┌──────────┐  ┌──────────┐                   │
│     │ Follower │  │ Follower │  │ Follower │                   │
│     │  Term=1  │  │  Term=1  │  │  Term=1  │                   │
│     └──────────┘  └──────────┘  └──────────┘                   │
│                                                                  │
│  2. Election Timeout 만료 (랜덤 150~300ms):                      │
│     → Follower → Candidate (Term 증가)                          │
│     → 자신에게 투표 + 다른 노드에 RequestVote 전송               │
│                                                                  │
│     ┌───────────┐  ┌──────────┐  ┌──────────┐                  │
│     │ Candidate │──│ Follower │──│ Follower │                  │
│     │  Term=2   │  │  Term=1  │  │  Term=1  │                  │
│     │ votes=1   │  │          │  │          │                  │
│     └───────────┘  └──────────┘  └──────────┘                  │
│          │ RequestVote(Term=2)                                  │
│          └──────────────────────────▶                           │
│                                                                  │
│  3. Quorum 투표 획득 시 Leader 승격:                             │
│                                                                  │
│     ┌──────────┐   ┌──────────┐  ┌──────────┐                  │
│     │  Leader  │ ─▶│ Follower │  │ Follower │                  │
│     │  Term=2  │   │  Term=2  │  │  Term=2  │                  │
│     └──────────┘   └──────────┘  └──────────┘                  │
│          │ AppendEntries (Heartbeat)                            │
│          └──────────────────────────▶                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Log Replication

```
┌─────────────────────────────────────────────────────────────────┐
│                    Log Replication                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Leader                Follower A           Follower B           │
│    │                      │                     │                │
│    │  1. Client Request   │                     │                │
│    │◀────────────────     │                     │                │
│    │                      │                     │                │
│    │  2. Append to local log                    │                │
│    ├───┐                  │                     │                │
│    │   │                  │                     │                │
│    │◀──┘                  │                     │                │
│    │                      │                     │                │
│    │  3. AppendEntries    │                     │                │
│    │─────────────────────▶│                     │                │
│    │─────────────────────────────────────────▶  │                │
│    │                      │                     │                │
│    │  4. Ack              │                     │                │
│    │◀─────────────────────│                     │                │
│    │◀──────────────────────────────────────────│                │
│    │                      │                     │                │
│    │  5. Commit (Quorum 도달)                   │                │
│    │  6. Apply to State Machine                 │                │
│    │  7. Response to Client                     │                │
│    │                      │                     │                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Redis Sentinel

> Redis의 고가용성(HA)을 위한 분산 모니터링 및 자동 Failover 시스템

### 1. 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    Redis Sentinel 아키텍처                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Sentinel Cluster                            ││
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐               ││
│  │  │ Sentinel-0│  │ Sentinel-1│  │ Sentinel-2│               ││
│  │  │ (monitor) │  │ (monitor) │  │ (monitor) │               ││
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘               ││
│  │        │              │              │                       ││
│  │        └──────────────┼──────────────┘                       ││
│  │                       │                                       ││
│  │               Quorum 투표 (2/3)                               ││
│  │                       │                                       ││
│  └───────────────────────┼──────────────────────────────────────┘│
│                          │                                        │
│                          ▼                                        │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Redis Cluster                               ││
│  │  ┌───────────┐                                               ││
│  │  │  Master   │◀─── 쓰기 (RW)                                 ││
│  │  │  (RW)     │                                               ││
│  │  └─────┬─────┘                                               ││
│  │        │ Async Replication                                   ││
│  │        ▼                                                      ││
│  │  ┌───────────┐  ┌───────────┐                               ││
│  │  │ Replica-1 │  │ Replica-2 │◀─── 읽기 (RO)                  ││
│  │  │  (RO)     │  │  (RO)     │                                ││
│  │  └───────────┘  └───────────┘                               ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. 장애 감지: SDOWN vs ODOWN

```
┌─────────────────────────────────────────────────────────────────┐
│                    장애 감지 흐름                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  SDOWN (Subjectively Down): 주관적 장애                          │
│  ────────────────────────────────────────                        │
│  • 단일 Sentinel이 Master 응답 없음 감지                         │
│  • down-after-milliseconds (기본 5000ms) 초과                    │
│                                                                  │
│     Sentinel-0: "Master가 5초간 응답 없음" → SDOWN               │
│                                                                  │
│  ODOWN (Objectively Down): 객관적 장애                           │
│  ────────────────────────────────────────                        │
│  • Quorum 이상의 Sentinel이 SDOWN 동의                           │
│  • Failover 시작 조건                                            │
│                                                                  │
│     Sentinel-0: SDOWN ─┐                                        │
│     Sentinel-1: SDOWN ─┼─▶ Quorum(2/3) 충족 → ODOWN → Failover │
│     Sentinel-2: OK     │                                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3. Failover 프로세스

```
┌─────────────────────────────────────────────────────────────────┐
│                    Failover 단계                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. ODOWN 감지 (Quorum 동의)                                     │
│     └── 다수의 Sentinel이 Master 장애에 동의                     │
│                                                                  │
│  2. Sentinel Leader 선출                                         │
│     └── Raft와 유사한 방식으로 Failover 주도 Sentinel 선출       │
│     └── 과반수 투표 필요                                         │
│                                                                  │
│  3. 새 Master 선택                                               │
│     └── 우선순위: replica-priority → replication offset → runid │
│     └── 가장 최신 데이터를 가진 Replica 선택                     │
│                                                                  │
│  4. Promotion                                                    │
│     └── 선택된 Replica에 SLAVEOF NO ONE 명령                     │
│     └── 새 Master로 승격                                         │
│                                                                  │
│  5. 재구성                                                       │
│     └── 다른 Replica들에 REPLICAOF new-master 명령               │
│     └── 클라이언트에 새 Master 주소 알림                         │
│                                                                  │
│  총 소요시간: down-after-milliseconds + failover-timeout         │
│              ≈ 5초 + 10초 = 15초 이내                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 4. Eco² Redis Sentinel 설정

```yaml
# workloads/redis/base/streams-redis-failover.yaml
apiVersion: databases.spotahome.com/v1
kind: RedisFailover
metadata:
  name: streams-redis
  namespace: redis
spec:
  sentinel:
    replicas: 3
    customConfig:
    - down-after-milliseconds 5000   # 5초 무응답 → SDOWN
    - failover-timeout 10000         # 10초 이내 Failover 완료

  redis:
    replicas: 3  # Master 1 + Replica 2
    customConfig:
    - maxmemory 256mb
    - maxmemory-policy noeviction
```

**Eco² Redis 구성:**

| Redis Instance | 용도 | Quorum | 장애 허용 |
|----------------|------|--------|---------|
| auth-redis | JWT Blacklist, OAuth State | 2/3 | 1노드 |
| streams-redis | SSE 이벤트 스트림 | 2/3 | 1노드 |
| cache-redis | Celery Result Backend | 2/3 | 1노드 |

---

## RabbitMQ Quorum Queues

> RabbitMQ 3.8+에서 도입된 Raft 기반 복제 큐
> Mirrored Queue의 대체제로, 더 나은 데이터 안전성 제공

### 1. 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                    Quorum Queue 아키텍처                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  RabbitMQ Cluster (3 Nodes)                                     │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Node 1 (Leader)                                           │ │
│  │  ┌─────────────────┐                                       │ │
│  │  │ Quorum Queue    │◀─── Publisher                        │ │
│  │  │ (Leader)        │                                       │ │
│  │  │ Log: [1,2,3,4]  │                                       │ │
│  │  └────────┬────────┘                                       │ │
│  └───────────┼───────────────────────────────────────────────┘ │
│              │ Raft Replication                                 │
│              ▼                                                   │
│  ┌───────────────────────────────────────────────────────────┐ │
│  │  Node 2 (Follower)           Node 3 (Follower)             │ │
│  │  ┌─────────────────┐         ┌─────────────────┐          │ │
│  │  │ Quorum Queue    │         │ Quorum Queue    │          │ │
│  │  │ (Follower)      │         │ (Follower)      │          │ │
│  │  │ Log: [1,2,3,4]  │         │ Log: [1,2,3,4]  │          │ │
│  │  └─────────────────┘         └─────────────────┘          │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Consumer ───▶ Leader에서 소비 (Consumer가 Leader 추적)         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Raft vs Mirrored Queue

| 특성 | Mirrored Queue (레거시) | Quorum Queue (Raft) |
|------|------------------------|---------------------|
| **복제 방식** | 비동기 미러링 | Raft 로그 복제 |
| **데이터 안전성** | 메시지 유실 가능 | Quorum Ack 보장 |
| **성능** | 높음 (비동기) | 중간 (동기 Ack) |
| **장애 복구** | 수동 개입 필요 | 자동 Leader Election |
| **Split-Brain** | 취약 | Quorum으로 방지 |

### 3. Eco² RabbitMQ 설정

```yaml
# workloads/rabbitmq/prod/kustomization.yaml
patches:
- patch: |
    - op: replace
      path: /spec/replicas
      value: 3
    - op: add
      path: /spec/rabbitmq/additionalConfig
      value: |
        # 3노드 클러스터 힌트
        cluster_formation.target_cluster_size_hint = 3

        # 네트워크 분할 처리 전략
        cluster_partition_handling = pause_minority

        # 리더 분산 (큐별 리더를 여러 노드에 분산)
        queue_leader_locator = balanced
```

**cluster_partition_handling 옵션:**

| 옵션 | 동작 | 사용 시나리오 |
|------|------|-------------|
| `ignore` | 분할 무시 | 테스트/개발 |
| `pause_minority` | 소수 파티션 일시정지 | **권장** (Eco² 사용) |
| `autoheal` | 자동 복구 (데이터 손실 가능) | 가용성 우선 |

### 4. Classic Queue vs Quorum Queue

Eco²에서는 **Classic Queue**를 사용합니다:

```yaml
# workloads/rabbitmq/base/topology/queues.yaml
apiVersion: rabbitmq.com/v1beta1
kind: Queue
metadata:
  name: scan-vision-queue
spec:
  name: scan.vision
  type: classic  # Classic Queue (Celery 호환)
  durable: true
```

**이유:**
- Celery의 Global QoS와의 호환성
- 개발 환경 단일 노드 지원
- 프로덕션에서는 `cluster_partition_handling = pause_minority`로 보완

---

## 운영 명령어

### Redis Sentinel 상태 확인

```bash
# Sentinel Master 정보 조회
kubectl exec -n redis rfs-streams-redis-0 -- \
  redis-cli -p 26379 SENTINEL master mymaster

# 출력 예시:
# name: mymaster
# ip: 10.0.1.15
# port: 6379
# flags: master
# num-slaves: 2
# quorum: 2

# Replica 목록
kubectl exec -n redis rfs-streams-redis-0 -- \
  redis-cli -p 26379 SENTINEL replicas mymaster

# Replication 상태
kubectl exec -n redis rfr-streams-redis-0 -- \
  redis-cli INFO replication

# 수동 Failover 테스트
kubectl exec -n redis rfs-streams-redis-0 -- \
  redis-cli -p 26379 SENTINEL failover mymaster
```

### RabbitMQ 클러스터 상태 확인

```bash
# 클러스터 상태
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl cluster_status

# Quorum Queue 상태 (사용 시)
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl list_quorum_queue_members

# 파티션 상태
kubectl exec -n rabbitmq eco2-rabbitmq-server-0 -- \
  rabbitmqctl list_partitions
```

---

## 장애 시나리오와 대응

### 1. Redis Master 장애

```
시나리오: rfr-streams-redis-0 (Master) 크래시

1. Sentinel 감지 (5초): SDOWN
2. Quorum 투표 (즉시): ODOWN
3. Sentinel Leader 선출
4. 새 Master 선택 (replication offset 기준)
5. Promotion: rfr-streams-redis-1 → Master
6. 재구성: rfr-streams-redis-2 → 새 Master의 Replica

총 복구 시간: ~15초
데이터 손실: 비동기 복제 미완료분 (수 ms)
```

### 2. RabbitMQ 네트워크 분할

```
시나리오: 3노드 클러스터에서 네트워크 분할

Partition A: Node 1, Node 2 (Quorum 유지)
Partition B: Node 3 (Quorum 미달)

cluster_partition_handling = pause_minority 동작:
- Partition A: 정상 동작 (2/3 Quorum)
- Partition B: 일시정지 (연결 거부)

복구 시:
- Node 3이 Partition A에 재합류
- 데이터 동기화 후 정상 동작
```

---

## Eco² 합의 알고리즘 요약

```
┌─────────────────────────────────────────────────────────────────┐
│                    Eco² 분산 합의 구조                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐         ┌──────────────────┐             │
│  │  Redis Sentinel  │         │  RabbitMQ Cluster │             │
│  │                  │         │                   │             │
│  │  합의: Quorum    │         │  합의: Raft       │             │
│  │  투표: 2/3       │         │  파티션: pause_   │             │
│  │                  │         │          minority │             │
│  │  ┌────────────┐ │         │  ┌─────────────┐  │             │
│  │  │ auth-redis │ │         │  │ eco2-rabbit │  │             │
│  │  │ streams    │ │         │  │ mq-server   │  │             │
│  │  │ cache      │ │         │  └─────────────┘  │             │
│  │  └────────────┘ │         │                   │             │
│  └──────────────────┘         └──────────────────┘             │
│                                                                  │
│  Kubernetes (etcd):                                             │
│  ───────────────────                                            │
│  • etcd: Raft 합의 (Control Plane)                              │
│  • API Server ← etcd (일관성 보장)                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 관련 문서

### Foundations

- [14-flp-impossibility.md](./14-flp-impossibility.md) - 분산 합의의 불가능성 (FLP 정리)
- [13-sharding-and-routing.md](./13-sharding-and-routing.md) - 샤딩과 라우팅
- [07-redis-streams.md](./07-redis-streams.md) - Redis Streams 데이터 구조
- [03-amqp-protocol.md](./03-amqp-protocol.md) - RabbitMQ/AMQP 프로토콜

### Workloads

- [workloads/redis/README.md](../../workloads/redis/README.md) - Redis HA 운영 가이드
- [workloads/rabbitmq/](../../workloads/rabbitmq/) - RabbitMQ 클러스터 설정

### 외부 자료

- [Paxos Made Simple](https://lamport.azurewebsites.net/pubs/paxos-simple.pdf) - Leslie Lamport 원본 논문
- [Paxos Made Live (Google)](https://research.google/pubs/pub33002/) - Chubby 실제 구현 경험
- [Raft 시각화](https://raft.github.io/) - Raft 알고리즘 인터랙티브 시각화
- [The Raft Paper](https://raft.github.io/raft.pdf) - 원본 논문
- [Redis Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/) - 공식 문서

---

## 버전 정보

- 작성일: 2025-12-27
- Redis 버전: 7.0+
- RabbitMQ 버전: 4.0
- 적용 대상: Eco² Backend Infrastructure

