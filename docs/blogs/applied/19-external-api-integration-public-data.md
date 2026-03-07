# 공공데이터포털 API 연동: Clean Architecture 패턴 적용

> 분리배출 챗봇에서 공공데이터포털 API(기상청, 한국환경공단, 행정안전부)를 Clean Architecture로 통합한 사례
>
> **작성일**: 2026-01-16

---

## 1. 배경

### 1.1 요구사항

분리배출 챗봇의 답변 품질 향상을 위해 외부 실시간 데이터 연동이 필요:

| 데이터 | 용도 | 예시 |
|--------|------|------|
| **날씨 정보** | 날씨 기반 분리배출 팁 | "비 예보가 있어요. 종이류는 실내 보관 후 배출하세요." |
| **수거함 위치** | 폐전자제품 수거함 안내 | "강남구 이마트 용산점에 수거함이 있어요." |
| **대형폐기물 수수료** | 지역별 수수료 조회 | "강남구에서 소파 배출 시 12,000원이에요." |
| **재활용품 시세** | 재활용품 예상 가격 | "캔 1kg당 약 1,200원 정도예요." |

### 1.2 연동할 API 목록

| API | 제공 기관 | 데이터 |
|-----|----------|--------|
| 기상청 단기예보 | 기상청 | 현재 기온, 강수 형태, 예보 |
| 폐전자제품 수거함 | 한국환경공단 (KECO) | 전국 12,800+ 수거함 위치 |
| 생활쓰레기배출정보 | 행정안전부 (MOIS) | 지역별 대형폐기물 수거 정보 |
| 재활용자원 거래가격 | 한국환경공단 | 품목별 시세 |

---

## 2. 아키텍처 설계

### 2.1 Clean Architecture 적용

```
┌─────────────────────────────────────────────────────────────────┐
│                        Application Layer                         │
├─────────────────────────────────────────────────────────────────┤
│  Ports (추상 인터페이스)          Commands (UseCase)              │
│  ├── WeatherClientPort           ├── GetWeatherCommand          │
│  ├── CollectionPointClientPort   ├── SearchCollectionPointCmd   │
│  ├── BulkWasteClientPort         ├── SearchBulkWasteCommand     │
│  └── RecyclablePriceClientPort   └── SearchRecyclablePriceCmd   │
│                                                                  │
│  Services (순수 비즈니스 로직)    DTOs                            │
│  └── WeatherService              └── AnswerContext               │
│      (좌표변환, 팁생성)               (컨텍스트 통합)              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure Layer                        │
├─────────────────────────────────────────────────────────────────┤
│  Adapters (HTTP 구현)                                            │
│  ├── integrations/kma/      ← 기상청 API                         │
│  ├── integrations/keco/     ← 한국환경공단 API                    │
│  ├── integrations/bulk_waste/ ← 행정안전부 API                   │
│  └── integrations/recyclable_price/                              │
│                                                                  │
│  LangGraph Nodes (오케스트레이션)                                 │
│  ├── weather_node.py        ← state 변환 + Command 호출          │
│  ├── collection_point_node.py                                    │
│  ├── bulk_waste_node.py                                          │
│  └── recyclable_price_node.py                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 레이어별 책임

| 레이어 | 구성 요소 | 책임 |
|--------|----------|------|
| **Application** | Port | 추상 인터페이스 정의 |
| | Command | 오케스트레이션, Port 호출 |
| | Service | 순수 비즈니스 로직 (Port 의존 없음) |
| **Infrastructure** | Adapter | HTTP 구현, API 응답 파싱 |
| | Node | LangGraph 상태 변환, Command 호출 |

### 2.3 데이터 흐름

```
사용자 메시지: "강남구에서 폐휴대폰 어디서 버려?"

1. intent_node → intent: "collection_point"
2. router → collection_point_node
3. collection_point_node:
   - state에서 address_keyword 추출 ("강남구")
   - SearchCollectionPointCommand.execute() 호출
4. Command:
   - CollectionPointClientPort.search_collection_points() 호출
   - 결과를 context dict로 변환
5. collection_point_node:
   - state["collection_point_context"] = context
6. answer_node:
   - context를 프롬프트에 포함
   - LLM이 수거함 위치 안내 답변 생성
```

---

## 3. Port 설계

### 3.1 WeatherClientPort

```python
# application/ports/weather_client.py

class PrecipitationType(IntEnum):
    """강수 형태 (기상청 PTY 코드)."""
    NONE = 0
    RAIN = 1
    RAIN_SNOW = 2
    SNOW = 3
    SHOWER = 4

