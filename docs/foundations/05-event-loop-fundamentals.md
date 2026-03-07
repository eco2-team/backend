# Event Loop 근원 개념

> [← 인덱스](./00-index.md) | [04. Concurrency Patterns ←](./04-concurrency-patterns.md) | [06. Concurrency Models →](./06-concurrency-models.md)

> **핵심 질문**: Event Loop란 무엇이며, 왜 서로 다른 Event Loop는 충돌하는가?

---

## 개요

Event Loop는 **비동기 I/O의 핵심**이다. 
단일 스레드에서 여러 I/O 작업을 동시에 처리하는 메커니즘이다.

```
┌─────────────────────────────────────────────────────────────┐
│                    Event Loop의 본질                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  "무한 루프 안에서 I/O 이벤트를 감지하고,                    │
│   해당 이벤트에 등록된 콜백을 실행한다"                       │
│                                                             │
│  while True:                                                │
│      events = wait_for_io_events()  # OS에 위임             │
│      for event in events:                                   │
│          callback = get_callback(event)                     │
│          callback()                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 1. OS 수준 I/O Multiplexing

Event Loop의 핵심은 **OS가 제공하는 I/O Multiplexing API**에 있다.

### 1.1 I/O Multiplexing이란?

여러 개의 파일 디스크립터(소켓, 파일 등)를 **하나의 스레드에서 동시에 감시**하는 기술.

```
┌─────────────────────────────────────────────────────────────┐
│              I/O Multiplexing 개념                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  전통적 방식 (Blocking I/O):                                 │
│  ───────────────────────────                                │
│  Thread 1: socket.recv()  ████████████████ (블로킹)         │
│  Thread 2: socket.recv()  ████████████████ (블로킹)         │
│  Thread 3: socket.recv()  ████████████████ (블로킹)         │
│                                                             │
│  → 연결당 1 스레드 필요 (C10K 문제)                          │
│                                                             │
│  ───────────────────────────────────────────────────────    │
│                                                             │
│  I/O Multiplexing:                                          │
│  ─────────────────                                          │
│  Thread 1: epoll_wait([fd1, fd2, fd3])                      │
│            │                                                │
│            ▼                                                │
│       [fd1 ready] → process fd1                             │
│       [fd3 ready] → process fd3                             │
│            ...                                              │
│                                                             │
│  → 1 스레드로 수천 개 연결 처리                              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 OS별 I/O Multiplexing API

| API | OS | 특징 | 시간 복잡도 |
|-----|-----|------|------------|
| **select** | 모든 OS | 가장 오래됨, FD 1024개 제한 | O(n) |
| **poll** | POSIX | select 개선, FD 제한 없음 | O(n) |
| **epoll** | Linux | Edge/Level trigger, 효율적 | O(1) |
| **kqueue** | BSD/macOS | epoll과 유사 | O(1) |
| **IOCP** | Windows | Completion Port 모델 | O(1) |

### 1.3 epoll 동작 원리 (Linux)

```
┌─────────────────────────────────────────────────────────────┐
│                    epoll 동작 원리                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. epoll 인스턴스 생성                                      │
│     epfd = epoll_create()                                   │
│                                                             │
│  2. 감시할 FD 등록                                           │
│     epoll_ctl(epfd, EPOLL_CTL_ADD, socket_fd, events)      │
│                                                             │
│  3. 이벤트 대기 (블로킹)                                     │
│     n = epoll_wait(epfd, events, max_events, timeout)       │
│          │                                                  │
│          │  ← 커널이 ready FD를 알려줌                       │
│          ▼                                                  │
│                                                             │
│  4. Ready FD 처리                                           │
│     for i in range(n):                                      │
│         fd = events[i].data.fd                              │
│         handle_event(fd)                                    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │  핵심: 커널이 Ready 상태인 FD만 반환                 │    │
│  │  → 애플리케이션은 모든 FD를 순회할 필요 없음          │    │
│  │  → O(1) 시간 복잡도                                  │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 Python에서의 I/O Multiplexing

```python
# Python select 모듈 (저수준)
import select

