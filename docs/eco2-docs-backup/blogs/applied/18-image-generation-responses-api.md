# 이미지 생성 서브에이전트: Responses API 하이브리드 아키텍처

> LangGraph 파이프라인에서 OpenAI Responses API를 선택적으로 활용한 이미지 생성 기능 구현
>
> **작성일**: 2026-01-16

---

## 1. 배경

### 1.1 요구사항

분리배출 챗봇에서 이미지 생성 기능 추가 검토:
- 분리배출 방법 인포그래픽 생성
- 폐기물 분류 결과 시각화
- 사용자 요청에 따른 맞춤 이미지

### 1.2 기술적 질문

| 질문 | 검토 내용 |
|------|----------|
| GPT-5.2가 이미지 생성 가능한가? | ❌ 텍스트 전용 모델 |
| 별도 API 호출이 필요한가? | ✅ GPT Image 1.5 또는 Responses API |
| Responses API가 새 표준인가? | ⚠️ 권장되지만 Chat Completions도 유지 |
| 기존 파이프라인과 공존 가능한가? | ✅ 같은 API 키로 혼용 가능 |

---

## 2. API 비교 분석

### 2.1 OpenAI API 현황 (2026-01 기준)

| API | 상태 | 용도 |
|-----|------|------|
| **Chat Completions** | ✅ 유지 | 텍스트 생성, function calling |
| **Responses API** | ⭐ 권장 | 에이전트, 멀티모달, built-in tools |
| **Images API** | ✅ 유지 | 직접 이미지 생성 |
| **Assistants API** | ⚠️ Deprecated | 2026년 8월 sunset |

### 2.2 Responses API 장점

```
성능: SWE-bench +3% 향상
비용: 캐시 효율 40-80% 개선
기능: 네이티브 built-in tools
  - image_generation
  - web_search
  - code_interpreter
  - file_search
```

### 2.3 현재 아키텍처와의 호환성

**현재**: Chat Completions + LangGraph (multi-intent 라우팅)

```
START → intent → [vision?] → router
                               │
        ┌──────┬───────┬───────┼───────┬───────┬──────┐
        ▼      ▼       ▼       ▼       ▼       ▼      ▼
     waste  character location bulk  web    general  ...
     (RAG)   (gRPC)   (Kakao)  (API)  (DDG)
```

**전면 전환 시 문제점**:

| 항목 | 현재 (Chat Completions) | Responses API |
|------|------------------------|---------------|
| Intent 라우팅 | LangGraph가 직접 제어 | 모델이 자동 결정 (제어권 상실) |
| Feedback Loop | 품질 평가 → Fallback | 미지원 |
| Progress Events | 노드별 세밀한 SSE | 토큰 스트리밍만 |
| Custom RAG | 자체 RetrieverPort | file_search로 제한 |

---

## 3. 아키텍처 결정

### 3.1 하이브리드 접근법

**결정**: 전면 마이그레이션 대신 **서브에이전트 단위로 Responses API 선택적 사용**

```
기존 파이프라인 (Chat Completions + LangGraph)
        │
        ├── intent_node (Chat Completions)
        ├── vision_node (Chat Completions)
        ├── rag_node (Chat Completions)
        ├── ...
        │
        └── image_generation_node (⭐ Responses API)
                    │
                    └── 네이티브 image_generation tool
```

**장점**:
- 기존 multi-intent 라우팅 구조 유지
- Feedback Loop, Progress Events 보존
- 이미지 생성에서만 Responses API의 이점 활용
- 같은 OpenAI API 키로 두 API 혼용

### 3.2 왜 직접 Images API가 아닌 Responses API인가?

| 항목 | Images API 직접 호출 | Responses API |
|------|---------------------|---------------|
| 프롬프트 | 그대로 전달 | 모델이 최적화 |
| 응답 | 이미지 URL만 | 이미지 + 설명 텍스트 |
| 비용 | 이미지 비용만 | 토큰 + 이미지 비용 |
| 품질 | 사용자 프롬프트 의존 | 모델이 프롬프트 개선 |

**선택**: Responses API
- 모델이 프롬프트를 최적화하여 더 나은 이미지 생성
- 이미지와 함께 설명 텍스트 자동 생성 (UX 향상)

---

## 4. 구현

### 4.1 Clean Architecture 구조

```
apps/chat_worker/
├── application/
│   ├── ports/
│   │   └── image_generator.py      # Port (추상화)
│   └── commands/
│       └── generate_image_command.py  # UseCase
│
├── infrastructure/
│   └── llm/image_generator/
│       └── openai_responses.py     # Adapter (Responses API)
│
└── infrastructure/orchestration/langgraph/nodes/
    └── image_generation_node.py    # LangGraph 노드
```

### 4.2 Port 정의

```python
# application/ports/image_generator.py

@dataclass(frozen=True)
class ImageGenerationResult:
    image_url: str
    description: str | None = None
    revised_prompt: str | None = None


class ImageGeneratorPort(ABC):
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        pass
```

### 4.3 Responses API Adapter

