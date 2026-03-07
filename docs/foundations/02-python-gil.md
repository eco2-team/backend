# Python GIL (Global Interpreter Lock)

> [← 01. Python asyncio](./01-python-asyncio.md) | [인덱스](./00-index.md) | [03. AMQP Protocol →](./03-amqp-protocol.md)

> **공식 문서**: [Global Interpreter Lock](https://docs.python.org/3.11/glossary.html#term-global-interpreter-lock)
> **핵심 PEP**: PEP 703 (Python 3.13+)
> **학술 자료**: OMP4Py (arXiv:2411.14887)

---

## 개요

GIL(Global Interpreter Lock)은 CPython 인터프리터의 **뮤텍스**로, 한 번에 하나의 스레드만 Python 바이트코드를 실행하도록 보장한다.

```
┌─────────────────────────────────────────────────────────────┐
│                    GIL의 역할                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Thread 1 ──────▶ [GIL 획득] ──▶ Python 실행 ──▶ [GIL 해제] │
│                        ↑                                    │
│  Thread 2 ─────────────┼──────── 대기 ────────────▶ 실행    │
│                        │                                    │
│  Thread 3 ─────────────┴───────────── 대기 ────────────────▶│
│                                                             │
│  한 번에 하나의 스레드만 Python 코드 실행 가능              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 공식 문서: GIL 정의

> 출처: [Python Glossary - global interpreter lock](https://docs.python.org/3.11/glossary.html#term-global-interpreter-lock)

### 공식 정의

```
"The mechanism used by the CPython interpreter to assure that only one 
thread executes Python bytecode at a time. This simplifies the CPython 
implementation by making the object model (including critical built-in 
types such as dict) implicitly safe against concurrent access."
```

**번역:**
- CPython 인터프리터가 **한 번에 하나의 스레드만** Python 바이트코드를 실행하도록 보장하는 메커니즘
- 이는 객체 모델(dict 등 중요 내장 타입 포함)을 동시 접근으로부터 **암묵적으로 안전**하게 만든다

### GIL이 필요한 이유

```
┌─────────────────────────────────────────────────────────────┐
│                  GIL의 존재 이유                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 참조 카운팅 (Reference Counting)                        │
│  ───────────────────────────────────                        │
│  Python은 참조 카운팅으로 메모리 관리:                       │
│                                                             │
│  x = []        # refcount = 1                               │
│  y = x         # refcount = 2                               │
│  del x         # refcount = 1                               │
│  del y         # refcount = 0 → 메모리 해제                 │
│                                                             │
│  GIL 없이 멀티스레드에서 refcount 동시 수정 시:             │
│  • Race Condition 발생                                      │
│  • 메모리 누수 또는 조기 해제                               │
│                                                             │
│  2. CPython 구현 단순화                                     │
│  ─────────────────────                                      │
│  • 모든 내장 자료구조가 thread-safe                         │
│  • C 확장 모듈 개발이 단순해짐                              │
│  • 단일 스레드 성능 최적화                                  │
│                                                             │
│  3. C 라이브러리 호환성                                     │
│  ─────────────────────                                      │
│  • 많은 C 라이브러리가 thread-safe하지 않음                 │
│  • GIL이 이를 보호                                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## GIL이 동시성에 미치는 영향

### I/O-bound vs CPU-bound

```
┌─────────────────────────────────────────────────────────────┐
│              I/O-bound vs CPU-bound                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  I/O-bound 작업 (GIL 영향 적음)                             │
│  ──────────────────────────────                             │
│  • 네트워크 요청 대기                                       │
│  • 파일 읽기/쓰기                                           │
│  • 데이터베이스 쿼리                                        │
│                                                             │
│  Thread 1: [Python]──[I/O 대기]────────────────[Python]     │
│  Thread 2: ────────[Python]──[I/O 대기]──[Python]           │
│                                                             │
│  I/O 대기 중에는 GIL을 해제하므로 다른 스레드 실행 가능     │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  CPU-bound 작업 (GIL 영향 큼)                               │
│  ──────────────────────────                                 │
│  • 수학 연산                                                │
│  • 이미지 처리                                              │
│  • 데이터 분석                                              │
│                                                             │
│  Thread 1: [Python 계산][Python 계산][Python 계산]          │
│  Thread 2: ───대기───[Python]───대기───[Python]             │
│                                                             │
│  CPU-bound에서는 멀티스레딩이 오히려 느려질 수 있음         │
│  (GIL 경쟁 + 컨텍스트 스위칭 오버헤드)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 이코에코 분석

```python
# 이코에코 워크로드 분류

# I/O-bound (GIL 영향 적음) ✅
# - FastAPI HTTP 요청 처리
# - asyncpg PostgreSQL 쿼리
# - aioredis Redis 접근
# - httpx 외부 API 호출
# - aio-pika RabbitMQ 통신

# CPU-bound (GIL 영향 큼) ⚠️
# - 이미지 전처리 (Celery Worker에서 처리)
# - JSON 파싱 (작은 데이터는 무시 가능)
# - 비즈니스 로직 계산

# 결론:
# 이코에코는 대부분 I/O-bound → asyncio가 효과적
# CPU-bound는 Celery Worker(멀티프로세스)로 분리
```

---

## C API: GIL 내부 동작

> 출처: [Thread State and the Global Interpreter Lock](https://docs.python.org/3.11/c-api/init.html#thread-state-and-the-global-interpreter-lock)

### GIL 획득/해제 API

```c
// C 확장에서 GIL 관리

// GIL 해제 (I/O 작업 전)
Py_BEGIN_ALLOW_THREADS
// ... 블로킹 I/O 또는 CPU 작업 ...
// 이 구간에서는 다른 Python 스레드 실행 가능
Py_END_ALLOW_THREADS

// 예: asyncpg의 내부 구현
Py_BEGIN_ALLOW_THREADS
result = PQexec(conn, query);  // PostgreSQL 쿼리 실행
Py_END_ALLOW_THREADS
// result를 Python 객체로 변환
```

### GIL 스위칭 간격

```python
# Python 3.2 이전: 100 바이트코드 명령마다 GIL 해제
# Python 3.2 이후: 5ms(기본) 간격으로 GIL 해제

import sys

# GIL 스위칭 간격 확인 (초 단위)
print(sys.getswitchinterval())  # 0.005 (5ms)

# 간격 변경 (권장하지 않음)
sys.setswitchinterval(0.001)  # 1ms
```

---

## PEP 703: GIL을 Optional로

> 원문: [PEP 703 - Making the Global Interpreter Lock Optional in CPython](https://peps.python.org/pep-0703/)
> 저자: Sam Gross
> 상태: Accepted (Python 3.13+, 실험적)

### 핵심 내용

```
┌─────────────────────────────────────────────────────────────┐
│                    PEP 703 요약                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  목표: CPython에서 GIL을 선택적으로 비활성화                │
│                                                             │
│  Python 3.13 (2024.10):                                     │
│  • --disable-gil 빌드 옵션 도입 (실험적)                    │
│  • free-threading 모드 지원                                 │
│                                                             │
│  Python 3.14+ (예정):                                       │
│  • 점진적 안정화                                            │
│  • C 확장 호환성 개선                                       │
│                                                             │
│  기술적 변경:                                               │
│  1. 참조 카운팅 → 지연 참조 카운팅 (deferred refcounting)  │
│  2. 바이어스드 참조 카운팅 (biased reference counting)     │
│  3. 불멸 객체 (immortal objects)                           │
│  4. 스레드별 GC                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Free-Threading 빌드

```bash
# Python 3.13+ free-threading 빌드
./configure --disable-gil
make

# 또는 공식 바이너리 (3.13+)
python3.13t  # 't' suffix = free-threaded build
```

### 성능 영향

```
┌─────────────────────────────────────────────────────────────┐
│              Free-Threading 성능 특성                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  CPU-bound 멀티스레딩 (free-threading 장점):               │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Threads: 1    2    4    8   16                    │    │
│  │  GIL:     1x   1x   1x   1x   1x  (스케일 안함)   │    │
│  │  No-GIL:  1x   2x   4x   8x  16x  (선형 스케일)   │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  단일 스레드 오버헤드:                                      │
│  ┌────────────────────────────────────────────────────┐    │
│  │  PEP 703 구현: ~5-10% 단일 스레드 성능 저하        │    │
│  │  원인: 참조 카운팅 atomic 연산                     │    │
│  │  최적화 진행 중 (Python 3.14+)                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  이코에코 영향:                                             │
│  • I/O-bound → asyncio 이미 효과적, 변화 적음              │
│  • CPU-bound → Celery 멀티프로세스로 이미 해결              │
│  • Python 3.14+ 안정화 후 검토 예정                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## OMP4Py 논문

> 원문: [OMP4Py: A Pure Python Implementation of OpenMP](https://arxiv.org/abs/2411.14887)
> 저자: Sergio Sánchez Ramírez et al.
> 출처: arXiv, 2024.11

### 핵심 내용

```
┌─────────────────────────────────────────────────────────────┐
│                   OMP4Py 논문 요약                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  배경:                                                      │
│  • Python은 전통적인 HPC 언어(C, C++, Fortran) 대비 성능 낮음│
│  • GIL로 인해 멀티스레딩 효율성 제한                        │
│  • Python 3.13 free-threading으로 새로운 가능성             │
│                                                             │
│  OMP4Py란:                                                  │
│  • OpenMP의 지시문 기반 병렬화를 Python에 도입              │
│  • 데코레이터 기반 API 제공                                 │
│  • free-threading 환경에서 진정한 병렬 실행                 │
│                                                             │
│  @omp.parallel                                              │
│  def parallel_work():                                       │
│      # 여러 스레드에서 병렬 실행                            │
│      pass                                                   │
│                                                             │
│  벤치마크 결과:                                             │
│  • free-threading 환경에서 선형에 가까운 스케일링           │
│  • Numba/Cython 없이 순수 Python으로 병렬화 가능            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 시사점

```
┌─────────────────────────────────────────────────────────────┐
│                이코에코에 대한 시사점                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  현재 (Python 3.11):                                        │
│  • GIL 존재 → CPU-bound는 멀티프로세스 필수                 │
│  • Celery prefork pool로 해결 중                            │
│                                                             │
│  미래 (Python 3.14+):                                       │
│  • free-threading 안정화 시                                 │
│  • CPU-bound 작업도 멀티스레딩 가능                         │
│  • Celery → 스레드 기반 Worker 검토 가능                    │
│                                                             │
│  권장 전략:                                                 │
│  1. 현재: asyncio + Celery prefork 유지                     │
│  2. Python 3.14 출시 후 벤치마크                            │
│  3. free-threading 안정화 확인 후 점진적 적용               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 이코에코 적용

### 현재 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│              이코에코 GIL 대응 전략                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  FastAPI (I/O-bound) → asyncio                              │
│  ─────────────────────────────                              │
│  • 단일 프로세스 내 Event Loop                              │
│  • GIL 해제 시점에 I/O 대기                                 │
│  • 수천 동시 연결 처리 가능                                 │
│                                                             │
│  Celery Worker → prefork (⚠️ 한계 존재)                     │
│  ─────────────────────────────────────                      │
│  • 멀티프로세스로 GIL 우회                                  │
│  • 각 프로세스가 독립적인 GIL 보유                          │
│  • ⚠️ I/O-bound 워크로드에서는 효과 없음 (아래 참조)        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                                                     │   │
│  │  [Uvicorn Process]                                  │   │
│  │   └── asyncio Event Loop (GIL 영향 적음)           │   │
│  │        └── FastAPI                                  │   │
│  │             └── async def endpoints                 │   │
│  │                                                     │   │
│  │  [Celery Worker Process 1] (독립 GIL)              │   │
│  │   └── Task (I/O 대기 중 블로킹됨!)                  │   │
│  │                                                     │   │
│  │  [Celery Worker Process 2] (독립 GIL)              │   │
│  │   └── Task (I/O 대기 중 블로킹됨!)                  │   │
│  │                                                     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### ⚠️ 한계점: prefork + I/O-bound 워크로드

> 📊 **실측 데이터**: 2025-12-24 Prometheus 메트릭 기반
> 🔗 [Grafana Snapshot](https://snapshots.raintank.io/dashboard/snapshot/zz5pBgaMfZXuPDf7TwSLYgcMw103UZUE)

**이론 vs 현실:**

| 가정 | 현실 |
|------|------|
| Celery Task가 CPU-bound | **실제로는 I/O-bound** (OpenAI API 호출) |
| prefork가 GIL 우회로 성능 향상 | **I/O 대기 중에는 GIL이 이미 해제됨** |
| 멀티프로세스로 병렬 처리 | **각 Worker가 I/O 대기 중 블로킹** |

**실측 스테이지별 소요 시간:**

```
┌────────────────────────────────────────────────────────────┐
│              Stage 소요 시간 (평균, 2025-12-24)              │
├────────────────────────────────────────────────────────────┤
│                                                            │
│  answer ████████████████████████████████████  14.13초 35%  │
│  vision ██████████████████████████████        12.25초 30%  │
│  rule   █████████████████████                  8.40초 21%  │
│  reward █████████████                          5.38초 14%  │
│                                                            │
│  총 소요 시간: ~40.16초 (Chain 평균: 41.65초)               │
│  OpenAI API 호출 (vision + answer): 65% ← I/O-bound!       │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**prefork의 문제점:**

```
┌─────────────────────────────────────────────────────────────┐
│              prefork + I/O-bound = 비효율                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1 request → 1 worker → 41.65초 블로킹 (I/O 대기)           │
│                                                             │
│  ┌──────────────────────────────────────────┐               │
│  │ Worker 1: ████████████████████████████ 41s (블로킹)     │
│  │ Worker 2:              ████████████████████████ 41s     │
│  │ Worker 3:                           █████████████ 41s   │
│  │           ↑                         ↑                   │
│  │           t=0                       t=41s               │
│  └──────────────────────────────────────────┘               │
│                                                             │
│  실측 결과:                                                 │
│  • 9 workers (메모리 제한으로 24개 중 일부)                 │
│  • 이론 최대: 9 / 41.65초 = 0.22 RPS                       │
│  • 실측: 0.0323 RPS (이론의 15%)                           │
│  • RPM: 1.94 RPM                                           │
│                                                             │
│  ⚠️ GIL 우회가 아닌, asyncio Pool로 I/O 병렬화 필요        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**결론:**
- prefork는 **CPU-bound 작업**에만 GIL 우회 효과 있음
- 이코에코의 Celery Task는 **65%가 OpenAI API 호출** (I/O-bound)
- I/O 대기 중에는 GIL이 이미 해제되므로 **prefork의 이점 없음**
- **해결책**: `celery-pool-asyncio`로 100+ 동시 I/O 처리

### Celery Worker 설정

```python
# domains/_shared/celery/config.py

class CelerySettings(BaseSettings):
    # Worker settings
    worker_concurrency: int = Field(
        2,
        description="Number of concurrent worker processes",
    )
    # prefork pool = 멀티프로세스 (GIL 우회)
    # 기본값이 prefork
```

### 동기 코드를 비동기 컨텍스트에서 실행

```python
# domains/_shared/celery/async_support.py

def run_async(coro: Coroutine[None, None, T]) -> T:
    """공유 event loop에서 코루틴 실행.
    
    Celery task 내에서 비동기 함수를 호출할 때 사용.
    """
    global _event_loop
    
    if _event_loop is None:
        logger.warning("Event loop not initialized, creating temporary loop")
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    return _event_loop.run_until_complete(coro)
```

---

## 요약

| 항목 | 설명 |
|------|------|
| **GIL이란?** | 한 번에 하나의 스레드만 Python 바이트코드 실행 보장 |
| **존재 이유** | 참조 카운팅 보호, CPython 구현 단순화 |
| **I/O-bound 영향** | 적음 (I/O 대기 중 GIL 해제) |
| **CPU-bound 영향** | 큼 (멀티스레딩 효과 없음) |
| **해결책** | asyncio (I/O), 멀티프로세스 (CPU) |
| **미래** | PEP 703 free-threading (Python 3.13+) |
| **⚠️ 이코에코 한계** | prefork는 I/O-bound에 무효, asyncio Pool 필요 |

---

## 참고 자료

### 공식 문서
- [Global Interpreter Lock](https://docs.python.org/3.11/glossary.html#term-global-interpreter-lock)
- [Thread State and the GIL](https://docs.python.org/3.11/c-api/init.html#thread-state-and-the-global-interpreter-lock)
- [Python 3.13 What's New - Free-threaded CPython](https://docs.python.org/3.13/whatsnew/3.13.html#free-threaded-cpython)

### PEP
- [PEP 703 - Making the Global Interpreter Lock Optional](https://peps.python.org/pep-0703/)

### 학술 자료
- [OMP4Py: A Pure Python Implementation of OpenMP](https://arxiv.org/abs/2411.14887)

### 관련 Foundation
- [01-python-asyncio.md](./01-python-asyncio.md) - asyncio로 I/O-bound 해결
- [04-concurrency-patterns.md](./04-concurrency-patterns.md) - Celery prefork로 CPU-bound 해결

