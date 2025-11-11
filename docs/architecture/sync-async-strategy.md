# 도메인별 동기/비동기 처리 전략

## 🎯 최종 결론

### 비동기 처리가 필요한 도메인 (WAL + MQ)

```yaml
✅ scan (폐기물 스캔/분석):
  이유:
    - 이미지 업로드: 2-5초 (S3)
    - AI 분석: 5-30초 (외부 모델 또는 자체 모델)
    - 총 10-35초 → 사용자 대기 불가능
  
  처리 방식:
    → 비동기 필수 (WAL + MQ)
    → Worker-Storage: 이미지 처리
    → Worker-AI: AI 분석

✅ chat (챗봇/LLM):
  이유:
    - GPT API: 5-15초 (OpenAI 외부 API)
    - 외부 네트워크 지연
    - 타임아웃 리스크
  
  처리 방식:
    Option A: WebSocket + 스트리밍 (권장) ⭐
      → 실시간 타이핑 효과
      → 사용자 경험 우수
      → WAL + MQ 불필요
      
    Option B: 비동기 배치 (대량 처리용)
      → WAL + MQ 사용
      → 안정성 높음
      → 대화 이력 저장 등
```

### 동기 처리로 충분한 도메인

```yaml
✅ auth (인증/인가):
  이유:
    - JWT 발급: 10-50ms (매우 빠름)
    - 로그인 검증: 50-200ms
    - 실시간 응답 필수
  
  처리 방식:
    → 동기 처리 (FastAPI 직접 응답)
    → Redis BlackList 조회 (<5ms)

✅ my (마이페이지):
  이유:
    - 조회: 10-50ms (DB + Cache)
    - 업데이트: 50-100ms
    - 사용자 대기 가능
  
  처리 방식:
    → 대부분 동기 처리
    → 예외: 프로필 이미지 업로드만 비동기
  
  예외 케이스:
    - 프로필 이미지 업로드 (2-5초)
      → scan의 Worker-Storage 재사용

✅ character (캐릭터/미션):
  이유:
    - 상태 조회: 10-50ms
    - 미션 완료: 100-300ms
    - 리워드 계산: 50-200ms
  
  처리 방식:
    → 기본 동기 처리
    → 예외: 대량 리워드 배치는 비동기
  
  예외 케이스:
    - 이벤트 리워드 일괄 지급 (1,000명+)
      → Worker로 배치 처리

✅ location (위치/지도):
  이유:
    - Redis 캐시: 5-20ms
    - 외부 지도 API: 200-500ms
    - 실시간 조회 필요
  
  처리 방식:
    → 동기 처리 + Redis 캐싱
    → 캐시 히트율 높임 (90%+)

✅ info (재활용 정보):
  이유:
    - 정적 컨텐츠
    - 조회 중심: 10-50ms
    - 업데이트 거의 없음
  
  처리 방식:
    → 동기 처리
    → Redis 캐싱 + CDN
```

---

## 📊 처리 방식 요약표

| 도메인 | 처리 방식 | 응답 시간 | Worker 필요 | Redis 사용 |
|--------|----------|----------|------------|-----------|
| **scan** | ✅ 비동기 | 10-35초 | Worker-Storage + AI | Cache |
| **chat** | ✅ 비동기/스트리밍 | 5-15초 | Worker-AI (선택) | Cache |
| **auth** | 동기 | 10-200ms | ❌ | BlackList |
| **my** | 동기 | 10-100ms | ❌ | Cache |
| **character** | 동기 | 10-300ms | ❌ | Cache |
| **location** | 동기 | 5-500ms | ❌ | Cache (중요) |
| **info** | 동기 | 10-50ms | ❌ | Cache (중요) |

---

## 🎯 최종 아키텍처

### Worker 구성 (2개 노드)