# epoll 사용 예시 (Linux)
epoll = select.epoll()
epoll.register(socket_fd, select.EPOLLIN)

while True:
    events = epoll.poll()  # 블로킹
    for fd, event in events:
        if event & select.EPOLLIN:
            data = connections[fd].recv(1024)
```

> **참고**: [Python select module](https://docs.python.org/3/library/select.html)

---

## 2. Event Loop 구조

### 2.1 기본 Event Loop 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Event Loop 아키텍처                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   Event Loop                         │   │
│  │  ┌─────────────────────────────────────────────────┐│   │
│  │  │                 Main Loop                        ││   │
│  │  │                                                  ││   │
│  │  │   ┌──────────┐    ┌──────────┐    ┌──────────┐ ││   │
│  │  │   │  Timer   │    │   I/O    │    │  Signal  │ ││   │
│  │  │   │  Queue   │    │  Queue   │    │  Queue   │ ││   │
│  │  │   └────┬─────┘    └────┬─────┘    └────┬─────┘ ││   │
│  │  │        │               │               │        ││   │
│  │  │        └───────────────┼───────────────┘        ││   │
│  │  │                        ▼                        ││   │
│  │  │                ┌──────────────┐                 ││   │
│  │  │                │  Ready Queue │                 ││   │
│  │  │                └──────┬───────┘                 ││   │
│  │  │                       │                         ││   │
│  │  │                       ▼                         ││   │
│  │  │                ┌──────────────┐                 ││   │
│  │  │                │   Execute    │                 ││   │
│  │  │                │   Callbacks  │                 ││   │
│  │  │                └──────────────┘                 ││   │
│  │  └─────────────────────────────────────────────────┘│   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  동작 순서:                                                 │
│  1. Timer 만료 체크 → Ready Queue                           │
│  2. I/O 이벤트 체크 (epoll_wait) → Ready Queue              │
│  3. Signal 체크 → Ready Queue                               │
│  4. Ready Queue의 콜백 실행                                  │
│  5. 반복                                                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Event Loop의 핵심 컴포넌트

| 컴포넌트 | 역할 | 예시 |
|---------|------|------|
| **I/O Watcher** | FD 이벤트 감시 | 소켓 읽기/쓰기 |
| **Timer** | 시간 기반 이벤트 | setTimeout, setInterval |
| **Signal Handler** | OS 시그널 처리 | SIGTERM, SIGINT |
| **Callback Registry** | 이벤트-콜백 매핑 | fd → handler |
| **Ready Queue** | 실행 대기 콜백 | FIFO 큐 |

---

## 3. asyncio Event Loop

### 3.1 asyncio의 Event Loop 구현

Python asyncio는 **selectors 모듈**을 사용하여 OS별 최적의 I/O Multiplexing을 선택한다.

```python
# asyncio는 자동으로 최적의 selector 선택
# Linux: EpollSelector
# macOS: KqueueSelector
# Windows: ProactorEventLoop (IOCP)

import asyncio

async def main():
    # Event Loop 내부에서 실행
    await asyncio.sleep(1)  # Timer 이벤트
    