@dataclass(frozen=True)
class CurrentWeatherDTO:
    """현재 날씨 정보."""
    temperature: float      # 기온 (°C)
    precipitation: float    # 강수량 (mm)
    precipitation_type: PrecipitationType
    humidity: int           # 습도 (%)
    sky_status: SkyStatus

class WeatherClientPort(ABC):
    @abstractmethod
    async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
        """현재 날씨 조회 (기상청 격자 좌표 기준)."""
        pass
```

**설계 결정**:
- `frozen=True`: DTO 불변성 보장
- 격자 좌표 사용: 위경도 → 격자 변환은 Service에서

### 3.2 CollectionPointClientPort

```python
# application/ports/collection_point_client.py

@dataclass(frozen=True)
class CollectionPointDTO:
    """수거함 위치 정보."""
    id: int
    name: str
    collection_types: tuple[str, ...]  # 불변 tuple
    address: str | None = None
    place_category: str | None = None
    fee: str | None = None

    @property
    def is_free(self) -> bool:
        """무료 여부."""
        if self.fee is None:
            return True
        return "무료" in self.fee or self.fee == ""

class CollectionPointClientPort(ABC):
    @abstractmethod
    async def search_collection_points(
        self,
        address_keyword: str | None = None,
        name_keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> CollectionPointSearchResponse:
        """수거함 위치 검색."""
        pass
```

**설계 결정**:
- `collection_types: tuple[str, ...]`: `list` 대신 `tuple`로 불변성 강화
- `is_free` 프로퍼티: 무료/유료 판단 로직 캡슐화

---

## 4. Adapter 구현

### 4.1 기상청 API Adapter

```python
# infrastructure/integrations/kma/kma_weather_http_client.py

class KmaWeatherHttpClient(WeatherClientPort):
    """기상청 단기예보 API HTTP 클라이언트."""

    BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0"

    async def get_current_weather(self, nx: int, ny: int) -> WeatherResponse:
        # 발표 시각 계산 (정시 기준)
        base_date, base_time = self._calculate_base_datetime()

        params = {
            "serviceKey": self._api_key,
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny,
            "dataType": "JSON",
        }

        response = await self._client.get("/getUltraSrtNcst", params=params)
        return self._parse_current_weather(response.json())

    def _parse_current_weather(self, data: dict) -> WeatherResponse:
        """API 응답 파싱."""
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        # 카테고리별 값 추출
        values = {}
        for item in items:
            values[item["category"]] = item["obsrValue"]

        return WeatherResponse(
            success=True,
            current=CurrentWeatherDTO(
                temperature=float(values.get("T1H", 0)),
                precipitation=float(values.get("RN1", 0)),
                precipitation_type=PrecipitationType(int(values.get("PTY", 0))),
                humidity=int(values.get("REH", 0)),
                sky_status=SkyStatus(int(values.get("SKY", 1))),
            ),
        )
```

**기상청 API 특이사항**:
- 격자 좌표 시스템: 위경도 → LCC 투영 변환 필요
- 발표 시각 규칙: 매 정시 + 10분에 데이터 갱신
- 카테고리 코드: T1H(기온), PTY(강수형태), RN1(강수량) 등

### 4.2 한국환경공단 API Adapter

```python
# infrastructure/integrations/keco/keco_collection_point_client.py

class KecoCollectionPointClient(CollectionPointClientPort):
    """한국환경공단 폐전자제품 수거함 API 클라이언트."""

    BASE_URL = "https://api.odcloud.kr/api/15106385/v1"
    DATASET_ID = "uddi:4977d714-dca6-4bda-a10f-9bed30e2ce9c"

    async def search_collection_points(
        self,
        address_keyword: str | None = None,
        name_keyword: str | None = None,
        page: int = 1,
        page_size: int = 10,
    ) -> CollectionPointSearchResponse:
        params = {
            "page": page,
            "perPage": min(page_size, 1000),
            "returnType": "JSON",
        }

        # 검색 조건 (LIKE 연산)
        if address_keyword:
            params["cond[수거장소(주소)::LIKE]"] = address_keyword
        if name_keyword:
            params["cond[상호명::LIKE]"] = name_keyword

        response = await self._client.get(f"/{self.DATASET_ID}", params=params)
        return self._parse_response(response.json())

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """안전한 정수 변환."""
        if value is None:
            return default
        try:
            return int(value)
        except (ValueError, TypeError):
            return default

    def _parse_collection_point(self, item: dict) -> CollectionPointDTO:
        # 수거종류 파싱 (쉼표 구분) → 불변 tuple
        collection_types_raw = item.get("수거종류", "")
        collection_types = tuple(
            t.strip() for t in collection_types_raw.split(",") if t.strip()
        ) if collection_types_raw else ()

        return CollectionPointDTO(
            id=self._safe_int(item.get("순번")),
            name=item.get("상호명", ""),
            collection_types=collection_types,
            address=item.get("수거장소(주소)"),
            place_category=item.get("장소구분"),
            fee=item.get("수거비용"),
        )
```

**공공데이터포털 API 특이사항**:
- 인증: `Authorization: Infuser {API_KEY}` 헤더 또는 `serviceKey` 파라미터
- 검색: `cond[필드명::LIKE]=검색어` 형태
- 페이징: `page`, `perPage` (최대 1000)

---

## 5. Service 구현

### 5.1 WeatherService (순수 비즈니스 로직)

```python
# application/services/weather_service.py

class WeatherService:
    """날씨 서비스 (순수 로직, Port 의존 없음)."""

    @staticmethod
    def convert_to_grid(lat: float, lon: float) -> tuple[int, int]:
        """위경도 → 기상청 격자좌표 변환 (LCC 투영)."""
        # Lambert Conformal Conic 투영 변환
        degrad = math.pi / 180.0
        re = 6371.00877 / 5.0  # 지구 반경 / 격자 간격

        # ... LCC 계산 ...

        return nx, ny

    @staticmethod
    def generate_weather_tip(
        weather: CurrentWeatherDTO | None,
        waste_category: str | None = None,
    ) -> str | None:
        """날씨 기반 분리배출 팁 생성."""
        if weather is None:
            return None

        tips = []

        # 강수 체크
        if weather.precipitation_type == PrecipitationType.RAIN:
            tips.append("비 예보가 있어요. 종이류는 젖지 않게 보관 후 배출하세요.")
        elif weather.precipitation_type == PrecipitationType.SNOW:
            tips.append("눈 예보가 있어요. 배출 시 미끄럼 주의하세요.")

        # 기온 체크
        if weather.temperature >= 30:
            tips.append(f"기온이 {weather.temperature:.0f}°C로 높아요. 음식물 쓰레기는 빨리 버리세요!")
        elif weather.temperature <= 0:
            tips.append(f"기온이 {weather.temperature:.0f}°C로 영하예요. 액체류 동결에 주의하세요.")

        return " ".join(tips) if tips else None
```

**Service 설계 원칙**:
- Port 의존 없음 (순수 함수)
- 테스트 용이성: API 호출 없이 로직만 테스트 가능
- 재사용성: Command 없이 직접 호출 가능

---

## 6. Command 구현

### 6.1 GetWeatherCommand

```python
# application/commands/get_weather_command.py

@dataclass(frozen=True)
class GetWeatherInput:
    job_id: str
    lat: float | None = None
    lon: float | None = None
    waste_category: str | None = None

@dataclass
class GetWeatherOutput:
    success: bool
    weather_context: dict[str, Any] | None = None
    needs_location: bool = False
    error_message: str | None = None
    events: list[str] = field(default_factory=list)

class GetWeatherCommand:
    """날씨 정보 조회 Command (UseCase)."""

    def __init__(self, weather_client: WeatherClientPort):
        self._weather_client = weather_client

    async def execute(self, input_dto: GetWeatherInput) -> GetWeatherOutput:
        events = []

        # 1. 좌표 확인
        if input_dto.lat is None or input_dto.lon is None:
            return GetWeatherOutput(success=True, needs_location=True, events=["location_required"])

        # 2. 격자 좌표 변환 (Service)
        nx, ny = WeatherService.convert_to_grid(input_dto.lat, input_dto.lon)
        events.append("grid_converted")

        # 3. API 호출 (Port)
        response = await self._weather_client.get_current_weather(nx, ny)
        events.append("weather_fetched")

        # 4. 날씨 팁 생성 (Service)
        tip = WeatherService.generate_weather_tip(response.current, input_dto.waste_category)

        # 5. 컨텍스트 반환
        return GetWeatherOutput(
            success=True,
            weather_context={
                "type": "weather",
                "temperature": response.current.temperature,
                "tip": tip,
                "context": f"🌤️ 현재 기온 {response.current.temperature:.0f}°C. {tip or ''}",
            },
            events=events,
        )
```

**Command 설계 원칙**:
- Port 호출만 담당 (비즈니스 로직은 Service로)
- events 리스트로 실행 흐름 추적
- 실패 시에도 graceful한 응답 반환

---

## 7. Node 구현

### 7.1 weather_node

```python
# infrastructure/orchestration/langgraph/nodes/weather_node.py

def create_weather_node(
    weather_client: WeatherClientPort,
    event_publisher: ProgressNotifierPort,
):
    """날씨 노드 팩토리."""

    command = GetWeatherCommand(weather_client=weather_client)

    async def weather_node(state: dict[str, Any]) -> dict[str, Any]:
        job_id = state.get("job_id", "")

        # Progress 이벤트 (UX)
        await event_publisher.notify_stage(
            task_id=job_id,
            stage="weather",
            status="started",
            progress=40,
            message="🌤️ 날씨 정보 확인 중...",
        )

        # state에서 좌표 추출
        user_location = state.get("user_location")
        lat = user_location.get("lat") if user_location else None
        lon = user_location.get("lon") if user_location else None

        input_dto = GetWeatherInput(job_id=job_id, lat=lat, lon=lon)
        output = await command.execute(input_dto)

        # state 업데이트
        return {**state, "weather_context": output.weather_context}

    return weather_node
```

**Node 설계 원칙**:
- "얇은 어댑터": state 변환 + Command 호출만
- Progress 이벤트 발행 (SSE를 통한 UX 피드백)
- 실패해도 파이프라인 계속 진행 (날씨는 보조 정보)

---

## 8. Factory 통합

### 8.1 LangGraph 파이프라인 연결

```python
# infrastructure/orchestration/langgraph/factory.py

def create_chat_graph(
    llm: LLMClientPort,
    # ... 기존 파라미터 ...
    weather_client: WeatherClientPort | None = None,
    collection_point_client: CollectionPointClientPort | None = None,
) -> StateGraph:

    # 노드 생성
    if weather_client is not None:
        weather_node = create_weather_node(weather_client, event_publisher)
    else:
        async def weather_node(state):
            return {**state, "weather_context": None}

    # 노드 등록
    graph.add_node("weather", weather_node)
    graph.add_node("collection_point", collection_point_node)

    # 라우팅 연결
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "waste": "waste_rag",
            "collection_point": "collection_point",
            # ...
        },
    )

    # 모든 노드 → Answer
    for node_name in ["weather", "collection_point", ...]:
        graph.add_edge(node_name, final_target)
