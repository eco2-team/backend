# 이코에코(Eco²) Agent #24: Multi-Model Image Generation

> 캐릭터 에셋 참조 기반 이미지 생성 파이프라인

**관련 커밋**:
- [`2bddb87e`](https://github.com/eco2-team/backend/commit/2bddb87e) feat(chat_worker): add multi-model image generation with character reference
- [`89c79c57`](https://github.com/eco2-team/backend/commit/89c79c57) feat(chat_worker): add character reference support to OpenAI image generator

---

## 배경

[#17: Image Generation](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)에서 기본 이미지 생성 기능을 구현했습니다. 그러나 사용자가 "페트리랑 같이 분리배출하는 그림 그려줘"처럼 **Eco² 내부 캐릭터**를 언급하면, 모델은 해당 캐릭터를 인식하지 못해 임의의 캐릭터를 생성하는 문제가 있었습니다.

**문제 상황**: 캐릭터 스타일 일관성 부재

```
사용자: "페트리가 페트병 재활용하는 모습 그려줘"

기존 동작: 모델이 임의의 캐릭터 생성 (페트리 스타일 무시)
목표 동작: CDN의 페트리 이미지를 참조하여 스타일 일관성 유지
```

이 문제를 해결하기 위해 캐릭터 서브에이전트에서 CDN 에셋을 로딩하고, 이미지 생성 시 참조 이미지로 활용하는 파이프라인을 구축했습니다.

---

## 아키텍처

### 전체 흐름

[#19: LangGraph Send API 기반 동적 라우팅](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)에서 구현한 병렬 라우팅 패턴을 활용합니다. `character`와 `image_generation` 노드가 병렬로 실행되며, `aggregator`에서 컨텍스트가 병합됩니다.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Router → [character, image_generation] 병렬 라우팅 (Send API)      │
│                                                                      │
│  ┌──────────────────────┐    ┌─────────────────────────────────┐   │
│  │ character_subagent   │    │ image_generation_node           │   │
│  │                      │    │                                 │   │
│  │ 1. gRPC 캐릭터 조회  │    │ 1. state에서 asset 읽기         │   │
│  │ 2. CDN 에셋 로딩     │    │ 2. generate_with_reference()   │   │
│  │ 3. state에 저장      │    │    호출                         │   │
│  └──────────┬───────────┘    └───────────────┬─────────────────┘   │
│             │                                │                      │
│             └────────────┬───────────────────┘                      │
│                          ▼                                          │
│                    aggregator_node                                  │
│                          │                                          │
│                          ▼                                          │
│                     answer_node                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Multi-Model 전략

두 가지 이미지 생성 Provider를 지원하며, 각각의 특성에 맞게 참조 이미지를 처리합니다.

| Provider | 모델 | 참조 이미지 | 특징 |
|----------|------|------------|------|
| **Google** | `gemini-3-pro-image-preview` (nano banana pro) | 최대 14개 | 네이티브 참조 이미지 지원, 스타일 전이 우수 |
| **OpenAI** | Responses API + `gpt-image-1.5` | 최대 1개 | 프롬프트 자동 최적화, 설명 텍스트 동시 생성 |

Gemini의 `gemini-3-pro-image-preview`는 내부 코드명 **nano banana pro**로 알려진 모델입니다. 참조 이미지를 최대 14개까지 입력받아 스타일 일관성을 유지하는 데 탁월한 성능을 보입니다.

---

## 구현 상세

### 1. Proto 스키마 확장

캐릭터 gRPC 응답에 `character_code` 필드를 추가하여 CDN 에셋 조회가 가능하도록 했습니다.

```protobuf
// apps/character/proto/character.proto
message GetByMatchResponse {
  bool found = 1;
  string character_name = 2;
  string character_type = 3;
  string character_dialog = 4;
  string match_label = 5;
  string character_code = 6;  // CDN 에셋 조회용 (신규)
}
```

### 2. 캐릭터 코드 변환

데이터베이스에서는 `char-pet` 형식을, CDN에서는 `pet` 형식을 사용합니다. 이 차이를 처리하기 위한 변환 로직을 `CharacterService`에 추가했습니다.

```python
# apps/chat_worker/application/services/character_service.py

CHARACTER_CODE_PREFIX = "char-"

@staticmethod
def to_cdn_code(character_code: str | None) -> str | None:
    """캐릭터 코드를 CDN 코드로 변환합니다.

    Examples:
        >>> CharacterService.to_cdn_code("char-pet")
        'pet'
        >>> CharacterService.to_cdn_code("pet")
        'pet'
        >>> CharacterService.to_cdn_code(None)
        None
    """
    if not character_code:
        return None
    if character_code.startswith(CharacterService.CHARACTER_CODE_PREFIX):
        return character_code[len(CharacterService.CHARACTER_CODE_PREFIX):]
    return character_code
```

### 3. CharacterAssetPort 설계 (Clean Architecture)

[#0: LangGraph 기반 클린 아키텍처](https://rooftopsnow.tistory.com/164)에서 정립한 Port/Adapter 패턴으로 CDN 의존성을 추상화했습니다.

```python
# apps/chat_worker/application/ports/character_asset.py

@dataclass(frozen=True)
class CharacterAsset:
    """캐릭터 에셋 DTO."""
    code: str
    image_url: str
    image_bytes: bytes | None = None

class CharacterAssetPort(Protocol):
    """캐릭터 에셋 로더 Port.

    Application Layer에서 정의하며, Infrastructure Layer에서 구현합니다.
    """

    async def get_asset(self, character_code: str) -> CharacterAsset | None:
        """캐릭터 코드로 에셋을 조회합니다."""
        ...
```

```python
# apps/chat_worker/infrastructure/integrations/character/cdn_asset_loader.py

class CDNCharacterAssetLoader(CharacterAssetPort):
    """CDN 기반 캐릭터 에셋 로더.

    httpx를 사용하여 CDN에서 이미지를 다운로드하고,
    인메모리 캐시로 중복 요청을 방지합니다.
    """

    def __init__(
        self,
        base_url: str = "https://cdn.eco2.kr/characters",
        cache_ttl: int = 3600,
    ):
        self._base_url = base_url
        self._cache: dict[str, tuple[CharacterAsset, float]] = {}
        self._cache_ttl = cache_ttl
        self._client = httpx.AsyncClient(timeout=10.0)

    async def get_asset(self, character_code: str) -> CharacterAsset | None:
        # 캐시 확인
        if cached := self._get_from_cache(character_code):
            return cached

        # CDN에서 이미지 다운로드
        url = f"{self._base_url}/{character_code}.png"
        try:
            response = await self._client.get(url)
            if response.status_code == 200:
                asset = CharacterAsset(
                    code=character_code,
                    image_url=url,
                    image_bytes=response.content,
                )
                self._set_cache(character_code, asset)
                return asset
        except Exception as e:
            logger.warning("Failed to load character asset: %s", e)

        return None
```

### 4. GetCharacterCommand 확장

캐릭터 조회 후 에셋도 함께 로딩합니다. **FAIL_OPEN** 정책을 적용하여 에셋 로딩에 실패하더라도 캐릭터 정보는 정상적으로 반환됩니다.

```python
# apps/chat_worker/application/commands/get_character_command.py

class GetCharacterCommand:
    """캐릭터 조회 Command (UseCase).

    Clean Architecture의 Application Layer에 위치하며,
    비즈니스 로직을 조율합니다.
    """

    def __init__(
        self,
        llm: LLMClientPort,
        character_client: CharacterClientPort,
        prompt_loader: PromptLoaderPort,
        character_asset_loader: CharacterAssetPort | None = None,  # 신규
    ):
        self._asset_loader = character_asset_loader
        # ...

    async def execute(self, input_dto: GetCharacterInput) -> GetCharacterOutput:
        # 1. 카테고리 추출 + 캐릭터 조회 (기존 로직)
        character = await self._character_client.get_character(...)

        if not character:
            return GetCharacterOutput(success=False, ...)

        # 2. 에셋 로딩 (신규, FAIL_OPEN 정책)
        char_context = CharacterService.to_answer_context(character)

        if self._asset_loader and character.code:
            cdn_code = CharacterService.to_cdn_code(character.code)
            if cdn_code:
                try:
                    asset = await self._asset_loader.get_asset(cdn_code)
                    if asset:
                        char_context["asset"] = {
                            "code": asset.code,
                            "image_url": asset.image_url,
                            "image_bytes": asset.image_bytes,
                        }
                        events.append("asset_loaded")
                except Exception as e:
                    logger.warning("Asset load failed (FAIL_OPEN): %s", e)
                    events.append("asset_load_error")

        return GetCharacterOutput(
            success=True,
            character_context=char_context,
            events=events,
        )
```

### 5. GenerateImageCommand 참조 이미지 처리

참조 이미지가 존재하고 Provider가 이를 지원하면 `generate_with_reference()` 메서드를 호출합니다.

```python
# apps/chat_worker/application/commands/generate_image_command.py

@dataclass(frozen=True)
class GenerateImageInput:
    """Command 입력 DTO."""
    job_id: str
    prompt: str
    size: str = "1024x1024"
    quality: str = "medium"
    reference_image_bytes: bytes | None = None  # 캐릭터 참조 이미지 (신규)
    reference_image_mime: str = "image/png"

class GenerateImageCommand:
    """이미지 생성 Command (UseCase)."""

    async def execute(self, input_dto: GenerateImageInput) -> GenerateImageOutput:
        # 프롬프트 검증 (기존 로직)
        # ...

        has_reference = input_dto.reference_image_bytes is not None

        if has_reference and self._image_generator.supports_reference_images:
            # 참조 이미지 기반 생성
            reference = ReferenceImage(
                image_bytes=input_dto.reference_image_bytes,
                mime_type=input_dto.reference_image_mime,
            )
            result = await self._image_generator.generate_with_reference(
                prompt=input_dto.prompt,
                reference_images=[reference],
                size=input_dto.size,
                quality=input_dto.quality,
            )
            events.append("image_generated_with_reference")
        else:
            # 기본 생성 (참조 이미지 없음)
            result = await self._image_generator.generate(
                prompt=input_dto.prompt,
                size=input_dto.size,
                quality=input_dto.quality,
            )
            events.append("image_generated")

        return GenerateImageOutput(success=True, image_url=result.image_url, ...)
```

### 6. image_generation_node에서 컨텍스트 활용

LangGraph 노드에서 state의 `character_context.asset`을 읽어 Command에 전달합니다. 이 노드는 Infrastructure Layer의 Adapter 역할을 수행합니다.

```python
# apps/chat_worker/infrastructure/orchestration/langgraph/nodes/image_generation_node.py

async def _image_generation_node_inner(state: dict[str, Any]) -> dict[str, Any]:
    """Image Generation 노드 내부 로직.

    Node는 LangGraph 어댑터로서:
    - state → input DTO 변환
    - Command(UseCase) 호출
    - output → state 변환
    """
    job_id = state.get("job_id", "")
    query = state.get("query", "")

    # 캐릭터 참조 이미지 추출
    # 병렬 라우팅으로 character_subagent가 먼저 실행되어 state에 저장됨
    character_context = state.get("character_context") or {}
    character_asset = character_context.get("asset") if character_context else None
    reference_bytes = character_asset.get("image_bytes") if character_asset else None

    if reference_bytes:
        logger.info(
            "Using character reference image for generation",
            extra={
                "job_id": job_id,
                "character_code": character_asset.get("code"),
                "reference_size": len(reference_bytes),
            },
        )

    input_dto = GenerateImageInput(
        job_id=job_id,
        prompt=query,
        size=state.get("image_size") or default_size,
        quality=state.get("image_quality") or default_quality,
        reference_image_bytes=reference_bytes,  # 참조 이미지 전달
    )

    output = await command.execute(input_dto)
    # ...
```

---

## Provider 구현체

### Gemini Native (gemini-3-pro-image-preview)

**nano banana pro** 코드명의 `gemini-3-pro-image-preview` 모델은 참조 이미지를 네이티브로 지원합니다. Google의 genai SDK를 사용하여 TEXT + IMAGE 혼합 응답을 처리합니다.

```python
# apps/chat_worker/infrastructure/llm/image_generator/gemini_native.py

MODEL_REFERENCE_LIMITS = {
    "gemini-3-pro-image-preview": 14,  # nano banana pro - 캐릭터 5개 포함
    "gemini-2.5-flash-image": 3,       # 빠른 생성용
}

class GeminiNativeImageGenerator(ImageGeneratorPort):
    """Gemini Native Image Generator.

    특징:
    - 참조 이미지 기반 스타일 일관성 (캐릭터 참조)
    - 멀티턴 대화 지원
    - TEXT + IMAGE 혼합 응답
    """

    def __init__(self, model: str = "gemini-3-pro-image-preview"):
        self._model = model
        self._client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        self._max_reference = MODEL_REFERENCE_LIMITS.get(model, 3)

    @property
    def supports_reference_images(self) -> bool:
        return True

    @property
    def max_reference_images(self) -> int:
        return self._max_reference

    async def generate_with_reference(
        self,
        prompt: str,
        reference_images: list[ReferenceImage],
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        # 참조 이미지 개수 제한
        if len(reference_images) > self._max_reference:
            reference_images = reference_images[:self._max_reference]

        parts: list[Part] = []

        # 참조 이미지와 프롬프트 구성
        parts.append(Part.from_text(
            "다음 참조 이미지의 캐릭터 스타일을 유지하면서 이미지를 생성해주세요:"
        ))
        for ref in reference_images:
            parts.append(Part.from_bytes(
                data=ref.image_bytes,
                mime_type=ref.mime_type,
            ))
        parts.append(Part.from_text(f"\n요청: {prompt}"))

        # Gemini API 호출
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=Content(parts=parts),
            config=GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            ),
        )

        # 응답 파싱 (이미지 바이트 + 텍스트 설명)
        # ...
```

### OpenAI Responses API (gpt-image-1.5)

OpenAI는 Responses API의 `image_generation` 네이티브 툴을 사용합니다. 참조 이미지는 멀티모달 입력으로 전달하며, 모델이 프롬프트를 자동으로 최적화합니다.

```python
# apps/chat_worker/infrastructure/llm/image_generator/openai_responses.py

class OpenAIResponsesImageGenerator(ImageGeneratorPort):
    """OpenAI Responses API 이미지 생성기.

    장점:
    - 모델이 프롬프트 최적화 (더 나은 결과)
    - 이미지 + 설명 텍스트 동시 생성
    - 대화 컨텍스트 활용 가능
    """

    def __init__(self, model: str = "gpt-5.2"):
        self._model = model
        self._client = AsyncOpenAI()

    @property
    def supports_reference_images(self) -> bool:
        return True

    @property
    def max_reference_images(self) -> int:
        return 1  # Gemini보다 제한적

    async def generate_with_reference(
        self,
        prompt: str,
        reference_images: list[ReferenceImage],
        size: str = "1024x1024",
        quality: str = "medium",
    ) -> ImageGenerationResult:
        reference = reference_images[0] if reference_images else None

        if reference:
            input_content = self._build_multimodal_input(prompt, reference)
        else:
            input_content = self._build_input_prompt(prompt)

        response = await self._client.responses.create(
            model=self._model,
            input=input_content,
            tools=[{
                "type": "image_generation",
                "image_generation": {
                    "size": size,
                    "quality": quality,
                },
            }],
        )
        # ...

    def _build_multimodal_input(
        self,
        user_prompt: str,
        reference: ReferenceImage,
    ) -> list[dict]:
        """참조 이미지를 포함한 멀티모달 입력을 구성합니다."""
        image_b64 = base64.b64encode(reference.image_bytes).decode("utf-8")
        data_url = f"data:{reference.mime_type};base64,{image_b64}"

        return [
            {
                "type": "input_text",
                "text": f"""다음 캐릭터 이미지의 스타일을 참고하여 새로운 이미지를 생성해주세요.

캐릭터 스타일:
- 이 캐릭터의 색상, 형태, 분위기를 유지해주세요
- 친근하고 귀여운 느낌을 살려주세요

요청: {user_prompt}""",
            },
            {
                "type": "input_image",
                "image_url": data_url,
            },
        ]
```

---

## 데이터 흐름

전체 데이터 흐름을 정리하면 다음과 같습니다.

```
character_code: "char-pet"
       │
       ▼ CharacterService.to_cdn_code()
cdn_code: "pet"
       │
       ▼ CharacterAssetLoader.get_asset()
asset: {
  code: "pet",
  image_url: "https://cdn.eco2.kr/characters/pet.png",
  image_bytes: <bytes>,
}
       │
       ▼ state["character_context"]["asset"]
character_context: {
  name: "페트리",
  type: "재활용",
  dialog: "재활용해줘서 고마워!",
  asset: { ... }
}
       │
       ▼ image_generation_node
GenerateImageInput(
  prompt="페트리가 페트병 재활용하는 모습",
  reference_image_bytes=<bytes>,
)
       │
       ▼ ImageGeneratorPort.generate_with_reference()
       │
       ├─ Gemini: gemini-3-pro-image-preview (nano banana pro)
       │   └─ 네이티브 참조 이미지 지원 (최대 14개)
       │
       └─ OpenAI: Responses API + gpt-image-1.5
           └─ 멀티모달 입력으로 스타일 참조 (최대 1개)
```

---

## 테스트

### 단위 테스트

캐릭터 코드 변환 로직에 대한 단위 테스트를 작성했습니다.

```python
# apps/chat_worker/tests/unit/application/integrations/character/test_character_service.py

class TestCharacterService:
    def test_to_cdn_code_with_prefix(self):
        """char- 접두사가 있는 코드를 CDN 코드로 변환합니다."""
        assert CharacterService.to_cdn_code("char-pet") == "pet"
        assert CharacterService.to_cdn_code("char-battery") == "battery"

    def test_to_cdn_code_without_prefix(self):
        """char- 접두사가 없는 코드는 그대로 반환합니다."""
        assert CharacterService.to_cdn_code("pet") == "pet"

    def test_to_cdn_code_none(self):
        """None 입력 시 None을 반환합니다."""
        assert CharacterService.to_cdn_code(None) is None

    def test_to_cdn_code_empty(self):
        """빈 문자열 입력 시 None을 반환합니다."""
        assert CharacterService.to_cdn_code("") is None
```

### 테스트 실행 결과

```bash
$ pytest apps/chat_worker/tests/unit/application/integrations/character/ -v

# 결과: 12 passed in 0.21s
```

---

## 관련 문서

- [#0: LangGraph 기반 클린 아키텍처 초안](https://rooftopsnow.tistory.com/164)
- [#2: Subagent 기반 도메인 연동](https://rooftopsnow.tistory.com/166)
- [#7: Application Layer](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)
- [#8: Infrastructure Layer](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)
- [#17: Image Generation](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)
- [#19: LangGraph Send API 기반 동적 라우팅](https://rooftopsnow.tistory.com/category/%EC%9D%B4%EC%BD%94%EC%97%90%EC%BD%94%28Eco%C2%B2%29/Agent)
- [#23: Observability - LangSmith + Prometheus 통합](https://rooftopsnow.tistory.com/203)

---

## 정리

| 항목 | 내용 |
|------|------|
| **문제** | 캐릭터 언급 시 스타일 일관성 부재 |
| **해결** | CDN 에셋 로딩 + 참조 이미지 기반 생성 |
| **아키텍처** | Clean Architecture (Port/Adapter 패턴) |
| **병렬 처리** | LangGraph Send API (character ↔ image_generation) |
| **Multi-Model** | Gemini (nano banana pro) + OpenAI (Responses API) |
| **장애 대응** | FAIL_OPEN 정책 (에셋 로딩 실패 시에도 기본 이미지 생성) |

다음 포스팅에서는 [#25: Native Token Streaming](../plans/langgraph-native-streaming-adr.md)을 다룰 예정입니다. `ainvoke` → `astream_events` 전환을 통해 네이티브 토큰 스트리밍을 구현합니다.