asyncio.run(main())  # Event Loop 생성 및 실행
```

### 3.2 asyncio Event Loop 동작

```
┌─────────────────────────────────────────────────────────────┐
│                 asyncio Event Loop 동작                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  asyncio.run(main())                                        │
│       │                                                     │
│       ▼                                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  loop = asyncio.new_event_loop()                     │   │
│  │  asyncio.set_event_loop(loop)                        │   │
│  │                                                       │   │
│  │  loop.run_until_complete(main())                     │   │
│  │       │                                               │   │
│  │       ▼                                               │   │
│  │  ┌───────────────────────────────────────────────┐   │   │
│  │  │              _run_once()                       │   │   │
│  │  │                                                │   │   │
│  │  │  1. self._scheduled (Timer) 처리               │   │   │
│  │  │  2. self._selector.select(timeout)            │   │   │
│  │  │     → epoll_wait / kqueue                     │   │   │
│  │  │  3. 콜백 실행                                  │   │   │
│  │  │  4. 반복                                       │   │   │
│  │  └───────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  핵심 특징:                                                 │
│  • Python 레벨 구현 (순수 Python + selectors)               │
│  • async/await 문법과 통합                                  │
│  • 스레드당 하나의 Event Loop                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3.3 asyncio 제약사항

```python
# ❌ 중첩된 Event Loop 실행 불가
import asyncio

async def outer():
    asyncio.run(inner())  # RuntimeError!
    
async def inner():
    await asyncio.sleep(1)

# 에러: "Cannot run the event loop while another loop is running"
```

---

## 4. Gevent/Eventlet Event Loop

### 4.1 libev/libuv 기반

Gevent와 Eventlet은 **C 라이브러리 기반**의 Event Loop를 사용한다.

| 라이브러리 | 언어 | 사용처 | 특징 |
|-----------|------|--------|------|
| **libev** | C | Gevent | 경량, Unix 중심 |
| **libuv** | C | Node.js, Gevent | 크로스플랫폼, 파일 I/O 지원 |
| **libgreen** | C | Eventlet | Eventlet 전용 |

### 4.2 Gevent Event Loop 구조

```
┌─────────────────────────────────────────────────────────────┐
│                   Gevent 아키텍처                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Python Layer                                               │
│  ─────────────                                              │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Gevent Hub                              │   │
│  │  (메인 Event Loop, greenlet으로 구현)                 │   │
│  │                                                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐              │   │
│  │  │greenlet1│  │greenlet2│  │greenlet3│  ...         │   │
│  │  └────┬────┘  └────┬────┘  └────┬────┘              │   │
│  │       │            │            │                    │   │
│  │       └────────────┼────────────┘                    │   │
│  │                    ▼                                 │   │
│  │            ┌──────────────┐                          │   │
│  │            │  Hub.switch()│                          │   │
│  │            └──────┬───────┘                          │   │
│  └───────────────────┼─────────────────────────────────┘   │
│                      │                                      │
│  C Layer (libev)     │                                      │
│  ───────────────     ▼                                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              libev Event Loop                        │   │
│  │                                                       │   │
│  │  • ev_io (I/O watcher)                               │   │
│  │  • ev_timer (Timer)                                  │   │
│  │  • ev_signal (Signal)                                │   │
│  │  • ev_loop_run() → epoll/kqueue/select               │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4.3 Monkey Patching

Gevent의 핵심은 **Monkey Patching**이다.

```python
# Gevent 시작 시
from gevent import monkey
monkey.patch_all()

# 다음 모듈들이 패치됨:
# socket → gevent.socket
# ssl → gevent.ssl
# time.sleep → gevent.sleep
# threading → gevent._threading

# 결과: 동기 코드가 자동으로 비동기처럼 동작
import socket
s = socket.socket()
s.recv(1024)  # 블로킹이 아닌 greenlet 전환!
```

```
┌─────────────────────────────────────────────────────────────┐
│                   Monkey Patching 동작                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Before Patch:                                              │
│  ─────────────                                              │
│  socket.recv() → Blocking I/O (스레드 전체 블록)             │
│                                                             │
│  After Patch:                                               │
│  ────────────                                               │
│  socket.recv() → gevent.socket.recv()                       │
│       │                                                     │
│       ▼                                                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  1. libev에 I/O watcher 등록                           │ │
│  │  2. hub.switch() → 다른 greenlet으로 전환              │ │
│  │  3. I/O 완료 시 원래 greenlet으로 복귀                  │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 5. asyncio vs Gevent Event Loop 비교

