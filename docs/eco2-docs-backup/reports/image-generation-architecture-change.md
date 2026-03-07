# Image Generation 아키텍처 변경 보고서

**작성일**: 2026-01-20
**작성자**: Claude Code
**관련 PR**: #462, #463, #464

---

## 1. 배경

### 1.1 기존 구조
기존 이미지 생성 에이전트는 클라이언트에서 전달하는 provider 설정에 따라 두 가지 모델을 지원했습니다:

| Provider | Model | 특징 |
|----------|-------|------|
| OpenAI | gpt-images-1.5 | DALL-E 기반, 조직 인증 필요 |
| Google | gemini-pro | Gemini Pro Vision, 이미지 생성 품질 낮음 |

### 1.2 문제점

**1) OpenAI 조직 인증 요구사항**
- GPT 이미지 생성 API(`gpt-images-1.5`)를 사용하려면 OpenAI 조직 인증이 필수
- 인증 절차가 복잡하고 시간이 소요됨
- 개발/테스트 환경에서 사용 불가

**2) Gemini Nano Banana의 등장**
- Google이 새로운 네이티브 이미지 생성 모델 `gemini-3-pro-image-preview` (코드명: Nano Banana) 출시
- 기존 `gemini-pro`보다 이미지 생성 품질이 월등히 우수
- 참조 이미지 기반 스타일 일관성 지원 (캐릭터 참조 최대 14개)
- SynthID 워터마크 자동 포함

→ **결정**: 이미지 생성 에이전트를 Nano Banana(`gemini-3-pro-image-preview`)로 고정

---

## 2. Token Explosion 문제

### 2.1 문제 발생

이미지 생성 모델을 Nano Banana로 변경한 후, **심각한 토큰 폭발 문제**가 발생했습니다.

**원인 분석**:
1. Gemini Native Image Generation은 이미지를 URL이 아닌 **바이트 데이터**로 반환
2. 기존 구조에서는 이 바이트 데이터를 Base64로 인코딩하여 `image_generation_context`에 저장
3. Answer Node로 전달될 때 Base64 문자열이 LLM 프롬프트에 포함됨
4. **1MB 이미지 → ~1.3MB Base64 → 수십만 토큰 소비** → Context Window 초과

```python
# 기존 문제 코드 (gemini_native.py:271-274)
image_b64 = base64.b64encode(image_bytes).decode("utf-8")
image_url = f"data:image/png;base64,{image_b64}"  # 토큰 폭발!
```

### 2.2 검토한 대안

**대안 1: Answer Node에서 직접 이미지 생성**
- 장점: 별도의 이미지 전달 로직 불필요
- 단점:
  - 이미지 생성 모델과 응답 생성 모델이 결합됨
  - Gemini로 이미지 생성 시 응답도 Gemini 사용 강제
  - GPT-4.5로 응답 생성 시 이미지 생성 불가
  - **자유도 심각하게 저하** → 기각

**대안 2: 별도 이미지 저장소 활용**
- 장점: 모델 독립성 유지, 토큰 소비 없음
- 단점: 추가 인프라 필요
- → **채택**

---

## 3. 해결책: gRPC + S3/CDN 아키텍처

### 3.1 아키텍처 설계

기존에 구축된 **Images API**의 presigned URL 발급 서버를 활용하기로 결정했습니다.

