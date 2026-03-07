# Event Sourcing: 상태 대신 이벤트를 저장하라

> 원문: [Event Sourcing](https://martinfowler.com/eaaDev/EventSourcing.html) - Martin Fowler

---

## 들어가며

우리가 만드는 대부분의 애플리케이션은 "현재 상태"를 저장한다. 사용자의 잔액이 10만원이면, 데이터베이스에 `balance = 100000`이라고 저장한다. 간단하고 직관적이다.

하지만 이 방식에는 치명적인 한계가 있다: **"왜 잔액이 10만원인가?"**라는 질문에 답할 수 없다. 처음에 50만원이 있었는데 40만원을 출금해서? 아니면 0원에서 10만원을 입금해서? 알 수 없다.

**Event Sourcing**은 이 문제를 해결하는 패턴이다. 현재 상태 대신 **"상태를 변경한 모든 이벤트"**를 저장한다. 그러면 "왜?"라는 질문에 언제든 답할 수 있다.

---

## 핵심 아이디어

### 상태가 아닌 이벤트를 저장

일반적인 CRUD 방식과 Event Sourcing의 차이를 은행 계좌로 비교해보자:

```
┌─────────────────────────────────────────────────────────────┐
│                    CRUD 방식 (상태 저장)                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  시간 T0: { balance: 500,000 }  ← 초기 잔액                 │
│  시간 T1: { balance: 450,000 }  ← 50,000원 출금? 이체?       │
│  시간 T2: { balance: 600,000 }  ← 150,000원 입금? 어디서?    │
│  시간 T3: { balance: 580,000 }  ← 20,000원 수수료? 출금?     │
│                                                             │
│  최종 잔액은 알지만, 어떻게 이 금액이 되었는지 알 수 없다.      │
│  → 이전 상태는 덮어쓰기 되어 사라짐                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                Event Sourcing (이벤트 저장)                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Event Store:                                               │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ #1 계좌개설 { initial: 500,000 }                     │   │
│  │ #2 출금 { amount: 50,000, reason: "ATM 출금" }       │   │
│  │ #3 입금 { amount: 150,000, from: "급여" }            │   │
│  │ #4 이체 { amount: 20,000, to: "휴대폰요금" }         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  현재 잔액 = 500,000 - 50,000 + 150,000 - 20,000            │
│           = 580,000원                                       │
│                                                             │
│  모든 변경 이력이 보존되어 있어 추적 가능!                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Event Sourcing에서 현재 상태는 **저장되지 않는다**. 대신 이벤트를 처음부터 차례로 재생(replay)하여 **계산**한다.

### Martin Fowler의 Ship 예제

원문에서 Martin Fowler는 배(Ship) 추적 시스템을 예로 든다. 항구에 배가 도착하고 출발하는 것을 추적하는 시스템이다:

```
┌─────────────────────────────────────────────────────────────┐
│               Ship Tracking with Event Sourcing              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이벤트 스토어 (Ship: "세종대왕호")                          │
│                                                             │
│  [1] 2024-01-01 09:00 - 부산항 도착 (Arrived)               │
│  [2] 2024-01-03 14:00 - 부산항 출발 (Departed)              │
│  [3] 2024-01-05 10:00 - 인천항 도착 (Arrived)               │
│  [4] 2024-01-08 16:00 - 인천항 출발 (Departed)              │
│  [5] 2024-01-10 11:00 - 목포항 도착 (Arrived)               │
│                                                             │
│  현재 위치 조회:                                             │
│  → 마지막 Arrived 이벤트 = 목포항                           │
│                                                             │
│  2024-01-06 시점의 위치 조회:                                │
│  → [1]~[3]까지 재생 = 인천항                                │
│                                                             │
│  부산항에 머문 시간:                                         │
│  → [1]과 [2] 사이 = 2일 5시간                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

이벤트를 저장하면 **시간 여행**이 가능해진다. "1월 6일에 배가 어디 있었지?"라는 질문에 답할 수 있다.

---

## Event Sourcing의 강점

### 1. 완벽한 감사 추적 (Audit Trail)

이벤트가 모두 저장되어 있으므로, 어떤 변경이든 **누가, 언제, 무엇을, 왜** 했는지 추적할 수 있다.

이것이 금융 시스템에서 Event Sourcing이 사실상 표준인 이유다:
- 금융 감독원: "3개월 전 이 거래 내역을 설명하세요"
- 고객 민원: "내가 이체한 적 없는데 왜 돈이 빠졌죠?"
- 법적 분쟁: "당시 계좌 상태가 정확히 어땠습니까?"

모두 이벤트 로그를 조회하면 답할 수 있다.

### 2. 시간 여행 (Temporal Query)

과거 어느 시점의 상태든 복원할 수 있다:

```python
def get_state_at(events: list, target_time: datetime) -> Account:
    """특정 시점의 계좌 상태 복원"""
    account = Account()
    
    for event in events:
        if event.timestamp <= target_time:
            account.apply(event)
        else:
            break  # target_time 이후 이벤트는 무시
    
    return account

# 사용 예
state = get_state_at(all_events, datetime(2024, 1, 6))
print(f"1월 6일 잔액: {state.balance}")
```

이 기능은 다음과 같은 상황에서 유용하다:
- 버그 발생 시점의 상태 재현
- "만약 이 이벤트가 없었다면?" 시뮬레이션
- 과거 데이터 기반 리포트 생성

### 3. 이벤트 재생 (Replay)

버그가 발견되면, 코드를 수정한 후 **모든 이벤트를 다시 재생**하여 올바른 상태를 계산할 수 있다:

```
┌─────────────────────────────────────────────────────────────┐
│                    버그 수정 후 재생                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  문제 발견: 출금 수수료 계산 버그                             │
│  - 기존 코드: 수수료 0.1% (잘못됨)                           │
│  - 올바른 코드: 수수료 0.05%                                 │
│                                                             │
│  해결 방법:                                                  │
│  1. 수수료 계산 코드 수정                                    │
│  2. 모든 계좌의 이벤트를 처음부터 재생                        │
│  3. 올바른 현재 상태 계산                                    │
│                                                             │
│  for account in all_accounts:                               │
│      events = event_store.get_events(account.id)            │
│      new_state = Account()                                  │
│      for event in events:                                   │
│          new_state.apply(event)  # 수정된 로직으로 적용       │
│      save_corrected_state(new_state)                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

CRUD 방식이었다면? 이미 잘못된 값으로 덮어쓰여서 복구가 불가능하다.

### 4. 소급 이벤트 처리 (Retroactive Events)

실무에서 흔한 상황: "어제 발생한 이벤트인데, 오늘에야 알게 됐어요"

Event Sourcing에서는 이런 **소급 이벤트**도 처리할 수 있다:

```
┌─────────────────────────────────────────────────────────────┐
│                  소급 이벤트 처리                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  현재 시간: 1월 15일                                         │
│                                                             │
│  기존 이벤트:                                                │
│  [1] 1월 1일 - 부산 도착                                    │
│  [2] 1월 5일 - 부산 출발                                    │
│  [3] 1월 10일 - 인천 도착                                   │
│                                                             │
│  뒤늦게 발견: "1월 3일에 부산항에서 정비를 받았음"            │
│                                                             │
│  해결:                                                      │
│  1. 새 이벤트 추가: [1.5] 1월 3일 - 정비 완료                │
│  2. 전체 이벤트 재정렬                                       │
│  3. 영향받는 모든 상태 재계산                                │
│                                                             │
│  CRUD라면? 과거로 돌아가서 상태를 수정하는 게 매우 복잡함     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 외부 시스템 호출 문제

### 결정론적 재생의 어려움

Event Sourcing의 중요한 전제: 같은 이벤트를 재생하면 같은 결과가 나와야 한다 (결정론적).

하지만 외부 API 호출이 있으면 문제가 생긴다:

```
┌─────────────────────────────────────────────────────────────┐
│                   외부 API 호출 문제                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이벤트: "USD로 100달러 입금"                                │
│  처리 시 외부 API 호출: 현재 환율 조회                        │
│                                                             │
│  최초 처리 (1월 1일):                                        │
│    환율 API 응답: $1 = ₩1,300                               │
│    결과: 130,000원 입금                                      │
│                                                             │
│  재생 (1월 15일):                                            │
│    환율 API 응답: $1 = ₩1,350  ← 환율이 바뀜!               │
│    결과: 135,000원 입금  ← 다른 결과!                        │
│                                                             │
│  → 재생할 때마다 결과가 달라지면 Event Sourcing 의미 없음     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 해결책: Gateway 이벤트

외부 시스템 응답도 이벤트로 저장한다:

```
┌─────────────────────────────────────────────────────────────┐
│                 Gateway 이벤트 패턴                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이벤트 스토어:                                              │
│  [1] USDDepositRequested { amount: 100 }                   │
│  [2] ExchangeRateReceived { rate: 1300, source: "API" }    │
│  [3] DepositCompleted { krw_amount: 130000 }               │
│                                                             │
│  재생 시:                                                   │
│  - [1] 처리: USD 입금 요청 확인                              │
│  - [2] 처리: 저장된 환율 1300 사용 (API 호출 안 함!)         │
│  - [3] 처리: 130,000원 입금 완료                            │
│                                                             │
│  → 언제 재생해도 동일한 결과                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

핵심: **외부 시스템의 응답 자체를 이벤트로 저장**하면, 재생 시 외부 시스템을 다시 호출할 필요가 없다.

---

## 성능 문제와 스냅샷

### 이벤트가 쌓이면?

이벤트가 100만 개 쌓인 계좌의 현재 잔액을 조회한다고 생각해보자. 매번 100만 개의 이벤트를 재생해야 할까?

그건 너무 비효율적이다. 해결책은 **스냅샷(Snapshot)**이다.

### 스냅샷 전략

주기적으로 현재 상태를 스냅샷으로 저장해두고, 재생 시 가장 최근 스냅샷부터 시작한다:

```
┌─────────────────────────────────────────────────────────────┐
│                    스냅샷 활용                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  이벤트: [1] [2] [3] ... [999,000] [S] [999,001] ... [1M]   │
│                              ↑                              │
│                           스냅샷                            │
│                    (999,000번째 상태 저장)                   │
│                                                             │
│  현재 상태 조회:                                             │
│  1. 스냅샷 [S] 로드                                         │
│  2. [999,001] ~ [1M] 이벤트만 재생 (1,000개)                │
│  3. 완료                                                    │
│                                                             │
│  1,000,000개 재생 → 1,000개 재생으로 단축!                   │
│                                                             │
│  스냅샷 생성 전략:                                           │
│  - 이벤트 N개마다 자동 생성                                  │
│  - 또는 주기적으로 (매시간, 매일)                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 스냅샷 구현 예시

```python
class EventSourcedAccount:
    def __init__(self):
        self.balance = 0
        self.version = 0
    
    def apply(self, event):
        if event.type == "Deposited":
            self.balance += event.amount
        elif event.type == "Withdrawn":
            self.balance -= event.amount
        self.version += 1
    
    def to_snapshot(self):
        return {
            "balance": self.balance,
            "version": self.version
        }
    
    @classmethod
    def from_snapshot(cls, snapshot):
        account = cls()
        account.balance = snapshot["balance"]
        account.version = snapshot["version"]
        return account

# 상태 로드
def load_account(account_id):
    # 1. 최신 스냅샷 로드
    snapshot = snapshot_store.get_latest(account_id)
    
    if snapshot:
        account = EventSourcedAccount.from_snapshot(snapshot)
        from_version = snapshot["version"] + 1
    else:
        account = EventSourcedAccount()
        from_version = 0
    
    # 2. 스냅샷 이후 이벤트만 재생
    events = event_store.get_events(account_id, from_version)
    for event in events:
        account.apply(event)
    
    return account
```

---

## 이벤트 스키마 변경 문제

### 이벤트는 불변

Event Sourcing에서 저장된 이벤트는 **절대 수정하면 안 된다**. 이벤트는 "과거에 일어난 사실"을 기록한 것이기 때문이다.

하지만 시스템은 진화한다. 이벤트 스키마도 바뀔 수 있다:

```
V1: MoneyDeposited { amount: 100 }
V2: MoneyDeposited { amount: 100, currency: "KRW" }  // 통화 필드 추가
```

### Upcasting으로 해결

과거 이벤트를 새 버전으로 "업캐스팅"한다:

```python
def upcast_event(event):
    """과거 버전 이벤트를 현재 버전으로 변환"""
    
    if event.type == "MoneyDeposited" and event.version == 1:
        # V1 → V2 변환
        return MoneyDepositedV2(
            amount=event.amount,
            currency="KRW",  # 기본값 적용
            version=2
        )
    
    return event

# 재생 시
for raw_event in stored_events:
    event = upcast_event(raw_event)  # 업캐스팅
    account.apply(event)
```

핵심: **저장된 이벤트는 그대로 두고**, 읽을 때 변환한다.

---

## Event Sourcing이 적합한 경우

### 사용하면 좋은 상황

| 상황 | 이유 |
|------|------|
| **금융/회계 시스템** | 감사 추적 필수, 모든 거래 기록 보존 의무 |
| **버전 관리 시스템** | Git이 대표적인 Event Sourcing 구현체 |
| **협업 도구** | 변경 이력 추적, 충돌 해결에 유리 |
| **법적 증거가 필요한 시스템** | 언제 무슨 일이 있었는지 증명 필요 |
| **복잡한 도메인 로직** | 상태 변화의 이유를 파악해야 할 때 |

### 피해야 할 상황

| 상황 | 이유 |
|------|------|
| **단순 CRUD** | 과도한 복잡성, 오버엔지니어링 |
| **이력이 의미 없는 데이터** | 예: 캐시 데이터, 임시 데이터 |
| **팀 경험 부족** | 학습 곡선이 높음 |
| **현재 상태만 중요** | 과거 이력이 비즈니스적으로 불필요 |

---

## Event Sourcing과 회계의 유사성

흥미로운 점: Event Sourcing은 **복식부기(Double-Entry Bookkeeping)**와 매우 유사하다.

회계에서는 잔액을 직접 수정하지 않는다. 모든 거래를 **분개장(Journal)**에 기록하고, 잔액은 분개 기록의 합계로 계산한다. 잘못된 기록이 있으면? 역분개(수정 분개)를 추가한다.

```
┌─────────────────────────────────────────────────────────────┐
│               회계와 Event Sourcing 비교                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  회계 (복식부기)              Event Sourcing                 │
│  ─────────────              ─────────────                   │
│  분개장 (Journal)            Event Store                    │
│  분개 기록                   이벤트                          │
│  원장 잔액 (Ledger)          현재 상태 (Projection)          │
│  역분개로 수정               새 이벤트로 수정                 │
│  절대 분개 삭제 안 함         절대 이벤트 삭제 안 함           │
│                                                             │
│  "회계사들은 수백 년 전부터 Event Sourcing을 해왔다"          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 핵심 개념 정리

| 개념 | 설명 |
|------|------|
| **Event Sourcing** | 현재 상태가 아닌 이벤트 시퀀스를 저장 |
| **이벤트 재생** | 이벤트를 순서대로 적용하여 현재 상태 계산 |
| **시간 여행** | 과거 시점까지만 이벤트 재생하여 당시 상태 복원 |
| **스냅샷** | 성능 최적화를 위해 특정 시점의 상태를 저장 |
| **Upcasting** | 과거 이벤트를 새 스키마로 변환 |
| **Gateway 이벤트** | 외부 시스템 응답을 이벤트로 저장하여 결정론적 재생 보장 |

---

## 더 읽을 자료

- [CQRS Documents](https://cqrs.files.wordpress.com/2010/11/cqrs_documents.pdf) - Greg Young
- [Event Sourcing made Simple](https://kickstarter.engineering/event-sourcing-made-simple-4a2625113224) - Kickstarter Engineering
- [Versioning in an Event Sourced System](https://leanpub.com/esversioning) - Greg Young

---

## 부록: Eco² 적용 포인트

### Scan 분류 히스토리

분리배출 분류 결과를 Event Sourcing으로 관리하면:

```python
# 이벤트 예시
@dataclass
class WasteClassificationRequested:
    task_id: UUID
    user_id: UUID
    image_url: str
    timestamp: datetime

@dataclass
class AIClassificationReceived:  # Gateway 이벤트
    task_id: UUID
    model_version: str
    classification: dict  # major, middle, minor
    confidence: float

@dataclass 
class RewardGranted:
    task_id: UUID
    points: int
    character_id: UUID

# 활용
# - "이 사용자가 지금까지 분류한 품목 통계는?"
# - "AI 모델 v2에서 잘못 분류된 건들을 재분류하고 싶다"
# - "특정 날짜에 분류 정확도가 낮았던 이유 분석"
```

### Character 획득 이력

```python
@dataclass
class CharacterGranted:
    user_id: UUID
    character_id: UUID
    source: str  # "scan-reward", "quest", "onboard-default"
    timestamp: datetime

# 활용
# - "이 캐릭터를 어떻게 획득했지?" → 이벤트 조회
# - "부정 획득 의심" → 획득 이벤트 전체 감사
# - "특정 기간 캐릭터 획득 통계" → 시간 범위 이벤트 집계
```

### 외부 API 호출 (GPT)

GPT API 응답을 Gateway 이벤트로 저장하면:

```python
@dataclass
class GPTResponseReceived:  # Gateway 이벤트
    task_id: UUID
    prompt: str
    response: dict
    model: str
    tokens_used: int
    timestamp: datetime

# 장점:
# - 재생 시 GPT API 재호출 불필요 (비용 절감)
# - GPT 응답 결과 분석 가능
# - 결정론적 재생 보장
```