```

### 8.2 Answer Context 통합

```python
# application/dto/answer_context.py

@dataclass
class AnswerContext:
    classification: dict | None = None
    disposal_rules: dict | None = None
    weather_context: str | None = None           # 날씨 팁
    collection_point_context: str | None = None  # 수거함 위치
    bulk_waste_context: str | None = None        # 대형폐기물 정보
    recyclable_price_context: str | None = None  # 재활용품 시세

    def to_prompt_context(self) -> str:
        """LLM 프롬프트용 컨텍스트."""
        parts = []
        if self.weather_context:
            parts.append(f"## Weather Info\n{self.weather_context}")
        if self.collection_point_context:
            parts.append(f"## Collection Point Info\n{self.collection_point_context}")
        # ...
        return "\n\n".join(parts)
```

---

## 9. 설정 및 배포

### 9.1 환경 변수

```python
# setup/config.py

@dataclass
class Settings:
    # 기상청 단기예보 API
    kma_api_key: str | None = None
    kma_api_timeout: float = 10.0

    # 한국환경공단 폐전자제품 수거함 API
    keco_api_key: str | None = None
    keco_api_timeout: float = 15.0

    # 행정안전부 생활쓰레기배출정보 API
    mois_waste_api_key: str | None = None
    mois_waste_api_timeout: float = 15.0