```
┌─────────────────────────────────────────────────────────────┐
│           Image Generation Node (chat-worker)               │
│  1. Gemini로 이미지 생성 (bytes 반환)                        │
│  2. gRPC Client로 Images API에 bytes 업로드 요청             │
└──────────────────────────┬──────────────────────────────────┘
                           │ gRPC UploadBytes (image bytes)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Images API (images namespace:50052)            │
│  3. 받은 bytes를 S3에 저장                                   │
│  4. CDN URL 생성 후 반환                                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ CDN URL 반환
                           ▼
┌─────────────────────────────────────────────────────────────┐
│           Image Generation Node (chat-worker)               │
│  5. CDN URL을 image_generation_context에 저장               │
└──────────────────────────┬──────────────────────────────────┘
                           │ state 전달
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Answer Node (GPT-4.5 등)                       │
│  6. CDN URL을 마크다운 이미지로 응답에 포함                   │
│     https://images.dev.growbin.app/generated/...            │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 데이터 흐름

1. **Image Generation Node**: Gemini로 이미지 생성 (바이트 반환)
2. **Image Generation Node**: gRPC Client를 통해 Images API로 바이트 업로드
3. **Images API**: 받은 바이트를 S3에 저장, CDN URL 반환
4. **Image Generation Node**: CDN URL을 `image_generation_context`에 저장
5. **Answer Node**: CDN URL을 마크다운 이미지로 응답에 포함

### 3.3 구현 코드

#### 3.3.1 Image Generation Node (`image_generation_node.py:146-218`)

```python
# 4. 이미지 업로드 (gRPC) - base64 data URL → CDN URL
final_image_url = output.image_url
if image_storage and output.image_url:
    try:
        # base64 data URL 파싱: data:image/png;base64,<base64_data>
        if output.image_url.startswith("data:") and "," in output.image_url:
            header, b64_data = output.image_url.split(",", 1)
            mime_parts = header.split(":")[1].split(";")
            content_type = mime_parts[0]

            # base64 디코딩
            image_bytes = base64.b64decode(b64_data)

            # gRPC로 업로드 (메타데이터 포함)
            upload_result = await image_storage.upload_bytes(
                image_data=image_bytes,
                content_type=content_type,
                channel="generated",
                uploader_id="chat_worker",
                metadata={
                    "job_id": job_id,
                    "description": output.description or "",
                    "has_synthid": str(output.has_synthid).lower(),
                },
            )

            if upload_result.success and upload_result.cdn_url:
                final_image_url = upload_result.cdn_url  # CDN URL로 교체!
```

#### 3.3.2 gRPC Client (`client.py`)

```python
class ImageStorageClient(ImageStoragePort):
    """Image Storage gRPC 클라이언트."""

    def __init__(self, host: str = "images-api", port: int = 50052):
        self._address = f"{host}:{port}"

    async def upload_bytes(
        self,
        image_data: bytes,
        content_type: str = "image/png",
        channel: str = "generated",
        uploader_id: str = "system",
        metadata: dict[str, str] | None = None,
    ) -> ImageUploadResult:
        """이미지 바이트를 S3에 업로드."""
        stub = await self._get_stub()

        request = UploadBytesRequest(
            channel=channel,
            image_data=image_data,
            content_type=content_type,
            uploader_id=uploader_id,
        )
        if metadata:
            request.metadata.update(metadata)

        response = await stub.UploadBytes(request, timeout=30.0)

        return ImageUploadResult(
            success=response.success,
            cdn_url=response.cdn_url,  # S3 → CloudFront CDN URL
            key=response.key,
        )
```

#### 3.3.3 Answer Context 처리 (`answer_context.py:97-139`)

```python
if self.image_generation_context:
    img_ctx = self.image_generation_context
    image_url = img_ctx.get("image_url")

    if image_url:
        description = img_ctx.get("description", "생성된 이미지")

        # CDN URL (http로 시작)은 마크다운으로 응답에 포함
        # base64 data URL (data:로 시작)은 프롬프트에 포함하면 토큰 폭발 발생
        if image_url.startswith("http"):
            markdown_image = f"![{description}]({image_url})"
            parts.append(
                f"## Generated Image\n"
                f"이미지가 성공적으로 생성되었습니다.\n"
                f"### 출력 규칙 (MUST)\n"
                f"1. 응답의 첫 번째 줄에 아래 마크다운을 그대로 출력하세요:\n"
                f"> {markdown_image}\n"
            )
        else:
            # base64 fallback: 이미지는 SSE로 전달됨
            parts.append(
                f"## Generated Image\n"
                f"이미지 URL이나 base64 데이터를 출력하지 마세요."
            )