```yaml
Worker-Storage (t3.small, 2GB):
  역할: I/O 집약적 작업
  
  Celery Tasks:
    1. scan.image_uploader (이미지 S3 업로드) ⭐
    2. scan.image_resizer (썸네일 생성)
    3. scan.image_optimizer (이미지 최적화)
    4. my.profile_image_uploader (프로필 이미지, 선택)
  
  Pool: eventlet (I/O Bound)
  Concurrency: 100
  
  SQLite WAL: Yes (40GB)

Worker-AI (t3.small, 2GB):
  역할: AI/외부 API 호출
  
  Celery Tasks:
    1. scan.waste_analyzer (AI 폐기물 분류) ⭐
    2. scan.classification_model (분류 모델)
    3. chat.batch_responder (배치 대화 처리, 선택)
  
  Pool: prefork (Network Bound)
  Concurrency: 4
  
  SQLite WAL: Yes (40GB)
```

### RabbitMQ Queues

```yaml
Queues:
  scan.image_upload:
    Priority: high
    Max Length: 10000
    TTL: 1 hour
    
  scan.ai_analysis:
    Priority: high
    Max Length: 5000
    TTL: 1 hour
  
  chat.batch (선택적):
    Priority: low
    Max Length: 1000
    TTL: 10 minutes
```

---

## 💡 chat 처리 방식 상세

### Option A: WebSocket 스트리밍 (권장) ⭐⭐⭐

```python
# chat-api/websocket.py
from fastapi import WebSocket
import openai

@app.websocket("/chat/{user_id}")
async def chat_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    
    try:
        while True:
            # 1. 사용자 메시지 수신
            message = await websocket.receive_text()
            
            # 2. GPT 스트리밍 호출
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[{"role": "user", "content": message}],
                stream=True  # 스트리밍
            )
            
            # 3. 실시간 전송 (타이핑 효과)
            full_response = ""
            async for chunk in response:
                delta = chunk.choices[0].delta.get("content", "")
                if delta:
                    await websocket.send_text(delta)
                    full_response += delta
            
            # 4. PostgreSQL에 대화 저장 (비동기)
            await save_conversation(user_id, message, full_response)
            
    except WebSocketDisconnect:
        pass

장점:
  ✅ 실시간 타이핑 효과
  ✅ 사용자 경험 우수
  ✅ GPT 스트리밍 API 활용
  ✅ 타임아웃 없음

단점:
  ⚠️ WebSocket 연결 관리 필요
  ⚠️ 로드밸런싱 복잡 (sticky session)
```

### Option B: 비동기 배치 (대량 처리용)

```python
# chat-api/routes.py
@router.post("/chat/send")
async def send_message(message: str, user_id: str):
    # RabbitMQ에 태스크 추가
    task = chat_responder.delay(user_id, message)
    
    return {
        "task_id": task.id,
        "status": "processing"
    }

# worker-ai/tasks.py
@celery_app.task(bind=True)
def chat_responder(self, user_id: str, message: str):
    task_id = self.request.id
    
    # SQLite WAL 기록
    local_db.insert(task_id, 'processing', message)
    
    # GPT API 호출
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": message}]
    )
    
    answer = response.choices[0].message.content
    
    # PostgreSQL 저장
    save_conversation(user_id, message, answer)
    
    # WAL 정리
    local_db.delete(task_id)
    
    # WebSocket 푸시 또는 푸시 알림
    notify_user(user_id, answer)

장점:
  ✅ 안정성 높음 (WAL + MQ)
  ✅ 재시도 가능
  ✅ 대량 처리 가능

단점:
  ⚠️ 실시간성 낮음
  ⚠️ 사용자 대기 필요
```

**권장**: 일반 채팅은 Option A (WebSocket), 대량 FAQ 처리는 Option B

---

## 🎯 결론

```yaml
비동기 필수:
  1. scan (이미지 + AI) → WAL + MQ ⭐⭐⭐
  2. chat (GPT API) → WebSocket 스트리밍 권장 ⭐⭐

동기 처리:
  3. auth → Redis BlackList
  4. my → Redis Cache
  5. character → Redis Cache
  6. location → Redis Cache (중요)
  7. info → Redis Cache + CDN

Worker 2개로 충분:
  - Worker-Storage: scan 이미지 처리
  - Worker-AI: scan AI 분석 (+ chat 선택)
```

---

**작성일**: 2025-11-08  
**최종 결정**: scan은 비동기 필수, chat은 WebSocket 스트리밍, 나머지는 동기 + Redis Cache