### 5.1 핵심 차이점

| 특성 | asyncio | Gevent |
|------|---------|--------|
| **Event Loop** | Python 구현 (selectors) | C 구현 (libev/libuv) |
| **동시성 단위** | Coroutine (async def) | Greenlet |
| **I/O 처리** | 명시적 (await) | 암시적 (monkey patch) |
| **기존 코드** | async/await 필수 | 동기 코드 그대로 사용 |
| **전환 제어** | 프로그래머가 await로 명시 | I/O 시 자동 전환 |

### 5.2 구조적 비교

```
┌─────────────────────────────────────────────────────────────┐
│                  Event Loop 구조 비교                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  asyncio:                                                   │
│  ─────────                                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  asyncio.run()                                       │   │
│  │      │                                               │   │
│  │      ▼                                               │   │
│  │  ┌─────────────────┐                                 │   │
│  │  │ SelectorEventLoop │  ← Python 구현                │   │
│  │  │                   │                               │   │
│  │  │   Task1 (coro)    │                               │   │
│  │  │   Task2 (coro)    │  ← async/await 필수           │   │
│  │  │   Task3 (coro)    │                               │   │
│  │  └────────┬──────────┘                               │   │
│  │           │                                          │   │
│  │           ▼                                          │   │
│  │     epoll/kqueue (OS)                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Gevent:                                                    │
│  ────────                                                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  gevent.spawn()                                      │   │
│  │      │                                               │   │
│  │      ▼                                               │   │
│  │  ┌─────────────────┐                                 │   │
│  │  │   Gevent Hub    │  ← Python 래퍼                  │   │
│  │  │                 │                                 │   │
│  │  │  greenlet1 (fn) │                                 │   │
│  │  │  greenlet2 (fn) │  ← 일반 함수 가능               │   │
│  │  │  greenlet3 (fn) │                                 │   │
│  │  └────────┬────────┘                                 │   │
│  │           │                                          │   │
│  │           ▼                                          │   │
│  │  ┌─────────────────┐                                 │   │
│  │  │  libev (C)      │  ← C 라이브러리                 │   │
│  │  └────────┬────────┘                                 │   │
│  │           │                                          │   │
│  │           ▼                                          │   │
│  │     epoll/kqueue (OS)                                │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Event Loop 충돌 원인

### 6.1 왜 서로 다른 Event Loop는 충돌하는가?

```
┌─────────────────────────────────────────────────────────────┐
│                Event Loop 충돌 원인                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  충돌 시나리오:                                              │
│  ─────────────                                              │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐ │
│  │  Gevent Hub (libev event loop)                        │ │
│  │     │                                                 │ │
│  │     └── greenlet: my_task()                          │ │
│  │              │                                        │ │
│  │              └── asyncio.run(coro)  ← ❌ 충돌!        │ │
│  │                       │                               │ │
│  │                       └── asyncio event loop 생성     │ │
│  └───────────────────────────────────────────────────────┘ │
│                                                             │
│  문제점:                                                    │
│  ────────                                                   │
│  1. 두 Event Loop가 동시에 실행 시도                         │
│  2. 각자 I/O를 감시하려 함 (epoll_wait 충돌)                 │
│  3. 스레드 제어권 충돌                                       │
│                                                             │
│  에러 메시지:                                               │
│  "RuntimeError: Cannot run the event loop while             │
│   another loop is running"                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 해결 방법

| 상황 | 해결책 |
|------|--------|
| **Gevent 환경에서 async 코드** | 동기 코드로 변경 (gevent가 자동 처리) |
| **asyncio 환경에서 sync 코드** | `run_in_executor()` 사용 |
| **두 Event Loop 혼용 필요** | 별도 프로세스 분리 |