```python
# infrastructure/llm/image_generator/openai_responses.py

class OpenAIResponsesImageGenerator(ImageGeneratorPort):
    async def generate(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        response = await self._client.responses.create(
            model=self._model,  # gpt-5.2 (기본 LLM과 동일)
            input=self._build_input_prompt(prompt),
            tools=[
                {
                    "type": "image_generation",
                    "image_generation": {
                        "size": size,
                        "quality": quality,
                    },
                }
            ],
        )

        # 응답에서 이미지 URL과 설명 추출
        for item in response.output:
            if item.type == "image_generation_call":
                image_url = item.result
            elif item.type == "message":
                description = item.content[0].text

        return ImageGenerationResult(
            image_url=image_url,
            description=description,
        )
```

### 4.4 LangGraph 노드

```python
# infrastructure/orchestration/langgraph/nodes/image_generation_node.py

def create_image_generation_node(
    image_generator: ImageGeneratorPort,
    event_publisher: ProgressNotifierPort,
):
    command = GenerateImageCommand(image_generator=image_generator)

    async def image_generation_node(state: dict) -> dict:
        # Progress 알림 (UX)
        await event_publisher.notify_stage(
            task_id=state["job_id"],
            stage="image_generation",
            message="🎨 이미지 생성 중...",
        )

        # Command 실행
        output = await command.execute(
            GenerateImageInput(
                job_id=state["job_id"],
                prompt=state["query"],
            )
        )

        return {
            **state,
            "generated_image_url": output.image_url,
            "image_description": output.description,
        }

    return image_generation_node
```

### 4.5 Intent 및 라우팅 추가

```python
# domain/enums/intent.py
class Intent(str, Enum):
    # ... 기존 intent들
    IMAGE_GENERATION = "image_generation"
    """이미지 생성 요청.

    - 분리배출 방법 이미지로 만들어줘
    - 페트병 버리는 법 그림으로 보여줘
    """

# factory.py - 라우팅 추가
graph.add_conditional_edges(
    "router",
    route_by_intent,
    {
        "waste": "waste_rag",
        # ... 기존 라우팅
        "image_generation": "image_generation",  # 추가
        "general": "general",
    },
)
```

---

## 5. 설정

### 5.1 환경변수

```bash
# 이미지 생성 활성화 (비용 발생, 기본 비활성화)
CHAT_WORKER_ENABLE_IMAGE_GENERATION=true

# Responses API 모델 (프롬프트 최적화용, 기본: gpt-5.2)
# 기본 LLM과 동일 모델 사용 → 설정 단순화
CHAT_WORKER_IMAGE_GENERATION_MODEL=gpt-5.2

# 기본 이미지 설정
CHAT_WORKER_IMAGE_GENERATION_DEFAULT_SIZE=1024x1024
CHAT_WORKER_IMAGE_GENERATION_DEFAULT_QUALITY=medium
```

### 5.2 비용 고려

| 품질 | 1024x1024 | 비고 |
|------|-----------|------|
| low | ~$0.02 | 빠름, 저품질 |
| medium | ~$0.07 | 균형 (권장) |
| high | ~$0.19 | 고품질, 느림 |

+ Responses API 토큰 비용 추가 (~$0.01-0.02)

---

## 6. 플로우 예시

```
User: "페트병 분리배출 방법 이미지로 만들어줘"
        │
        ▼
   intent_node (Chat Completions)
   → intent: "image_generation"
        │
        ▼
   router → image_generation_node
        │
        ▼
   Responses API + image_generation tool
   → 모델이 프롬프트 최적화
   → GPT Image 1.5 호출
        │
        ▼
   SSE: {
     stage: "image_generation",
     image_url: "https://...",
     message: "✅ 이미지 생성 완료"
   }
        │
        ▼
   answer_node
   → "요청하신 이미지를 생성했습니다.
      [이미지 설명]
      ![생성된 이미지](url)"
```

---

## 7. 결론

### 7.1 의사결정 요약

| 항목 | 결정 | 이유 |
|------|------|------|
| 전면 Responses API 전환 | ❌ 거부 | multi-intent 라우팅 제어권 유지 |
| 하이브리드 접근 | ✅ 채택 | 기존 아키텍처 보존 + 선택적 활용 |
| Images API 직접 호출 | ❌ 거부 | 프롬프트 최적화 + 설명 생성 이점 |
| Responses API 네이티브 tool | ✅ 채택 | 모델이 프롬프트 최적화 |
| 오케스트레이션 모델 (gpt-5.2) | ✅ 채택 | 기본 LLM과 동일 → 설정 단순화 |

### 7.2 아키텍처 원칙 준수

- **Clean Architecture**: Port/Adapter 패턴으로 API 교체 용이
- **단일 책임**: image_generation_node는 이미지 생성만 담당
- **점진적 확장**: 필요 시 다른 Responses API 기능 추가 가능

### 7.3 향후 고려사항

- Responses API의 다른 built-in tools 활용 검토 (web_search 등)
- 비용 모니터링 및 rate limiting
- 이미지 캐싱 전략 (동일 프롬프트 재사용)

---

## 참고 자료

- [OpenAI Responses API](https://platform.openai.com/docs/guides/responses)
- [Image Generation Tool](https://platform.openai.com/docs/guides/tools-image-generation)
- [GPT Image 1.5 Model](https://platform.openai.com/docs/models/gpt-image-1.5)
- [Migrate to Responses API](https://platform.openai.com/docs/guides/migrate-to-responses)