```

---

## 4. 인프라 설정

### 4.1 Kubernetes ConfigMap

```yaml
# workloads/domains/chat-worker/base/configmap.yaml
data:
  # gRPC Client (Image Storage)
  CHAT_WORKER_IMAGES_GRPC_HOST: images-api.images.svc.cluster.local
  CHAT_WORKER_IMAGES_GRPC_PORT: '50052'
```

**주의**: Cross-namespace 통신을 위해 FQDN(Full Qualified Domain Name) 사용 필수
- `images-api` (X) - 같은 namespace에서만 동작
- `images-api.images.svc.cluster.local` (O) - cross-namespace 통신 가능

### 4.2 NetworkPolicy

```yaml
# workloads/network-policies/base/allow-chat-to-images-grpc.yaml
---
# Egress: chat-worker → images-api gRPC
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-chat-to-images-grpc
  namespace: chat
spec:
  podSelector:
    matchLabels:
      app: chat-worker
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: images
      podSelector:
        matchLabels:
          app: images-api
    ports:
    - protocol: TCP
      port: 50052
---
# Ingress: images-api ← chat-worker gRPC
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-chat-to-images-grpc
  namespace: images
spec:
  podSelector:
    matchLabels:
      app: images-api
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: chat
      podSelector:
        matchLabels:
          app: chat-worker
    ports:
    - protocol: TCP
      port: 50052
```

---

## 5. E2E 테스트 결과

### 5.1 테스트 요청

```bash
curl -X POST "https://api.dev.growbin.app/api/v1/chat" \
  -H "Cookie: s_access=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"character_id": "aba19e5a-e7a2-4a47-a8a5-59c078832b99"}'
```

```bash
curl -X POST "https://api.dev.growbin.app/api/v1/chat/{session_id}/messages" \
  -H "Cookie: s_access=$TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "밤하늘 그려줘"}'
```

### 5.2 SSE 이벤트 흐름

```
event: stage
data: {"stage":"image_generation","status":"processing","message":"이미지 생성 중"}

event: stage
data: {"stage":"image_generation","status":"completed","result":{"image_url":"https://images.dev.growbin.app/generated/42391f5a8adc4c8780307271462bac74.png"}}

event: token
data: {"token":">"}

event: token
data: {"token":" !["}
...

