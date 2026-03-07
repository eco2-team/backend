# SAGAS: 장기 실행 트랜잭션의 해법

> **Part V: 분산 트랜잭션** | [← 06. Life Beyond](./06-life-beyond-distributed-transactions.md) | [인덱스](./00-index.md) | [08. Outbox →](./08-transactional-outbox.md)

> 원문: [SAGAS](https://sigmodrecord.org/1987/12/09/sagas/) - Hector Garcia-Molina, Kenneth Salem (ACM SIGMOD Record, December 1987)  
> PDF: [Direct Download](https://sigmodrecord.org/?smd_process_download=1&download_id=11106)

---

## 들어가며

1987년, Princeton 대학의 Hector Garcia-Molina와 Kenneth Salem이 발표한 이 논문은 **분산 시스템에서 장기 실행 트랜잭션을 처리하는 방법**의 원형을 제시했다. 36년이 지난 지금, 이 개념은 마이크로서비스 아키텍처의 핵심 패턴으로 부활했다.

논문의 핵심 질문은 단순하다: "트랜잭션이 몇 시간 동안 실행된다면, 그 동안 데이터를 잠가둬야 할까?"

---

## Long-Lived Transactions의 문제

### 기존 트랜잭션의 한계

전통적인 ACID 트랜잭션은 **짧은 작업**을 전제로 설계되었다:

```
┌─────────────────────────────────────────────────────────────┐
│              전통적 트랜잭션 vs Long-Lived Transaction        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  전통적 트랜잭션 (밀리초~초):                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ BEGIN                                               │   │
│  │   UPDATE accounts SET balance = balance - 100       │   │
│  │   UPDATE accounts SET balance = balance + 100       │   │
│  │ COMMIT                                              │   │
│  └─────────────────────────────────────────────────────┘   │
│  → 빠르게 완료, 잠금 시간 최소화                           │
│                                                             │
│  Long-Lived Transaction (분~시간):                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ BEGIN                                               │   │
│  │   1. 재고 확인 및 예약           ← 5초              │   │
│  │   2. 결제 처리                   ← 사용자 입력 대기  │   │
│  │   3. 외부 배송 API 호출          ← 네트워크 지연    │   │
│  │   4. 이메일 발송                 ← 외부 서비스      │   │
│  │   5. 포인트 적립                                    │   │
│  │ COMMIT                           ← 총 5분 소요?     │   │
│  └─────────────────────────────────────────────────────┘   │
│  → 5분간 모든 관련 데이터 잠금?                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 잠금의 악몽

Long-Lived Transaction이 잠금을 유지하면:

```
┌─────────────────────────────────────────────────────────────┐
│                  잠금 경합 문제                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시간 →                                                     │
│                                                             │
│  트랜잭션 A (5분 소요):                                     │
│  ════════════════════════════════════▶                     │
│  │← 상품 #123 잠금 ─────────────────→│                     │
│                                                             │
│  트랜잭션 B: "상품 #123 조회"                               │
│       ────────────▶│ 대기... │──▶ (5분 후 실행)           │
│                     └────────┘                              │
│                                                             │
│  트랜잭션 C: "상품 #123 구매"                               │
│            ──▶│ 대기... │──▶│ 대기... │──▶ (timeout)      │
│                └────────┘   └────────┘                      │
│                                                             │
│  문제:                                                      │
│  • 다른 사용자 블로킹                                       │
│  • 처리량 급감                                              │
│  • 타임아웃으로 인한 실패                                   │
│  • 데드락 가능성 증가                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Saga의 정의

### 큰 트랜잭션을 작은 조각으로

Garcia-Molina의 해결책: **하나의 Long-Lived Transaction을 여러 개의 작은 트랜잭션으로 분해**한다.

```
┌─────────────────────────────────────────────────────────────┐
│                     Saga의 구조                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Long-Lived Transaction:                                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                T (전체 트랜잭션)                      │   │
│  │  ════════════════════════════════════════════════   │   │
│  │  5분간 실행, 전체 잠금                               │   │
│  └─────────────────────────────────────────────────────┘   │
│                          │                                  │
│                          ▼ 분해                             │
│                                                             │
│  Saga (작은 트랜잭션의 시퀀스):                             │
│  ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐   ┌─────┐        │
│  │ T1  │──▶│ T2  │──▶│ T3  │──▶│ T4  │──▶│ T5  │        │
│  │재고 │   │결제 │   │배송 │   │이메일│   │포인트│        │
│  └─────┘   └─────┘   └─────┘   └─────┘   └─────┘        │
│   10초      30초      20초      5초       5초             │
│                                                             │
│  각 Ti는 독립적으로 커밋                                    │
│  각 Ti는 짧은 잠금만 유지                                   │
│  전체 Saga는 결과적 일관성                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Saga의 공식 정의

논문에서의 정의:

> **Saga** = 인터리빙될 수 있는 트랜잭션의 시퀀스 (T1, T2, ..., Tn)

즉, Saga의 각 단계 사이에 다른 트랜잭션이 실행될 수 있다. 이것이 핵심이다!

```
┌─────────────────────────────────────────────────────────────┐
│               Saga의 인터리빙 실행                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시간 →                                                     │
│                                                             │
│  Saga A: ──[T1]────────[T2]────────[T3]──▶                 │
│              │          │          │                        │
│  Saga B:     └──[T1]────┼──[T2]────┼──[T3]──▶              │
│                         │          │                        │
│  일반 TX:               └──[TX]────┘                        │
│                                                             │
│  각 트랜잭션은 독립적으로 실행                              │
│  서로의 완료를 기다리지 않음                                │
│  잠금 경합 최소화                                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Compensating Transactions: 보상 트랜잭션

### 롤백의 대안

ACID 트랜잭션에서는 실패 시 `ROLLBACK`으로 모든 것을 되돌린다. 하지만 Saga에서는 이미 커밋된 트랜잭션을 롤백할 수 없다.

해결책: **Compensating Transaction (보상 트랜잭션)**

```
┌─────────────────────────────────────────────────────────────┐
│                    보상 트랜잭션 개념                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  각 트랜잭션 Ti에 대해 보상 트랜잭션 Ci를 정의:             │
│                                                             │
│  T1: 재고 10개 차감        C1: 재고 10개 복구               │
│  T2: 결제 10,000원 처리    C2: 결제 10,000원 환불           │
│  T3: 배송 요청             C3: 배송 취소                    │
│  T4: 이메일 발송           C4: 취소 안내 이메일 발송        │
│  T5: 포인트 100점 적립     C5: 포인트 100점 차감            │
│                                                             │
│  정상 실행:                                                 │
│  T1 → T2 → T3 → T4 → T5  (완료!)                          │
│                                                             │
│  T3에서 실패:                                               │
│  T1 → T2 → T3(실패) → C2 → C1  (보상 실행)                │
│                                                             │
│  ※ T4, T5는 실행되지 않았으므로 보상 불필요                 │
│  ※ C3은 T3이 실패했으므로 보상 불필요                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 보상의 역순 실행

보상 트랜잭션은 **역순**으로 실행된다:

```
┌─────────────────────────────────────────────────────────────┐
│                  Backward Recovery                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정상 흐름:                                                 │
│                                                             │
│  T1 ──▶ T2 ──▶ T3 ──▶ T4 ──▶ T5                           │
│   │      │      │      │      │                            │
│   ✓      ✓      ✓      ✓      ✓                            │
│                                                             │
│  T3에서 실패 시 보상:                                       │
│                                                             │
│  T1 ──▶ T2 ──▶ T3 ──X                                      │
│   │      │      │                                          │
│   ✓      ✓      ✗                                          │
│   │      │                                                 │
│   │      └──── C2 (결제 환불)                              │
│   │             │                                          │
│   └──────────── C1 (재고 복구)                             │
│                                                             │
│  최종 상태: 시작 전과 동일 (논리적으로)                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Semantic Rollback: 의미적 롤백

### 완벽한 되돌리기는 불가능

중요한 점: 보상 트랜잭션은 **물리적 롤백이 아니라 의미적 롤백**이다.

```
┌─────────────────────────────────────────────────────────────┐
│              물리적 vs 의미적 롤백                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  물리적 롤백 (불가능):                                      │
│  "마치 아무 일도 없었던 것처럼"                             │
│  → 이메일 이미 발송됨                                      │
│  → SMS 이미 전송됨                                         │
│  → 외부 API 이미 호출됨                                    │
│                                                             │
│  의미적 롤백 (Compensating Transaction):                    │
│  "비즈니스 관점에서 동등한 결과"                            │
│                                                             │
│  예: 호텔 예약                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ T1: 예약 생성 (예약 ID: 12345)                       │   │
│  │     → DB에 예약 레코드 INSERT                        │   │
│  │                                                     │   │
│  │ C1: 예약 취소 (예약 ID: 12345)                       │   │
│  │     → DB에서 DELETE? ❌                             │   │
│  │     → status = "cancelled" UPDATE ✅                │   │
│  │     → 취소 이력 INSERT                              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  물리적으로는 데이터가 더 늘어남 (취소 이력)                │
│  의미적으로는 "예약이 없는 상태"와 동등                     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Forward vs Backward Recovery

### 두 가지 복구 전략

논문에서는 두 가지 복구 전략을 제시한다:

```
┌─────────────────────────────────────────────────────────────┐
│            Forward Recovery vs Backward Recovery             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Backward Recovery (보상):                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ T1 → T2 → T3(fail) → C2 → C1                        │   │
│  │                                                     │   │
│  │ 특징:                                               │   │
│  │ • 실패 지점까지 되돌아감                            │   │
│  │ • 모든 성공한 트랜잭션을 보상                       │   │
│  │ • 시작점으로 복귀                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Forward Recovery (재시도):                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ T1 → T2 → T3(fail) → T3(retry) → T4 → T5            │   │
│  │                                                     │   │
│  │ 특징:                                               │   │
│  │ • 실패한 단계를 재시도                              │   │
│  │ • 앞으로 계속 진행                                  │   │
│  │ • 완료를 목표로 함                                  │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  선택 기준:                                                 │
│  • 일시적 오류 (네트워크 타임아웃) → Forward Recovery       │
│  • 비즈니스 오류 (재고 부족) → Backward Recovery           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Pivot Transaction

### 되돌릴 수 없는 지점

일부 트랜잭션은 실행 후 보상이 불가능하다. 이를 **Pivot Transaction**이라 한다:

```
┌─────────────────────────────────────────────────────────────┐
│                    Pivot Transaction                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  T1 → T2 → [Pivot] → T4 → T5                               │
│            └─ T3 ─┘                                         │
│                                                             │
│  Pivot Transaction 예시:                                    │
│  • 실제 결제 승인 (취소 수수료 발생)                        │
│  • 물리적 상품 배송 시작                                    │
│  • 법적 계약 체결                                           │
│  • 외부 시스템에 돌이킬 수 없는 변경                        │
│                                                             │
│  설계 원칙:                                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  [보상 가능한 트랜잭션] → [Pivot] → [재시도 가능]    │   │
│  │        T1, T2              T3         T4, T5        │   │
│  │                                                     │   │
│  │  Pivot 전: Backward Recovery 가능                   │   │
│  │  Pivot 후: Forward Recovery만 가능 (반드시 완료)    │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Pivot을 가능한 뒤로 미루는 것이 좋은 설계                  │
│  → 더 많은 검증을 Pivot 전에 수행                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 현대적 Saga 구현

### Choreography vs Orchestration

Chris Richardson의 Microservices Patterns에서 확장된 두 가지 구현 방식:

```
┌─────────────────────────────────────────────────────────────┐
│                Choreography (안무)                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  각 서비스가 이벤트를 발행하고 구독                         │
│                                                             │
│  Order ──"OrderCreated"──▶ Inventory                       │
│                               │                             │
│                    "InventoryReserved"                      │
│                               │                             │
│  Payment ◀────────────────────┘                            │
│     │                                                       │
│     └──"PaymentProcessed"──▶ Shipping                      │
│                                  │                          │
│                       "ShipmentCreated"                     │
│                                  │                          │
│  Order ◀─────────────────────────┘                         │
│                                                             │
│  장점: 느슨한 결합, 단순한 서비스                           │
│  단점: 전체 흐름 파악 어려움, 순환 의존성 위험              │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Orchestration (지휘)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  중앙 Orchestrator가 전체 흐름을 조정                       │
│                                                             │
│              ┌─────────────────┐                           │
│              │   Orchestrator  │                           │
│              │  (Saga Manager) │                           │
│              └────────┬────────┘                           │
│                       │                                     │
│      ┌────────────────┼────────────────┐                   │
│      │                │                │                   │
│      ▼                ▼                ▼                   │
│  ┌───────┐       ┌─────────┐      ┌────────┐             │
│  │ Order │       │Inventory│      │Payment │             │
│  └───────┘       └─────────┘      └────────┘             │
│                                                             │
│  Orchestrator:                                             │
│  1. Order 서비스에 "주문 생성" 명령                        │
│  2. Inventory 서비스에 "재고 예약" 명령                    │
│  3. Payment 서비스에 "결제 처리" 명령                      │
│  4. 실패 시 각 서비스에 "보상" 명령                        │
│                                                             │
│  장점: 전체 흐름 명확, 테스트 용이                         │
│  단점: Orchestrator가 단일 장애점, 결합도 증가             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 개념 정리

| 개념 | 설명 |
|------|------|
| **Saga** | 작은 트랜잭션의 시퀀스 (T1, T2, ..., Tn) |
| **Compensating Transaction** | 각 Ti를 논리적으로 되돌리는 Ci |
| **Backward Recovery** | 실패 시 보상 트랜잭션으로 되돌리기 |
| **Forward Recovery** | 실패 시 재시도하여 앞으로 진행 |
| **Pivot Transaction** | 보상 불가능한 지점, 이후는 반드시 완료 |
| **Semantic Rollback** | 물리적이 아닌 비즈니스 관점의 되돌리기 |

---

## 더 읽을 자료

- [Microservices Patterns - Chapter 4](https://microservices.io/patterns/data/saga.html) - Chris Richardson
- [Life Beyond Distributed Transactions](https://www.cidrdb.org/cidr2007/papers/cidr07p15.pdf) - Pat Helland (2007)
- [Compensating Action](https://martinfowler.com/eaaDev/CompensatingAction.html) - Martin Fowler

---

## 부록: Eco² 적용 포인트

### Scan → Character → My 보상 트랜잭션

Eco²의 AI 분류 파이프라인을 Saga로 모델링:

```
┌─────────────────────────────────────────────────────────────┐
│              Eco² Scan Saga                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  정상 흐름:                                                 │
│                                                             │
│  T1: Vision Scan     T2: Rule Match     T3: Answer Gen      │
│  ┌─────────┐        ┌─────────┐        ┌─────────┐        │
│  │ GPT-4   │───────▶│ 규칙    │───────▶│ 답변    │        │
│  │ Vision  │        │ 매칭    │        │ 생성    │        │
│  └─────────┘        └─────────┘        └─────────┘        │
│       │                  │                  │              │
│       ✓                  ✓                  ✓              │
│                                             │              │
│  T4: Reward Grant       T5: Stats Update   │              │
│  ┌─────────┐           ┌─────────┐        │              │
│  │Character│◀──────────│   My    │◀───────┘              │
│  │ +points │           │  +scan  │                        │
│  └─────────┘           └─────────┘                        │
│                                                             │
│  T4 실패 시 (Character 서비스 장애):                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 옵션 1: Forward Recovery (재시도)                    │   │
│  │   → DLQ에 저장                                       │   │
│  │   → 서비스 복구 후 재처리                            │   │
│  │   → 사용자에게 "보상 지연 중" 알림                   │   │
│  │                                                     │   │
│  │ 옵션 2: Backward Recovery (보상)                     │   │
│  │   → C3: 답변 결과 무효화                            │   │
│  │   → C2: 매칭 결과 무효화                            │   │
│  │   → C1: 분류 결과 무효화                            │   │
│  │   → 사용자에게 "분류 실패" 알림                     │   │
│  │                                                     │   │
│  │ 선택: Forward Recovery 권장                         │   │
│  │   이유: 분류 결과는 유효, 보상만 지연               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 보상 트랜잭션 구현

```python
# domains/scan/tasks/compensation.py

from celery import chain
from domains._shared.taskqueue.app import celery_app

# 각 단계의 보상 트랜잭션 정의
COMPENSATIONS = {
    "vision_scan": "compensate_vision_scan",
    "rule_match": "compensate_rule_match", 
    "answer_gen": "compensate_answer_gen",
    "reward_grant": "compensate_reward_grant",
}


@celery_app.task(bind=True)
def compensate_vision_scan(self, task_id: str, reason: str):
    """T1 보상: Vision 분석 결과 무효화"""
    logger.info(f"Compensating vision_scan for {task_id}: {reason}")
    
    # Redis 상태 업데이트
    await state_manager.update(
        task_id,
        status=TaskStatus.COMPENSATED,
        metadata={"compensation_reason": reason},
    )
    
    # 분석 결과 논리적 삭제 (soft delete)
    await db.execute(
        "UPDATE scan_results SET status = 'compensated' WHERE task_id = :id",
        {"id": task_id}
    )


@celery_app.task(bind=True)
def compensate_reward_grant(self, task_id: str, user_id: str, reason: str):
    """T4 보상: 지급된 보상 회수"""
    logger.info(f"Compensating reward for {task_id}: {reason}")
    
    # Character 서비스에 보상 회수 요청
    # (멱등성 키로 중복 회수 방지)
    idempotency_key = f"compensate-reward-{task_id}"
    
    await character_client.revoke_reward(
        user_id=user_id,
        task_id=task_id,
        idempotency_key=idempotency_key,
        reason=reason,
    )


def execute_backward_recovery(task_id: str, failed_step: str, reason: str):
    """Backward Recovery 실행"""
    
    # 실행된 단계들 역순으로 보상
    steps = ["vision_scan", "rule_match", "answer_gen", "reward_grant"]
    failed_index = steps.index(failed_step)
    
    compensation_chain = []
    for step in reversed(steps[:failed_index]):
        compensation_task = COMPENSATIONS[step]
        compensation_chain.append(
            celery_app.signature(compensation_task, args=[task_id, reason])
        )
    
    # 보상 체인 실행
    chain(*compensation_chain).apply_async()
```

### Saga 상태 관리

```python
# domains/scan/tasks/saga_state.py

from enum import Enum
from dataclasses import dataclass
from typing import Optional

class SagaStatus(str, Enum):
    STARTED = "started"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"


@dataclass
class SagaState:
    """Saga 실행 상태"""
    saga_id: str
    status: SagaStatus
    current_step: int
    completed_steps: list[str]
    failed_step: Optional[str] = None
    error_message: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "status": self.status.value,
            "current_step": self.current_step,
            "completed_steps": self.completed_steps,
            "failed_step": self.failed_step,
            "error_message": self.error_message,
        }


class SagaManager:
    """Saga Orchestrator"""
    
    async def start_saga(self, saga_id: str, steps: list[str]) -> SagaState:
        state = SagaState(
            saga_id=saga_id,
            status=SagaStatus.STARTED,
            current_step=0,
            completed_steps=[],
        )
        await self._save_state(state)
        return state
    
    async def complete_step(self, saga_id: str, step: str) -> SagaState:
        state = await self._load_state(saga_id)
        state.completed_steps.append(step)
        state.current_step += 1
        state.status = SagaStatus.PROCESSING
        await self._save_state(state)
        return state
    
    async def fail_step(self, saga_id: str, step: str, error: str) -> SagaState:
        state = await self._load_state(saga_id)
        state.failed_step = step
        state.error_message = error
        state.status = SagaStatus.COMPENSATING
        await self._save_state(state)
        return state
```

### Garcia-Molina 원칙의 Eco² 적용 (Command-Event Separation)

```
┌─────────────────────────────────────────────────────────────┐
│      Eco² Scan Saga (Command-Event Separation)               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  AI 파이프라인 (RabbitMQ + Celery = Command)                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  vision_scan → rule_match → answer_gen              │   │
│  │       │            │             │                  │   │
│  │       ▼            ▼             ▼                  │   │
│  │   [Redis]      [Redis]       [Redis]                │   │
│  │   상태 업데이트  상태 업데이트   상태 업데이트         │   │
│  │       │            │             │                  │   │
│  │       └────────────┴─────────────┘                  │   │
│  │                    │                                │   │
│  │                    │ 완료 시                        │   │
│  │                    ▼                                │   │
│  │              Event Store                            │   │
│  │           (ScanCompleted)                           │   │
│  │                    │                                │   │
│  │                    ▼ CDC                            │   │
│  └────────────────────┼────────────────────────────────┘   │
│                       │                                     │
│  도메인 이벤트 (Kafka = Event)                              │
│  ┌────────────────────▼────────────────────────────────┐   │
│  │              eco2.events.scan                        │   │
│  └────────────────────┬────────────────────────────────┘   │
│                       │                                     │
│  Character            │     My Context                     │
│  ┌────────────────────▼─────┐  ┌───────────────────────┐   │
│  │ Consumer: ScanCompleted  │  │ Consumer: All Events  │   │
│  │        │                 │  │        │              │   │
│  │        ▼                 │  │        ▼              │   │
│  │ CharacterGranted 발행    │  │ Projection 업데이트   │   │
│  └──────────────────────────┘  └───────────────────────┘   │
│                                                             │
│  실패 시:                                                   │
│  Celery Task 실패 → DLQ + 재시도                           │
│  도메인 이벤트 처리 실패 → Kafka Consumer 재처리           │
│  Backward Recovery → ScanFailed 이벤트 발행                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### AI 파이프라인 Saga (Celery Task Chain)

```python
# domains/scan/tasks/ai_pipeline.py

@celery_app.task(bind=True, max_retries=3)
def vision_scan(self, task_id: str, image_url: str):
    """Saga Step 1: Vision 분석 (Celery Task)"""
    try:
        redis.hset(f"task:{task_id}", "step", "vision")
        result = vision_api.analyze(image_url)
        redis.hset(f"task:{task_id}", "vision_result", json.dumps(result))
        return result
    except Exception as exc:
        # Celery 자동 재시도
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)


@celery_app.task(bind=True, max_retries=3)
def answer_gen(self, prev_result: dict, task_id: str):
    """Saga Step 3: Answer 생성 + Event 발행"""
    try:
        answer = llm_api.generate(prev_result)
        
        # Saga 완료 → Event Store 저장 (Kafka 발행 트리거)
        async with db.begin():
            task = await event_store.load(ScanTask, task_id)
            task.complete(prev_result["classification"], answer)
            await event_store.save(task, task.collect_events())
        
        redis.hset(f"task:{task_id}", "status", "completed")
        return answer
        
    except Exception as exc:
        # 실패 시 Saga 보상 트리거
        await trigger_compensation(task_id, str(exc))
        raise
```

### Compensation (Celery DLQ + Kafka Event)

```python
# domains/scan/tasks/compensation.py

async def trigger_compensation(task_id: str, reason: str):
    """Saga 보상 트리거"""
    
    async with db.begin():
        task = await event_store.load(ScanTask, task_id)
        task.fail(reason)  # ScanFailed 이벤트 발행
        await event_store.save(task, task.collect_events())
    
    # CDC → Kafka → Character Consumer가 보상 처리


# domains/character/consumers/compensation_handler.py

class CompensationHandler:
    """Kafka Consumer - ScanFailed 이벤트 처리"""
    
    async def handle_scan_failed(self, event: ScanFailed):
        grants = await self.find_grants_by_task(event.task_id)
        
        for grant in grants:
            user_char = await self.load(UserCharacter, grant.user_id)
            user_char.revoke_character(grant.character_id, event.reason)
            await self.save(user_char)
```

| 원칙 | AS-IS (gRPC) | TO-BE (Command-Event Separation) |
|------|-------------|-------------------|
| **트랜잭션 분해** | gRPC 순차 호출 | Celery Chain + Kafka Event |
| **Saga 유형** | N/A | Orchestration (Celery) + Choreography (Kafka) |
| **Forward Recovery** | Circuit Breaker | Celery Retry + Kafka Consumer |
| **Backward Recovery** | 수동 처리 | ScanFailed → Compensation Consumer |
| **Pivot Transaction** | 없음 (실패 시 손실) | CharacterGranted Event |
| **Semantic Rollback** | N/A | CharacterRevoked 이벤트 |
| **상태 추적** | 없음 | Redis (Task) + Event Store (Domain) |
| **DLQ** | 없음 | Celery DLQ + Kafka DLQ Topic |