```python
# ✅ Gevent 환경에서의 올바른 패턴
# 동기 코드 사용 → gevent가 자동으로 greenlet 전환
def my_task():
    response = requests.get("https://api.example.com")  # 자동 전환
    return response.json()

# ❌ Gevent 환경에서의 잘못된 패턴
async def my_async_task():
    async with aiohttp.ClientSession() as session:
        response = await session.get("https://api.example.com")
        return await response.json()

# Gevent 환경에서 asyncio.run(my_async_task()) 호출 시 충돌
```

---

## 7. 이코에코 적용 사례

### 7.1 Celery Worker Pool과 Event Loop

```
┌─────────────────────────────────────────────────────────────┐
│              이코에코 Event Loop 사용 현황                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  API Layer (FastAPI + Uvicorn):                             │
│  ───────────────────────────────                            │
│  • asyncio Event Loop 사용                                  │
│  • async def 엔드포인트                                     │
│  • aiohttp, asyncpg 등 async 클라이언트                     │
│                                                             │
│  Worker Layer (Celery):                                     │
│  ──────────────────────                                     │
│  • Pool별 다른 Event Loop 사용                              │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  prefork Pool:                                       │   │
│  │  • 프로세스별 독립 asyncio Event Loop 가능            │   │
│  │  • run_async() 헬퍼 사용 가능                         │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  gevent Pool:                                        │   │
│  │  • libev Event Loop (monkey patched)                 │   │
│  │  • asyncio Event Loop 사용 불가! ← 충돌               │   │
│  │  • 동기 코드만 사용                                   │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 실제 트러블슈팅 사례

> **참고**: [18-gevent-asyncio-eventloop-conflict.md](../blogs/async/18-gevent-asyncio-eventloop-conflict.md)

```python
# ❌ Before (충돌 발생)
@celery_app.task
def vision_task():
    from domains._shared.celery.async_support import run_async
    result = run_async(analyze_images_async())  # asyncio loop 실행 시도
    return result

# ✅ After (정상 동작)
@celery_app.task
def vision_task():
    result = analyze_images()  # 동기 함수 (gevent가 자동 처리)
    return result
```

---

## 8. 핵심 요약

```
┌─────────────────────────────────────────────────────────────┐
│                      핵심 요약                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. Event Loop = I/O Multiplexing + Callback 실행           │
│     ─────────────────────────────────────────────           │
│     • OS의 epoll/kqueue로 I/O 감시                          │
│     • Ready 이벤트 발생 시 콜백 실행                         │
│                                                             │
│  2. asyncio vs Gevent                                       │
│     ─────────────────────                                   │
│     • asyncio: Python 구현, async/await 필수                 │
│     • Gevent: C 구현 (libev), 동기 코드 자동 변환            │
│                                                             │
│  3. 충돌 원인                                                │
│     ───────────                                             │
│     • 하나의 스레드에 두 Event Loop 공존 불가                 │
│     • 각자 I/O 감시 → 제어권 충돌                            │
│                                                             │
│  4. 해결책                                                   │
│     ─────────                                               │
│     • Gevent 환경: 동기 코드 사용                            │
│     • asyncio 환경: async/await 사용                         │
│     • 혼용 필요: 프로세스 분리                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 참고 자료

### 공식 문서
- [Python asyncio](https://docs.python.org/3.11/library/asyncio.html)
- [Python select module](https://docs.python.org/3/library/select.html)
- [Gevent Introduction](https://www.gevent.org/intro.html)

### C 라이브러리
- [libev](http://software.schmorp.de/pkg/libev.html) - Gevent의 기반
- [libuv](https://libuv.org/) - Node.js, Gevent의 기반

### 관련 문서
- [01-python-asyncio.md](./01-python-asyncio.md) - asyncio 사용법
- [04-concurrency-patterns.md](./04-concurrency-patterns.md) - Celery Pool 패턴
- [18-gevent-asyncio-eventloop-conflict.md](../blogs/async/18-gevent-asyncio-eventloop-conflict.md) - 트러블슈팅

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2025-12-24 | 최초 작성 |