event: done
data: {
  "stage": "done",
  "result": {
    "intent": "image_generation",
    "answer": "> ![None](https://images.dev.growbin.app/generated/42391f5a8adc4c8780307271462bac74.png)\n\n별들이 반짝이는 밤하늘을 담은 그림이야 🌌..."
  }
}
```

### 5.3 로그 확인

```
INFO  | Generating image (model=gemini-3-pro-image-preview, aspect_ratio=1:1, image_size=1K, references=1)
INFO  | Image generated successfully (size=1048576 bytes, dimensions=1024x1024)
INFO  | Uploading generated image via gRPC (content_type=image/png, size_bytes=1048576)
INFO  | Image uploaded via gRPC (cdn_url=https://images.dev.growbin.app/generated/42391f5a8adc4c8780307271462bac74.png)
```

---

## 6. 성과 요약

| 항목 | Before | After |
|------|--------|-------|
| 이미지 생성 모델 | GPT/Gemini 선택 | Nano Banana 고정 |
| 이미지 전달 방식 | Base64 Data URL | CDN URL (S3) |
| 토큰 소비 | ~300,000+ tokens | ~50 tokens (URL만) |
| Answer 모델 | 이미지 모델에 종속 | 독립적 선택 가능 |
| 인프라 | 없음 | gRPC + S3 + CDN |

---

## 7. aioboto3 마이그레이션: 비동기 I/O 최적화

### 7.1 기존 방식의 문제점 (run_in_executor + boto3)

기존 Images API gRPC Servicer는 동기 boto3 클라이언트를 스레드풀에서 실행했습니다:

```python
# Before: run_in_executor + boto3 (동기)
loop = asyncio.get_running_loop()
await loop.run_in_executor(
    None,  # 기본 ThreadPoolExecutor 사용
    partial(
        self._s3.put_object,
        Bucket=bucket,
        Key=key,
        Body=image_data,
    ),
)
```

**문제점:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Event Loop (단일 스레드)                              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                     │
│  │ Task A  │  │ Task B  │  │ Task C  │  ... 다른 코루틴들                   │
│  └────┬────┘  └────┬────┘  └────┬────┘                                     │
│       │            │            │                                           │
│       ▼            ▼            ▼                                           │
│  ┌─────────────────────────────────────┐                                   │
│  │        run_in_executor 호출         │                                   │
│  │  (Event Loop → ThreadPool 전환)     │                                   │
│  └─────────────────┬───────────────────┘                                   │
└────────────────────┼────────────────────────────────────────────────────────┘
                     │ 컨텍스트 스위칭 오버헤드
                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ThreadPoolExecutor (별도 스레드들)                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐                                     │
│  │Thread 1 │  │Thread 2 │  │Thread 3 │  ... max_workers=10                 │
│  │ S3 PUT  │  │ S3 PUT  │  │ S3 PUT  │                                     │
│  │(블로킹) │  │(블로킹) │  │(블로킹) │                                     │
│  └─────────┘  └─────────┘  └─────────┘                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

1. **스레드 컨텍스트 스위칭 비용**: Event Loop ↔ ThreadPool 전환 시 CPU 오버헤드
2. **스레드 자원 낭비**: I/O 대기 중에도 스레드가 점유됨 (블로킹)
3. **스레드풀 크기 제한**: `max_workers=10`으로 동시 업로드 10개 제한
4. **GIL 경합**: Python GIL로 인한 멀티스레딩 효율 저하

### 7.2 aioboto3 방식 (네이티브 async I/O)

마이그레이션 후 aioboto3의 네이티브 비동기 클라이언트를 사용합니다:

```python
# After: aioboto3 (네이티브 async)
async with self._session.client("s3", region_name=region) as s3:
    await s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=image_data,
    )
```

**동작 원리:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Event Loop (단일 스레드)                              │
│                                                                             │
│  시간 ──────────────────────────────────────────────────────────────────▶  │
│                                                                             │
│  Task A: ████░░░░░░░░░░░████░░░░░░░░░░░████                                │
│          실행  I/O대기     실행  I/O대기    완료                             │
│                                                                             │
│  Task B:     ████░░░░░░░░░░░████░░░░░░░░░░░████                            │
│              실행  I/O대기     실행  I/O대기    완료                         │
│                                                                             │
│  Task C:         ████░░░░░░░░░░░████░░░░░░░░░░░████                        │
│                  실행  I/O대기     실행  I/O대기    완료                     │
│                                                                             │
│  ████ = CPU 사용 (실행)                                                     │
│  ░░░░ = I/O 대기 (다른 Task가 실행 가능)                                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 asyncio 동시성 메커니즘

aioboto3는 내부적으로 `aiohttp`를 사용하여 비동기 HTTP 요청을 처리합니다:

```python
# aioboto3/aiohttp 내부 동작 (간소화)
async def put_object(self, Bucket, Key, Body, ...):
    # 1. HTTP 요청 준비 (CPU 바운드 - 즉시 실행)
    request = self._prepare_request(...)

    # 2. 소켓에 데이터 전송 시작 (I/O 시작)
    await self._connection.write(request_data)  # ← yield to event loop

    # 3. S3 응답 대기 (I/O 대기)
    response = await self._connection.read()    # ← yield to event loop

    # 4. 응답 파싱 (CPU 바운드 - 즉시 실행)
    return self._parse_response(response)
