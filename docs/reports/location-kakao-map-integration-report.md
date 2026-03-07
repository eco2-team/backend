# Location + Kakao Map API 통합 개발 리포트

> **작성일**: 2026-01-23
> **대상**: `apps/location` (Backend) + `frontend/src/components/map` (Frontend)
> **목표**: Kakao Local API 통합을 통한 위치 검색 고도화 및 Map 페이지 UX 개선

| 링크 | URL |
|------|-----|
| **Backend Repo** | [eco2-team/backend](https://github.com/eco2-team/backend/tree/develop) |
| **Frontend Repo** | [eco2-team/frontend](https://github.com/eco2-team/frontend/tree/develop) |
| **Service** | [frontend.dev.growbin.app](https://frontend.dev.growbin.app) |

---

## 아키텍처

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite + TanStack Query)                            │
│                                                                      │
│  ┌────────────┐  ┌────────────┐  ┌───────────┐  ┌───────────────┐  │
│  │ MapSearch  │  │ MapCard    │  │ MapDetail │  │ StoreCategory │  │
│  │ Bar        │  │ List       │  │ Sheet     │  │ Filter        │  │
│  │ (suggest)  │  │ (centers)  │  │ (detail)  │  │ (store_cat)   │  │
│  └──────┬─────┘  └──────┬─────┘  └─────┬─────┘  └───────┬───────┘  │
│         │               │               │                │          │
│  ┌──────▼───────────────▼───────────────▼────────────────▼────────┐ │
│  │              MapService (axios HTTP Client)                     │ │
│  │  getLocations / searchLocations / suggestPlaces / getDetail    │ │
│  └────────────────────────────────┬───────────────────────────────┘ │
└───────────────────────────────────┼─────────────────────────────────┘
                                    │ REST API (HTTPS)
┌───────────────────────────────────▼─────────────────────────────────┐
│  Backend (FastAPI + async)                                           │
│                                                                      │
│  ┌─ Presentation ───────────────────────────────────────────────┐   │
│  │  LocationController: /centers, /search, /suggest, /centers/id│   │
│  │  Schemas: LocationEntry, LocationDetail, SuggestEntry        │   │
│  └──────────────────────────────────┬───────────────────────────┘   │
│                                     │                               │
│  ┌─ Application ────────────────────▼───────────────────────────┐   │
│  │  Queries: GetNearbyCenters, SearchByKeyword,                 │   │
│  │           SuggestPlaces, GetCenterDetail                     │   │
│  │  Services: CategoryClassifier, LocationEntryBuilder,         │   │
│  │            ZoomPolicy                                        │   │
│  │  DTOs: LocationEntryDTO, LocationDetailDTO, SuggestEntryDTO  │   │
│  └─────────────┬──────────────────────────────┬─────────────────┘   │
│                │                              │                     │
│  ┌─────────────▼──────────────┐  ┌────────────▼─────────────────┐  │
│  │  Infrastructure: PostgreSQL │  │  Infrastructure: Kakao API   │  │
│  │  PostGIS earth_distance     │  │  /v2/local/search/keyword    │  │
│  │  Haversine fallback         │  │  KakaoAK 인증, httpx async   │  │
│  │  SqlaLocationReader         │  │  KakaoLocalHttpClient        │  │
│  └─────────────────────────────┘  └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                        │
                            ┌───────────▼───────────┐
                            │  Kakao Map Navigation │
                            │  (Frontend 직접 호출)  │
                            │  map.kakao.com/link/   │
                            │  from/{origin}/to/{dest}│
                            └───────────────────────┘
```

---

## 1. Backend: Kakao Local API 통합

### 1.1 설계 배경

기존 Location 서비스는 PostgreSQL의 `NormalizedLocationSite` 테이블에 정규화된 재활용 센터/제로웨이스트 매장 데이터만을 조회하는 **읽기 전용 서비스**였습니다. 그러나 DB에 수록되지 않은 장소를 검색하거나, 주소/키워드 기반 자동완성을 제공하려면 외부 Geocoding API 연동이 필수적입니다.

Kakao Local API를 선택한 이유:

| 기준 | Kakao Local | Google Places | Naver Map |
|------|-------------|---------------|-----------|
| 국내 장소 커버리지 | 최상 | 양호 | 양호 |
| 무료 할당량 | 일 30만 건 | 월 $200 크레딧 | 일 10만 건 |
| 응답 속도 (Korea) | ~50ms | ~120ms | ~80ms |
| `place_url` 제공 | O (카카오맵 상세) | X | X |
| 프론트엔드 Map SDK 호환 | Kakao Maps SDK 연동 | 별도 SDK 필요 | 별도 SDK 필요 |

프론트엔드가 이미 Kakao Maps SDK를 사용 중이었으므로, **place_url을 통한 상세 페이지 연결**과 **네비게이션 URL 스킴 활용**이 자연스럽게 가능한 Kakao Local API를 채택했습니다.

### 1.2 Port/Adapter 패턴

Clean Architecture 원칙에 따라 Kakao API 의존성을 Port 인터페이스로 추상화했습니다. 이를 통해 테스트 시 Mock 주입이 가능하고, 향후 다른 Geocoding 서비스로의 교체도 Application 계층 변경 없이 수행할 수 있습니다.

**Port 정의** (`application/ports/kakao_local_client.py`):

```python
class KakaoLocalClientPort(ABC):
    """카카오 로컬 API 포트."""

    @abstractmethod
    async def search_keyword(
        self,
        query: str,
        x: float | None = None,    # longitude
        y: float | None = None,    # latitude
        radius: int = 5000,         # meters
        page: int = 1,
        size: int = 15,
        sort: str = "accuracy",     # accuracy | distance
    ) -> KakaoSearchResponse: ...
```

Port에 정의된 DTO들은 불변 데이터 클래스로 설계했습니다:

| DTO | 역할 | 주요 필드 |
|-----|------|----------|
| `KakaoPlaceDTO` | 단일 장소 | id, place_name, x/y, place_url, distance, phone |
| `KakaoSearchMeta` | 페이지네이션 | total_count, pageable_count, is_end |
| `KakaoSearchResponse` | 응답 래퍼 | places[], meta, query |

`KakaoPlaceDTO`는 Kakao API가 좌표를 문자열(`x`, `y`)로 반환하는 특성을 반영하여, `latitude`/`longitude` property를 통해 float 변환을 캡슐화합니다:

```python
@dataclass(frozen=True)
class KakaoPlaceDTO:
    x: str  # longitude (Kakao 원본)
    y: str  # latitude  (Kakao 원본)

    @property
    def latitude(self) -> float:
        return float(self.y)

    @property
    def longitude(self) -> float:
        return float(self.x)

    @property
    def distance_meters(self) -> int | None:
        """거리 문자열 → 정수 변환 (Kakao는 "1234" 형태로 반환)."""
        if self.distance:
            try:
                return int(self.distance)
            except ValueError:
                return None
        return None
```

### 1.3 HTTP Client 구현

**Adapter** (`infrastructure/integrations/kakao/kakao_client.py`):

```python
class KakaoLocalHttpClient(KakaoLocalClientPort):
    BASE_URL = "https://dapi.kakao.com/v2/local/search"

    def __init__(self, api_key: str, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
```

주요 설계 결정:

| 결정 | 근거 |
|------|------|
| `httpx.AsyncClient` | FastAPI의 async 생태계와 자연스러운 호환. connection pooling 내장 |
| Lazy Initialization + Lock | 앱 시작 시 API 키 미설정 상태에서도 안전하게 기동. 첫 요청 시 클라이언트 생성 |
| `asyncio.Lock` (Double-Check) | 동시 요청 시 클라이언트 중복 생성 방지 |
| `size` 상한 15 | Kakao API 자체 제약 (`min(size, 15)`) |
| `radius` 상한 20000m | Kakao API 최대 반경 제약 (`min(radius, 20000)`) |

에러 처리는 세 단계로 분리됩니다:

```python
try:
    response = await client.get("/keyword.json", params=params)
    response.raise_for_status()
except httpx.HTTPStatusError as e:     # 4xx/5xx
    logger.error("Kakao API HTTP error", extra={...})
except httpx.TimeoutException:          # 타임아웃
    logger.error("Kakao API timeout", extra={...})
except Exception as e:                  # 네트워크 등 기타
    logger.error("Kakao keyword search failed", extra={...})
```

### 1.4 Query 계층: 비즈니스 오케스트레이션

네 개의 Query가 각각 독립적인 Use Case를 담당합니다:

#### (1) SearchByKeywordQuery — 하이브리드 검색

가장 복잡한 오케스트레이션 로직을 포함합니다. **DB 결과(정확도 높음)와 Kakao 결과(커버리지 넓음)를 병합**하여 사용자에게 최적의 검색 결과를 제공합니다.

```
[사용자 입력: "강남역 재활용센터"]
         │
         ▼
┌─────────────────────────────┐
│ 1. Kakao 키워드 검색         │  sort=accuracy
│    → 첫 번째 결과의 좌표 획득 │
└──────────────┬──────────────┘
               │ anchor_lat, anchor_lon
         ┌─────┴─────┐
         ▼           ▼
┌────────────┐ ┌─────────────┐
│ 2. Kakao   │ │ 3. DB       │  병렬 수행
│ 재검색     │ │ spatial     │
│ sort=dist  │ │ query       │
└──────┬─────┘ └──────┬──────┘
       │               │
       └───────┬───────┘
               ▼
┌─────────────────────────────┐
│ 4. 50m 좌표 중복 제거        │
│ 5. DB 우선 + Kakao 보충      │
│ 6. distance_km 기준 정렬     │
└─────────────────────────────┘
```

중복 제거 로직은 **Haversine 공식**으로 두 좌표 간 실거리를 계산하여 50m 이내면 동일 장소로 판별합니다:

```python
@staticmethod
def _is_duplicate(
    lat: float, lon: float, coords: list[tuple[float, float]], threshold_m: float = 50.0
) -> bool:
    for db_lat, db_lon in coords:
        dist = _haversine_meters(lat, lon, db_lat, db_lon)
        if dist <= threshold_m:
            return True
    return False
```

DB에 없는 Kakao 전용 결과는 **음수 ID**를 부여하여 프론트엔드에서 source를 구분할 수 있도록 합니다:

```python
kakao_id_counter = -1
for place in kakao_places:
    if self._is_duplicate(place.latitude, place.longitude, db_coords):
        continue
    kakao_entries.append(self._kakao_to_entry(place, anchor_lat, anchor_lon, kakao_id_counter))
    kakao_id_counter -= 1
```

#### (2) SuggestPlacesQuery — 자동완성

가장 단순한 패턴입니다. Kakao API의 accuracy 정렬을 그대로 활용하며, 최대 5개로 제한합니다:

```python
class SuggestPlacesQuery:
    async def execute(self, query: str) -> list[SuggestEntryDTO]:
        response = await self._kakao.search_keyword(
            query=query, size=MAX_SUGGEST_RESULTS, sort="accuracy",
        )
        return [SuggestEntryDTO(
            place_name=place.place_name,
            address=place.road_address_name or place.address_name,
            latitude=place.latitude,
            longitude=place.longitude,
            place_url=place.place_url or None,
        ) for place in response.places]
```

#### (3) GetCenterDetailQuery — 상세 조회 + Kakao 보강

DB에서 ID 기반으로 조회한 뒤, **Kakao API로 place_url과 전화번호를 보강**합니다. Kakao API 실패 시에도 DB 데이터만으로 정상 응답합니다 (Graceful Degradation):

```python
if self._kakao and site.positn_nm and site.positn_pstn_lat:
    try:
        response = await self._kakao.search_keyword(
            query=site.positn_nm,
            x=site.positn_pstn_lot, y=site.positn_pstn_lat,
            radius=100, size=1, sort="distance",
        )
        if response.places:
            place_url = response.places[0].place_url
            kakao_place_id = response.places[0].id
            if not phone and matched.phone:
                phone = matched.phone
    except Exception:
        logger.warning("Kakao enrichment failed", ...)
```

#### (4) GetNearbyCentersQuery — 주변 센터 조회

기존에 존재하던 핵심 Query입니다. zoom level → radius 변환 정책, 카테고리 분류/필터링, 영업시간 판별 등을 수행합니다.

### 1.5 Presentation 계층: HTTP API

4개의 엔드포인트가 RESTful 패턴으로 설계되어 있습니다:

| Method | Endpoint | 파라미터 | 응답 타입 | 설명 |
|--------|----------|---------|----------|------|
| `GET` | `/locations/centers` | lat, lon, zoom/radius, store_category, pickup_category | `LocationEntry[]` | 주변 센터 목록 |
| `GET` | `/locations/search` | q, radius | `LocationEntry[]` | 키워드 하이브리드 검색 |
| `GET` | `/locations/suggest` | q | `SuggestEntry[]` | 자동완성 (최대 5개) |
| `GET` | `/locations/centers/{id}` | — | `LocationDetail` | 상세 조회 + Kakao 보강 |

파라미터 검증은 FastAPI의 `Query` 어노테이션으로 선언적으로 수행합니다:

```python
lat: float = Query(..., ge=-90, le=90)
lon: float = Query(..., ge=-180, le=180)
radius: int | None = Query(None, ge=100, le=50000)
zoom: int | None = Query(None, ge=1, le=20)
```

카테고리 파라미터는 comma-separated string으로 수신하여 Enum 집합으로 변환합니다:

```python
def _parse_store_category_param(raw: str) -> set[StoreCategory] | None:
    if not raw or raw.lower() == "all":
        return None  # 필터 미적용
    for token in raw.split(","):
        categories.add(StoreCategory(token.strip()))
    return categories
```

### 1.6 인프라 설정 및 시크릿 관리

**Pydantic Settings** (`setup/config.py`):

```python
class Settings(BaseSettings):
    kakao_rest_api_key: str | None = Field(
        None,
        validation_alias=AliasChoices(
            "LOCATION_KAKAO_REST_API_KEY",
            "KAKAO_REST_API_KEY",
        ),
    )
    grpc_port: int = Field(
        50051,
        validation_alias=AliasChoices("LOCATION_GRPC_SERVER_PORT"),
    )
    model_config = SettingsConfigDict(env_prefix="LOCATION_", extra="ignore")
```

`grpc_port`에 명시적 alias를 지정한 이유는 **Kubernetes Service Discovery 환경변수 충돌** 때문입니다. K8s는 Service 이름 기반으로 `{SERVICE_NAME}_PORT=tcp://IP:PORT` 형태의 환경변수를 자동 주입하는데, `location` 서비스의 경우 `LOCATION_GRPC_PORT=tcp://10.108.19.79:50051`이 주입되어 Pydantic의 `int` 파싱이 실패했습니다. `validation_alias`로 명시적 변수명을 지정하여 충돌을 회피합니다.

**ExternalSecret** (`workloads/secrets/external-secrets/dev/location-api-secrets.yaml`):

| 환경변수 | SSM 경로 | 용도 |
|---------|----------|------|
| `LOCATION_DATABASE_URL` | `/sesacthon/dev/data/postgres-password` | PostgreSQL 접속 |
| `LOCATION_KAKAO_REST_API_KEY` | `/sesacthon/dev/api/chat/kakao-rest-api-key` | Kakao API 인증 |

Refresh interval 1시간으로 설정되어 키 로테이션 시에도 파드 재시작 없이 반영됩니다.

---

## 2. Frontend: Map 페이지 기능 구현

### 2.1 API 서비스 레이어

**MapService** (`src/api/services/map/map.service.ts`):

axios 인스턴스를 활용한 HTTP 클라이언트로, 백엔드 4개 엔드포인트에 1:1 매핑됩니다:

```typescript
export class MapService {
  static async getLocations(request: LocationListRequest) { ... }
  static async searchLocations(request: LocationSearchRequest) { ... }
  static async suggestPlaces(query: string) { ... }
  static async getLocationDetail(centerId: number) { ... }
}
```

**타입 정의** (`src/api/services/map/map.type.ts`):

프론트엔드 타입은 백엔드 응답 스키마를 정확히 반영하되, Kakao 통합으로 추가된 필드를 optional로 처리합니다:

```typescript
export type LocationListItemResponse = {
  id: number;
  name: string;
  source: 'keco' | 'zerowaste' | 'kakao' | string;
  // ... 기존 필드
  place_url?: string;           // Kakao 장소 상세 URL
  kakao_place_id?: string;      // Kakao 장소 고유 ID
};
```

**카테고리 상수**는 프론트엔드에서 한글 라벨과 함께 정의됩니다:

```typescript
export const STORE_CATEGORIES: StoreCategory[] = [
  { key: 'refill_zero', label: '제로웨이스트' },
  { key: 'cafe_bakery', label: '카페/베이커리' },
  { key: 'vegan_dining', label: '비건/식당' },
  { key: 'upcycle_recycle', label: '업사이클/재활용' },
  { key: 'book_workshop', label: '도서관/공방' },
  { key: 'market_mart', label: '마트/시장' },
  { key: 'lodging', label: '숙박' },
  { key: 'public_dropbox', label: '무인 수거함' },
  { key: 'general', label: '기타' },
];
```

### 2.2 MapSearchBar — 검색 + 자동완성

사용자가 키워드를 입력하면 **300ms debounce** 후 `/suggest` API를 호출하고, 최대 5개의 자동완성 결과를 드롭다운으로 표시합니다.

**핵심 동작 흐름**:

```
[입력 시작] → 300ms 대기 → /suggest API → 드롭다운 표시
                                              │
                                     [항목 선택] → onSuggestSelect 콜백 → 지도 이동 + 마커
                                              │
                                     [Enter/검색] → onSearch 콜백 → /search API → 결과 표시
```

**UX 고려사항**:

| 설계 | 이유 |
|------|------|
| 300ms debounce | API 호출 빈도 제어. 타이핑 중 불필요한 요청 방지 |
| 외부 클릭 시 닫기 | `mousedown` 이벤트 리스너로 드롭다운 외부 클릭 감지 |
| 로딩 스피너 | 입력 필드 우측에 spinner 표시로 API 응답 대기 시각화 |
| 클리어 버튼 | 검색어 초기화 시 suggestions도 함께 초기화 |
| `safe-area-inset-top` | PWA 환경에서 status bar 영역과 겹침 방지 |

```tsx
<div className='absolute top-[calc(0.75rem+env(safe-area-inset-top))] left-3 right-3 z-40'>
```

### 2.3 MapCard — 장소 카드

장소 목록의 개별 항목을 표시하는 카드 컴포넌트입니다. source 타입에 따라 적절한 아이콘을 표시하고, 수거품목/영업시간/전화번호 등 부가 정보를 조건부 렌더링합니다.

**source별 아이콘 매핑**:

| Source | 아이콘 | 출처 |
|--------|--------|------|
| `keco` | SuperBin 아이콘 | 한국환경공단 수거함 데이터 |
| `zerowaste` | ZeroWaste 아이콘 | 제로웨이스트 매장 데이터 |
| `kakao` | ZeroWaste 아이콘 | Kakao 검색 결과 (DB 미등록) |

**상호작용 패턴**:

| 동작 | 결과 |
|------|------|
| 첫 번째 클릭 | 카드 선택 상태로 전환 (테두리 강조 + 지도 중심 이동) |
| 선택 상태에서 재클릭 | 상세 시트 열기 (`onDetailOpen` 콜백) |
| 길찾기 버튼 클릭 | Kakao Map 네비게이션 URL로 외부 이동 |

Kakao source 장소는 DB에 존재하지 않으므로 상세 시트를 열 수 없도록 가드합니다:

```typescript
const handleClick = (e: React.MouseEvent) => {
  if (isSelected && location.source !== 'kakao') {
    onDetailOpen(location.id);
  } else {
    setSelectedLocationId(location.id);
  }
};
```

### 2.4 MapDetailSheet — 장소 상세 바텀 시트

카드를 더블 클릭하면 하단에서 슬라이드 업되는 상세 정보 시트입니다. 백엔드 `/centers/{id}` 엔드포인트를 호출하여 수거품목, 수거 안내, 소개, 전화번호 등 풍부한 정보를 표시합니다.

**표시 정보**:

| 영역 | 데이터 출처 | 설명 |
|------|-----------|------|
| 이름/주소 | DB | 장소명, 도로명/지번 주소 |
| 수거품목 | DB `pickup_categories` | 배터리, 형광등, 의류 등 chip 표시 |
| 수거 안내 | DB `collection_items` | 자유형식 안내문 |
| 소개 | DB `introduction` | 장소 설명 |
| 전화번호 | DB + Kakao 보강 | DB에 없으면 Kakao 전화번호 사용 |
| place_url | Kakao 보강 | "상세" 버튼으로 카카오맵 상세 페이지 연결 |

**액션 버튼**:

| 버튼 | 동작 | 조건 |
|------|------|------|
| 길찾기 | Kakao Map 네비게이션 (현위치 → 목적지) | 항상 표시 |
| 전화 | `tel:` 스킴으로 전화 앱 실행 | phone 존재 시 |
| 상세 | place_url을 새 탭으로 열기 | Kakao 보강 성공 시 |

### 2.5 StoreCategoryFilter — 카테고리 필터

9개 store_category를 chip 형태의 토글 버튼으로 제공합니다. 사용자가 원하는 장소 유형만 선택하면 해당 카테고리의 결과만 지도에 표시됩니다.

**동작 방식**:

```
[필터 열기] → 임시 상태(tempFilter)에 현재 선택 복사
                │
      [chip 토글] → tempFilter 업데이트 (로컬)
                │
      [초기화] → tempFilter = []
                │
      [결과보기] → 부모 상태 업데이트 → API 재호출 (store_category 파라미터 포함)
```

임시 상태를 활용한 이유는, 사용자가 여러 카테고리를 토글한 뒤 "결과보기"를 눌러야만 실제 API 호출이 발생하도록 하여 **불필요한 네트워크 요청을 최소화**하기 위함입니다.

### 2.6 길찾기 연동 — Geolocation + Kakao Map URL

사용자의 현재 위치를 출발지로 자동 설정하여 Kakao Map 네비게이션 페이지로 이동하는 기능입니다.

**URL 포맷**:

```
출발지 + 목적지: https://map.kakao.com/link/from/현위치,{userLat},{userLon}/to/{placeName},{lat},{lng}
목적지만:       https://map.kakao.com/link/to/{placeName},{lat},{lng}
```

**Geolocation 전략**:

```typescript
navigator.geolocation.getCurrentPosition(
  (pos) => {
    // 성공: 출발지(현위치) + 목적지 URL
    const url = `https://map.kakao.com/link/from/현위치,${pos.coords.latitude},${pos.coords.longitude}/to/${dest}`;
    window.open(url, '_blank');
  },
  () => {
    // 실패 fallback: 목적지만 포함
    window.open(`https://map.kakao.com/link/to/${dest}`, '_blank');
  },
  { maximumAge: 60000, timeout: 3000 },
);
```

| 옵션 | 값 | 이유 |
|------|---|------|
| `maximumAge` | 60초 | 1분 이내 캐시된 위치 재사용 (GPS 재측위 대기 방지) |
| `timeout` | 3초 | 위치 획득 실패 시 빠르게 fallback으로 전환 |

이 방식은 사용자에게 위치 권한 요청 없이 즉시 결과를 제공하되, 권한이 있으면 더 정확한 경로를 보여주는 **Progressive Enhancement** 패턴입니다.

---

## 3. PWA Viewport 대응

### 3.1 문제 상황

PWA standalone 모드(홈 화면에서 실행)에서 하단 공백이 발생했습니다. 원인 분석 결과:

| 원인 | 상세 |
|------|------|
| `#root { max-height: 900px }` | 디바이스 뷰포트가 900px를 초과할 경우 #root 높이가 제한됨 |
| `body { place-items: center }` | #root가 body 중앙에 배치되어 상/하 공백 발생 |
| CSS `@media (display-mode: standalone)` | iOS Safari에서 불안정하게 동작하여 override가 적용 안 됨 |

### 3.2 해결 방안: JS 기반 Standalone 감지

CSS 미디어 쿼리의 iOS 호환성 문제를 우회하기 위해, `index.html`에서 **렌더링 전** JS로 standalone 모드를 감지합니다:

```html
<script>
  if (window.navigator.standalone ||  // iOS Safari
      window.matchMedia('(display-mode: standalone)').matches ||  // Android/Chrome
      window.matchMedia('(display-mode: fullscreen)').matches) {
    document.documentElement.classList.add('pwa-standalone');
  }
</script>
```

| 감지 API | 대상 플랫폼 | 반환값 |
|---------|-----------|--------|
| `navigator.standalone` | iOS Safari | boolean (PWA 여부) |
| `matchMedia('standalone')` | Android Chrome, Desktop | MediaQueryList |
| `matchMedia('fullscreen')` | 일부 Android 브라우저 | MediaQueryList |

감지된 클래스를 기반으로 CSS에서 PWA 전용 스타일을 적용합니다:

```css
/* 데스크톱/브라우저: 기존 제한 유지 */
#root {
  max-width: var(--max-width-app);  /* 480px */
  max-height: 900px;
  margin: 0 auto;
  box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
}

/* PWA standalone: 디바이스 전체 화면 사용 */
html.pwa-standalone body {
  align-items: stretch;
}

html.pwa-standalone #root {
  height: 100dvh;
  max-width: 100%;
  max-height: none;
  min-height: 100dvh;
  box-shadow: none;
}
```

### 3.3 Safe Area 대응

노치/홈 인디케이터가 있는 디바이스에서 콘텐츠 겹침을 방지합니다:

| 컴포넌트 | Safe Area 적용 |
|---------|---------------|
| AppLayout 외부 래퍼 | `mt-[env(safe-area-inset-top)]`, `h-[calc(100%-env(safe-area-inset-top))]` |
| MapSearchBar | `top: calc(0.75rem + env(safe-area-inset-top))` |
| BottomNav | `pb-[env(safe-area-inset-bottom)]` |
| MapDetailSheet | `pb-[calc(1.5rem + env(safe-area-inset-bottom))]` |
| AppLayout Outlet (bottom) | `calc(var(--height-bottom-nav) + env(safe-area-inset-bottom))` |

---

## 4. PR 히스토리

### Backend

| PR # | 제목 | 주요 내용 |
|------|------|----------|
| #506 | `feat: web-search agent + location 리팩토링` | Clean Architecture 전환 (32파일), Kakao Port/Adapter, Query 구현 |
| #507 | `fix(secrets): add Kakao REST API key` | ExternalSecret에 `LOCATION_KAKAO_REST_API_KEY` SSM 경로 추가 |
| #508 | `fix(location): K8s env var collision on grpc_port` | `validation_alias=AliasChoices` 적용으로 Service Discovery 충돌 회피 |

### Frontend

| PR # | 제목 | 주요 내용 |
|------|------|----------|
| #123 | `feat: Map 검색/상세/필터 UI` | MapSearchBar, MapCard, MapDetailSheet, StoreCategoryFilter 구현 |
| #124 | `release: Map 검색/상세/필터 기능` | develop → main 배포 |
| #125 | `feat(map): 길찾기 출발지 자동 설정` | Geolocation + Kakao Map `from/to` URL 스킴 |
| #126 | `release: 길찾기 출발지 자동 설정 + PWA 뷰포트 수정` | 배포 |
| #127 | `fix(map): 검색바 safe-area-inset-top 대응` | PWA status bar 영역 겹침 수정 |
| #129 | `fix(pwa): UI 위로 올라가는 현상 수정` | safe-area-inset-bottom을 개별 컴포넌트로 이동 |
| #131 | `fix(pwa): 하단 공백 제거 + safe-area 대응` | body align-items, #root max-height 조정 |
| #133 | `fix(pwa): JS 기반 standalone 감지` | CSS 미디어 쿼리 → JS 감지 전환으로 iOS 호환성 확보 |

---

## 5. 데이터 흐름 요약

### 5.1 주변 센터 조회

```
사용자 지도 이동/줌 변경
  → Map.tsx: lat, lon, zoom 변경 감지
    → MapService.getLocations({ lat, lon, zoom, store_category })
      → Backend: GetNearbyCentersQuery.execute(SearchRequest)
        → ZoomPolicy: zoom → radius_km 변환
        → SqlaLocationReader: PostGIS earth_distance spatial query
        → CategoryClassifier: source + metadata → store/pickup 분류
        → 필터 적용 후 LocationEntryDTO[] 반환
      → Frontend: MapCard 리스트 렌더링 + 지도 마커 표시
```

### 5.2 키워드 검색 (하이브리드)

```
사용자 검색어 입력 + Enter
  → MapSearchBar: onSearch 콜백
    → MapService.searchLocations({ q: "강남 재활용" })
      → Backend: SearchByKeywordQuery.execute("강남 재활용")
        → Kakao API: 키워드 검색 → 좌표 획득
        → Kakao API: 좌표 기반 재검색 (거리순)
        → DB: find_within_radius(anchor_lat, anchor_lon)
        → 50m 중복 제거 → DB 우선 병합 → 정렬
      → Frontend: 검색 결과로 지도 이동 + 마커 + 카드 목록 갱신
```

### 5.3 자동완성

```
사용자 입력 (1글자 이상)
  → MapSearchBar: 300ms debounce
    → MapService.suggestPlaces("강남")
      → Backend: SuggestPlacesQuery.execute("강남")
        → Kakao API: keyword search (size=5, sort=accuracy)
      → Frontend: 드롭다운에 SuggestEntry[] 표시
        → 항목 선택 시 onSuggestSelect → 지도 이동
```

### 5.4 길찾기

```
사용자 "길찾기" 버튼 클릭
  → MapCard/MapDetailSheet: handleNavigation()
    → navigator.geolocation.getCurrentPosition()
      → 성공: from/현위치,lat,lon/to/장소명,lat,lon
      → 실패: to/장소명,lat,lon (출발지 미포함)
    → window.open(kakaoMapUrl, '_blank')
      → Kakao Map 네비게이션 페이지에서 경로 안내
```

---

## 6. 주요 설계 판단

| 판단 | 선택 | 대안 | 근거 |
|------|------|------|------|
| 검색 전략 | DB + Kakao 하이브리드 | Kakao only | DB에 풍부한 메타데이터(수거품목, 영업시간) 존재 |
| 중복 판별 | 50m Haversine | 이름 비교 | 동일 장소의 이름이 다를 수 있음 (약칭/풀네임) |
| 자동완성 위치 | 서버 사이드 | 클라이언트 사이드 | Kakao API 키 노출 방지 + 결과 품질 보장 |
| Kakao API 실패 시 | Graceful Degradation | 500 에러 | 부분 데이터(DB)만으로도 유의미한 결과 제공 가능 |
| PWA 감지 | JS 기반 클래스 | CSS media query | iOS Safari `display-mode: standalone` 미디어 쿼리 불안정 |
| 길찾기 출발지 | Geolocation fallback | 항상 현위치 | 위치 권한 거부 시에도 목적지 안내 가능 |
| 카테고리 필터 | 임시 상태 → 확정 | 즉시 적용 | 다중 토글 시 불필요한 API 호출 방지 |

---

## 7. 검증

### Backend

```bash
# 주변 센터 조회
curl "http://localhost:8000/api/v1/locations/centers?lat=37.5665&lon=126.9780&zoom=5"

# 키워드 검색
curl "http://localhost:8000/api/v1/locations/search?q=강남역+재활용센터&radius=5000"

# 자동완성
curl "http://localhost:8000/api/v1/locations/suggest?q=강남"

# 상세 조회
curl "http://localhost:8000/api/v1/locations/centers/1"
```

### Frontend

| 시나리오 | 검증 항목 |
|---------|----------|
| 검색바 입력 | 300ms 후 드롭다운 표시, 5개 이하 결과 |
| 자동완성 선택 | 지도 중심 이동 + 마커 표시 |
| 카드 클릭 | 선택 강조 → 재클릭 시 상세 시트 |
| 길찾기 | 카카오맵 새 탭 열림 (출발지 포함 여부 확인) |
| 카테고리 필터 | 토글 후 "결과보기" → 지도 마커 갱신 |
| PWA standalone | 하단 공백 없음, safe-area 정상 적용 |