```

### 9.2 Kubernetes Secret (ExternalSecret)

```yaml
# workloads/secrets/external-secrets/dev/chat-worker-secrets.yaml

apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: chat-worker-secret
spec:
  secretStoreRef:
    kind: ClusterSecretStore
    name: aws-ssm-store
  data:
    - secretKey: kmaApiKey
      remoteRef:
        key: /sesacthon/dev/api/chat/kma-api-key
    - secretKey: kecoApiKey
      remoteRef:
        key: /sesacthon/dev/api/chat/keco-api-key
    - secretKey: moisWasteApiKey
      remoteRef:
        key: /sesacthon/dev/api/chat/mois-waste-api-key
  target:
    template:
      data:
        CHAT_WORKER_KMA_API_KEY: '{{ .kmaApiKey }}'
        CHAT_WORKER_KECO_API_KEY: '{{ .kecoApiKey }}'
        CHAT_WORKER_MOIS_WASTE_API_KEY: '{{ .moisWasteApiKey }}'
```

---

## 10. 테스트

### 10.1 단위 테스트

```python
# tests/unit/infrastructure/integrations/keco/test_keco_collection_point_client.py

class TestKecoCollectionPointClient:

    @pytest.mark.asyncio
    async def test_search_collection_points_success(self, client, mock_response_data):
        """검색 성공 테스트."""
        mock_response = MagicMock()
        mock_response.json.return_value = mock_response_data
        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        with patch.object(client, "_get_client", return_value=mock_http_client):
            result = await client.search_collection_points(address_keyword="용산")

        assert result.total_count == 2
        assert len(result.results) == 2
        assert result.results[0].name == "이마트 용산점"

    def test_safe_int_parsing(self, client):
        """_safe_int 안전한 정수 변환 테스트."""
        assert client._safe_int(123) == 123
        assert client._safe_int("456") == 456
        assert client._safe_int(None) == 0
        assert client._safe_int("abc") == 0
        assert client._safe_int("abc", default=-1) == -1