```

**핵심 포인트:**
- `await` 시점에서 Event Loop에 제어권 반환
- I/O 대기 중 다른 코루틴이 실행됨
- 스레드 전환 없이 단일 스레드에서 동시성 달성

### 7.4 동시성 처리 비교

**시나리오: 10개의 이미지 동시 업로드**

| 지표 | run_in_executor | aioboto3 |
|------|-----------------|----------|
| 필요한 OS 스레드 | 10개 | 1개 |
| 컨텍스트 스위칭 | 스레드당 ~1000 cycles | 없음 (cooperative) |
| 메모리 (스레드 스택) | ~80MB (10 × 8MB) | ~0MB |
| 최대 동시 연결 | 10개 (스레드풀 크기) | 100+개 (OS 제한까지) |
| GIL 경합 | 있음 | 없음 |

**코드 레벨 동시성:**

```python
# run_in_executor: 스레드풀 크기에 제한됨
# 11번째 요청은 스레드가 반환될 때까지 대기
await loop.run_in_executor(None, s3.put_object, ...)  # Thread 1
await loop.run_in_executor(None, s3.put_object, ...)  # Thread 2
...
await loop.run_in_executor(None, s3.put_object, ...)  # Thread 10
await loop.run_in_executor(None, s3.put_object, ...)  # 대기... Thread 반환 후 실행

# aioboto3: Event Loop이 허용하는 한 무제한 동시 실행
async with session.client('s3') as s3:
    tasks = [s3.put_object(...) for _ in range(100)]
    await asyncio.gather(*tasks)  # 100개 동시 실행 가능
```

### 7.5 구현 코드

#### 7.5.1 ImageServicer (aioboto3 버전)

```python
# apps/images/presentation/grpc/servicers/image_servicer.py

class ImageServicer(image_pb2_grpc.ImageServiceServicer):
    """aioboto3를 사용하여 S3에 비동기로 이미지를 업로드합니다."""

    def __init__(self, session: aioboto3.Session, settings: Settings):
        self._session = session
        self._settings = settings

    async def UploadBytes(self, request, context):
        # 검증 로직 생략...

        # aioboto3 - 진정한 비동기 I/O
        async with self._session.client(
            "s3",
            region_name=self._settings.aws_region,
        ) as s3:
            await s3.put_object(
                Bucket=self._settings.s3_bucket,
                Key=key,
                Body=request.image_data,
                ContentType=request.content_type,
                Metadata={...},
            )

        return UploadBytesResponse(cdn_url=cdn_url, key=key)
```

#### 7.5.2 gRPC Server (세션 주입)

```python
# apps/images/presentation/grpc/server.py

async def serve():
    settings = get_settings()

    # aioboto3 세션 생성 (비동기 S3 클라이언트용)
    session = aioboto3.Session()

    server = grpc.aio.server(...)
    servicer = ImageServicer(session=session, settings=settings)
    image_pb2_grpc.add_ImageServiceServicer_to_server(servicer, server)

    await server.start()
```

### 7.6 성능 이점 요약

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         성능 비교 (이론적)                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  처리량 (동시 업로드)                                                        │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ run_in_executor │████████████████████                    │ 10개/batch ││
│  │ aioboto3        │████████████████████████████████████████│ 100+개    ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  메모리 사용량 (10개 동시 업로드)                                            │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ run_in_executor │████████████████████████████████████████│ ~80MB     ││
│  │ aioboto3        │██                                      │ ~1MB      ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                             │
│  CPU 오버헤드 (컨텍스트 스위칭)                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐│
│  │ run_in_executor │████████████████████                    │ 높음      ││
│  │ aioboto3        │████                                    │ 최소      ││
│  └────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 7.7 관련 PR

- **PR #466**: `refactor(images): migrate S3 upload from boto3 to aioboto3`

---

## 8. 결론

1. **모델 통일**: Nano Banana(`gemini-3-pro-image-preview`)로 이미지 생성 모델 고정
   - GPT 조직 인증 불필요
   - 우수한 이미지 품질
   - 캐릭터 참조 이미지 지원

2. **토큰 폭발 해결**: gRPC + S3/CDN 아키텍처 도입
   - Base64 바이트 대신 CDN URL 전달
   - Answer Node의 모델 독립성 확보
   - 토큰 사용량 99.98% 감소

3. **인프라 활용**: 기존 Images API presigned 서버 재활용
   - 신규 인프라 구축 없이 gRPC 엔드포인트 추가
   - NetworkPolicy로 cross-namespace 통신 보안 확보
