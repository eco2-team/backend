# 이코에코(Eco2) Message Queue #12: Celery 5.6.0 + Gevent Pool 전환

> **작성일**: 2025-12-24  
> **GitHub**: [eco2-team/backend](https://github.com/eco2-team/backend)  
> **브랜치**: `feat/high-throughput-workers`  
> **Celery 버전**: 5.4.0 → **5.6.0** (2025-11-30 릴리스)

## 1. 개요

본 문서는 Celery를 최신 버전(5.6.0)으로 업그레이드하고, Pool 타입을 `prefork`에서 `gevent`로 전환하여 I/O-bound 작업의 동시성을 크게 향상시킨 과정을 기록합니다.

### 배경

이전 분석([#11: AsyncIO 전환 전 시스템 RPM 현황](./15-system-rpm-analysis-before-asyncio.md))에서 다음 병목이 확인되었습니다:

| 지표 | 측정값 |
|------|--------|
| Chain 평균 소요시간 | 41.65초 |
| OpenAI API 비중 | 65% (vision + answer) |
| 실측 RPS | 0.0323 req/s |
| Worker 블로킹 | 100% (1 request → 1 worker → 41초) |

**문제점**: prefork pool에서 I/O 대기 시간 동안 worker가 블로킹되어 리소스 낭비 심각

---

## 2. Pool 타입 비교

### 2.1 Celery Pool 옵션

| Pool | 동작 방식 | 적합한 워크로드 |
|------|----------|----------------|
| **prefork** | 멀티프로세스 (fork) | CPU-bound |
| **threads** | 멀티스레드 (GIL 제한) | 가벼운 I/O |
| **gevent** | Greenlet (협력적 멀티태스킹) | **I/O-bound** |
| **eventlet** | 유사 greenlet | I/O-bound |

### 2.2 왜 Gevent인가?

1. **I/O 블로킹 자동 전환**: Monkey patching으로 표준 라이브러리의 블로킹 I/O를 greenlet으로 자동 전환
2. **메모리 효율**: 스레드보다 10배 이상 가벼운 greenlet
3. **높은 동시성**: 단일 프로세스에서 수천 개의 동시 연결 처리
4. **기존 코드 호환**: async/await 변환 없이 동기 코드 그대로 사용

### 2.3 AsyncIO Pool 시도 및 결론

네이티브 `async def` Task를 지원하기 위해 여러 옵션을 시도했습니다:

| 패키지 | 결과 |
|--------|------|
| `celery-pool-asyncio` | ❌ Celery 5.4+ 비호환 (`trace.monotonic` 오류) |
| `celery-aio-pool` | ❌ Python 3.11 미지원 (3.8-3.10만) |
| Celery 5.6.0 native | ❌ asyncio pool 미포함 |

**결론**: Celery 5.6.0(2025-11-30 릴리스)에서도 네이티브 asyncio pool이 없습니다. 
Celery 공식 지원 pool 중 I/O-bound에 가장 적합한 **gevent**를 선택했습니다.

참고: [Celery 5.6.0 PyPI](https://pypi.org/project/celery/)

---

## 3. 구현

### 3.1 패키지 추가

```diff
# domains/_base/requirements.txt
- celery==5.4.0
+ celery==5.6.0  # Latest version (2025-11-30)
  celery-batches==0.9.0
+ gevent>=24.2.1  # Celery official gevent pool
```

### 3.2 Worker Deployment 수정

```yaml
# workloads/domains/scan-worker/base/deployment.yaml
args:
- -A
- domains.scan.celery_app
- worker
- --loglevel=info
- -E
- -P
- gevent  # prefork → gevent
- -Q
- scan.vision,scan.rule,scan.answer,scan.reward
- -c
- '100'  # 동시 greenlet 수 (8 → 100)
```

### 3.3 리소스 조정

```yaml
resources:
  requests:
    cpu: 250m
    memory: 512Mi  # 1Gi → 512Mi
  limits:
    cpu: 1000m
    memory: 1Gi    # 4Gi → 1Gi
```

Gevent는 멀티프로세스가 아니므로 메모리 사용량이 크게 감소합니다.

---

## 4. 동작 원리

### 4.1 Gevent Monkey Patching

Gevent는 시작 시 Python 표준 라이브러리를 monkey patch하여 블로킹 I/O를 비동기로 전환합니다:

```python
# Celery가 gevent pool 사용 시 자동 적용
from gevent import monkey
monkey.patch_all()
```

이후 `socket.recv()`, `time.sleep()`, `select()` 등이 greenlet-aware가 됩니다.

### 4.2 Task 실행 흐름

```
┌─────────────────────────────────────────────────────────┐
│                    Gevent Pool (1 process)              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Greenlet 1: vision_task                                │
│       └─> OpenAI API 호출 (I/O 대기)                    │
│              ↓ (자동 yield)                             │
│  Greenlet 2: vision_task                                │
│       └─> OpenAI API 호출 (I/O 대기)                    │
│              ↓ (자동 yield)                             │
│  Greenlet 3: answer_task                                │
│       └─> OpenAI API 호출 (I/O 대기)                    │
│              ↓ (자동 yield)                             │
│  ...                                                    │
│  Greenlet 100: rule_task                                │
│       └─> 파일 I/O (즉시 완료)                          │
│                                                         │
│  ※ I/O 대기 시 다른 greenlet으로 자동 전환             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 4.3 기존 코드 유지

`run_async()` 함수는 그대로 유지됩니다. Gevent pool에서는:

1. `asyncio.new_event_loop().run_until_complete(coro)` 호출
2. 내부 I/O 블로킹 시 gevent가 자동으로 greenlet 전환
3. 다른 greenlet 실행 → I/O 완료 시 복귀

```python
# domains/scan/tasks/vision.py
@celery_app.task
def vision_task(...):
    # gevent pool에서 자동 greenlet 전환됨
    result = run_async(analyze_images_async(prompt, image_url))
    return result
```

---

## 5. 예상 성능 개선

### 5.1 이론적 개선

| 항목 | Prefork (이전) | Gevent (현재) |
|------|---------------|---------------|
| 동시 Worker | 6-9 (메모리 제한) | **100** |
| I/O 블로킹 | 100% (41초/req) | **자동 yield** |
| 메모리 | 3.6GB+ | **~500MB** |
| 예상 RPS | 0.22 | **OpenAI 한계(~4 RPS)** |

### 5.2 병목 이동

```
이전: prefork 프로세스 수 제한
현재: OpenAI API Rate Limit (Tier 1: 500 RPM → 8.3 RPS)
```

Gevent 전환으로 Worker 병목이 해소되어, 실질 병목은 OpenAI API 호출 한도로 이동합니다.

---

## 6. 주의사항

### 6.1 CPU-bound 작업 불가

Gevent는 협력적 멀티태스킹이므로 CPU-intensive 작업 시 다른 greenlet이 블로킹됩니다.
현재 scan-worker는 대부분 I/O-bound(OpenAI API)이므로 적합합니다.

### 6.2 C 확장 호환성

일부 C 확장은 gevent monkey patching과 호환되지 않을 수 있습니다.
주요 라이브러리(httpx, asyncpg, openai)는 정상 동작 확인되었습니다.

### 6.3 디버깅 복잡성

Greenlet 스택 트레이스가 일반 스레드와 다르게 표시될 수 있습니다.
`gevent.hub.Hub.print_exception`으로 상세 로그 확인 가능.

---

## 7. 롤백 방안

문제 발생 시 deployment 수정만으로 즉시 롤백 가능:

```yaml
args:
- -P
- prefork  # gevent → prefork
- -c
- '8'       # 100 → 8
```

---

## 8. 다음 단계

1. **클러스터 배포 및 성능 측정** - Locust로 RPS 비교
2. **OpenAI Tier 업그레이드** 또는 **Gemini 병행** - Rate Limit 완화
3. **다른 Worker 확장** - character-worker, my-worker에도 적용 검토

---

## 참고 자료

- [Celery Concurrency](https://docs.celeryq.dev/en/stable/userguide/workers.html#concurrency)
- [Gevent Documentation](https://www.gevent.org/)
- [Gevent vs Eventlet](https://blog.miguelgrinberg.com/post/greenlet-based-concurrency-in-python)
- [이전 블로그: AsyncIO 전환 전 분석](./15-system-rpm-analysis-before-asyncio.md)

---

## 변경 이력

| 날짜 | 내용 |
|------|------|
| 2025-12-24 | 최초 작성 - Gevent Pool 전환 |
| 2025-12-24 | Celery 5.4.0 → 5.6.0 업그레이드 |
| 2025-12-24 | AsyncIO pool 시도 결과 문서화 (celery-pool-asyncio, celery-aio-pool) |