```

### 10.2 통합 테스트 (실제 API)

```python
# 로컬 테스트
CHAT_WORKER_KECO_API_KEY=your_api_key \
PYTHONPATH=apps python -c "
import asyncio
from chat_worker.infrastructure.integrations.keco import KecoCollectionPointClient

async def test():
    client = KecoCollectionPointClient(api_key='your_api_key')
    result = await client.search_collection_points(address_keyword='강남구', page_size=3)
    print(f'총 {result.total_count}개 중 {len(result.results)}개 조회')
    for point in result.results:
        print(f'  - {point.name}: {point.address}')
    await client.close()

asyncio.run(test())
"
```

---

## 11. 결과

### 11.1 통합된 API

| API | Port | Adapter | Node | 상태 |
|-----|------|---------|------|------|
| 기상청 단기예보 | `WeatherClientPort` | `KmaWeatherHttpClient` | `weather_node` | ✅ |
| KECO 수거함 | `CollectionPointClientPort` | `KecoCollectionPointClient` | `collection_point_node` | ✅ |
| MOIS 대형폐기물 | `BulkWasteClientPort` | `MoisBulkWasteHttpClient` | `bulk_waste_node` | ✅ |
| 재활용품 시세 | `RecyclablePriceClientPort` | `RecyclablePriceHttpClient` | `recyclable_price_node` | ✅ |

### 11.2 아키텍처 장점

1. **테스트 용이성**: Port를 Mock하여 API 호출 없이 테스트
2. **유연한 확장**: 새 API 추가 시 Port → Adapter → Node 패턴 반복
3. **장애 격리**: 개별 API 실패가 전체 파이프라인에 영향 없음
4. **설정 분리**: API 키는 ExternalSecret으로 안전하게 관리

### 11.3 LangGraph 파이프라인

```
START → intent → [vision?] → router
                               │
        ┌──────┬───────┬───────┼───────────┬───────────┬───────────┬───────┐
        ▼      ▼       ▼       ▼           ▼           ▼           ▼       ▼
     waste  char    location  bulk      weather   collection   price  general
     (RAG)  (gRPC)  (Kakao)   (MOIS)    (KMA)     (KECO)      (KECO)
        │      │       │        │          │           │           │       │
        ▼      │       │        │          │           │           │       │
    [feedback] │       │        │          │           │           │       │
        │      │       │        │          │           │           │       │
        └──────┴───────┴────────┴──────────┴───────────┴───────────┴───────┘
                                   │
                                   ▼
                            [summarize?]
                                   │
                                   ▼
                                answer → END
```

---

## 12. 참고 자료

- [공공데이터포털](https://www.data.go.kr/)
- [기상청 단기예보 API](https://www.data.go.kr/data/15084084/openapi.do)
- [한국환경공단 폐전자제품 수거함](https://www.data.go.kr/data/15106385/fileData.do)
- [행정안전부 생활쓰레기배출정보](https://www.data.go.kr/)
- [LangGraph 공식 문서](https://langchain-ai.github.io/langgraph/)
