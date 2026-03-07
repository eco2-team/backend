# Gevent + Asyncio Event Loop 충돌 트러블슈팅

> **Date**: 2025-12-24  
> **Author**: eco2 Backend Team  
> **Tags**: `gevent`, `asyncio`, `celery`, `troubleshooting`

## 📋 개요

Celery Worker를 `prefork` pool에서 `gevent` pool로 전환 후, 부하 테스트에서 **98% 실패율** 발생.
원인은 Gevent와 Asyncio event loop 간의 충돌이었다.

---

## 🚨 증상

### 부하 테스트 결과
```
100 users / 10s ramp-up
Failures: 98%
```

### 에러 로그
```
[ERROR/MainProcess] Vision analysis failed
Task scan.vision[...] retry: Retry in 180s: 
RuntimeError('Cannot run the event loop while another loop is running')
```

---

## 🔍 원인 분석

### 문제 코드

```python
# domains/scan/tasks/vision.py (Before)
@celery_app.task(...)
def vision_task(...):
    from domains._shared.celery.async_support import run_async
    from domains._shared.waste_pipeline.vision import analyze_images_async
    
    # ❌ Gevent 환경에서 asyncio loop 실행 시도
    result_payload = run_async(analyze_images_async(prompt_text, image_url))
```

### run_async() 내부
```python
# domains/_shared/celery/async_support.py
def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)  # ❌ 충돌!
    finally:
        loop.close()
```

### 충돌 원인

```
┌─────────────────────────────────────────────────────────────┐
│  Gevent Pool                                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Gevent Event Loop (libev/libuv 기반)                  │ │
│  │    └── greenlet: vision_task                           │ │
│  │          └── run_async()                               │ │
│  │                └── asyncio.new_event_loop()  ❌ 충돌!  │ │
│  │                      └── loop.run_until_complete()     │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Gevent는 자체 이벤트 루프**(libev/libuv)를 사용하며, 그 안에서 **asyncio 이벤트 루프**를 실행하면 충돌 발생.

---

## ✅ 해결 방법

### 핵심: Gevent Pool에서는 동기 클라이언트 사용

Gevent는 **monkey patching**으로 `socket`, `ssl`, `time` 등을 패치하여,
**동기 호출도 자동으로 greenlet 전환**됨.

```python
# domains/scan/tasks/vision.py (After)
@celery_app.task(...)
def vision_task(...):
    # ✅ 동기 함수 사용 (gevent가 자동으로 greenlet 전환)
    from domains._shared.waste_pipeline.vision import analyze_images
    
    result_payload = analyze_images(prompt_text, image_url, save_result=False)
```

### 동작 원리

```
┌─────────────────────────────────────────────────────────────┐
│  Gevent Pool                                                │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  Gevent Event Loop                                     │ │
│  │    └── greenlet-1: vision_task                         │ │
│  │          └── analyze_images()                          │ │
│  │                └── httpx.post()  ← socket I/O          │ │
│  │                      ↓                                 │ │
│  │              [gevent: greenlet 전환!]                  │ │
│  │                      ↓                                 │ │
│  │    └── greenlet-2: vision_task (다른 요청)             │ │
│  │          └── analyze_images()                          │ │
│  │                └── httpx.post()                        │ │
│  └────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 변경 파일

### 1. `domains/scan/tasks/vision.py`

```diff
- from domains._shared.celery.async_support import run_async
- from domains._shared.waste_pipeline.vision import analyze_images_async
+ from domains._shared.waste_pipeline.vision import analyze_images

- result_payload = run_async(analyze_images_async(prompt_text, image_url))
+ result_payload = analyze_images(prompt_text, image_url, save_result=False)
```

### 2. `domains/scan/tasks/answer.py`

```diff
- from domains._shared.celery.async_support import run_async
- from domains._shared.waste_pipeline.answer import generate_answer_async
+ from domains._shared.waste_pipeline.answer import generate_answer

- final_answer = run_async(generate_answer_async(...))
+ final_answer = generate_answer(..., save_result=False)
```

---

## 🔑 핵심 교훈

### 1. Pool별 적합한 I/O 패턴

| Pool | I/O 패턴 | 비고 |
|------|----------|------|
| **prefork** | `run_async()` + async 함수 | 프로세스별 독립 event loop |
| **gevent** | 동기 함수 직접 호출 | gevent가 자동 greenlet 전환 |
| **eventlet** | 동기 함수 직접 호출 | eventlet이 자동 greenlet 전환 |

### 2. Gevent Monkey Patching

Gevent는 시작 시 다음을 패치:
- `socket` → `gevent.socket`
- `ssl` → `gevent.ssl`
- `time.sleep` → `gevent.sleep`
- `threading` → `gevent.threading`

따라서 **동기 코드가 비동기처럼 동작**함.

### 3. Asyncio와 Gevent 혼용 불가

```python
# ❌ 불가능
import gevent
import asyncio

async def async_task():
    await asyncio.sleep(1)

# gevent 환경에서 asyncio loop 실행 시 충돌
asyncio.run(async_task())
```

---

## 📊 수정 후 결과

```
Before: 98% failure rate
After:  0% failure rate (정상 동작)
```

---

## 🔗 관련 문서

- [16-celery-gevent-pool-migration.md](./16-celery-gevent-pool-migration.md)
- [15-system-rpm-analysis-before-asyncio.md](./15-system-rpm-analysis-before-asyncio.md)
- [Gevent Introduction](https://www.gevent.org/intro.html)
- [Celery - Concurrency](https://docs.celeryq.dev/en/stable/userguide/concurrency/index.html)

---

## 📌 Checklist (다른 프로젝트 적용 시)

- [ ] Gevent pool 사용 시 `run_async()` 호출 제거
- [ ] Async 함수 → 동기 함수로 변경
- [ ] OpenAI, httpx 등 HTTP 클라이언트는 동기 버전 사용
- [ ] DB 클라이언트도 동기 버전 사용 (asyncpg → psycopg2)

