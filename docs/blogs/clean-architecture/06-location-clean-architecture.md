# Clean Architecture #12: Location 도메인 마이그레이션

> `domains/location` → `apps/location` Clean Architecture 전환  
> **AI Assistant**: Claude Opus 4.5 (Anthropic)  
> **작업 일자**: 2026-01-05

| 링크 | URL |
|------|-----|
| **GitHub** | [eco2-team/backend](https://github.com/eco2-team/backend/tree/develop) |
| **Service** | [frontend.dev.growbin.app](https://frontend.dev.growbin.app) |

---

## 1. 마이그레이션 배경

### 1.1 기존 구조 (domains/location)

```
domains/location/
├── api/v1/endpoints/
│   ├── location.py          # HTTP 엔드포인트
│   └── metrics.py
├── services/
│   ├── location.py          # ~300줄, 조회 + 변환 + 정책
│   ├── category_classifier.py
│   └── zoom_policy.py
├── repositories/
│   └── normalized_site_repository.py
├── models/
│   └── normalized_site.py
└── clients/
    └── redis_cache.py       # Redis 캐시 의존
```

**문제점**:

| 문제 | 설명 |
|------|------|
| 책임 혼재 | `LocationService`가 조회, 변환, 정책을 모두 담당 |
| 구현체 의존 | Service가 Repository 구현체에 직접 의존 |
| 테스트 어려움 | 인프라 구현체에 직접 의존 → Mock 불가 |

### 1.2 마이그레이션 목표

| 목표 | 방법 |
|------|------|
| 계층 분리 | Domain, Application, Infrastructure, Presentation |
| 의존성 역전 | Port/Adapter 패턴으로 외부 의존성 추상화 |
| 테스트 용이성 | Port 기반 Mock 주입 가능 |

---

## 2. 최종 폴더 구조

```
apps/location/
├── domain/
│   ├── entities/
│   │   └── normalized_site.py    # NormalizedSite 엔티티
│   ├── enums/
│   │   ├── store_category.py     # StoreCategory
│   │   └── pickup_category.py    # PickupCategory
│   └── value_objects/
│       └── coordinates.py        # Coordinates VO
├── application/
│   └── nearby/
│       ├── dto/
│       │   ├── location_entry.py    # LocationEntry DTO
│       │   └── search_request.py    # SearchRequest DTO
│       ├── ports/
│       │   └── location_reader.py   # LocationReader Port
│       ├── services/
│       │   ├── zoom_policy.py           # ZoomPolicyService
│       │   ├── category_classifier.py   # CategoryClassifierService
│       │   └── location_entry_builder.py # LocationEntryBuilder
│       └── queries/
│           └── get_nearby_centers.py    # GetNearbyCentersQuery
├── infrastructure/
│   └── persistence_postgres/
│       ├── models.py                    # ORM 모델
│       └── location_reader_sqla.py      # SqlaLocationReader
├── presentation/
│   └── http/
│       ├── controllers/
│       │   ├── health.py         # 헬스 체크
│       │   └── location.py       # /locations/centers
│       └── schemas/
│           └── location.py       # Pydantic 응답
├── setup/
│   ├── config.py
│   ├── database.py
│   └── dependencies.py           # DI 설정
├── main.py
└── tests/
```

---

## 3. 계층별 설계

### 3.1 Domain Layer

도메인 계층은 **외부 의존성 없이** 순수 비즈니스 객체만 포함합니다.

```python
# domain/entities/normalized_site.py
@dataclass(frozen=True)
class NormalizedSite:
    """정규화된 위치 사이트 엔티티."""
    id: int
    source: str
    source_key: str
    positn_nm: Optional[str] = None
    positn_pstn_lat: Optional[float] = None
    positn_pstn_lot: Optional[float] = None
    # ... 영업시간, 주소 등 20+ 필드
    metadata: dict[str, Any] = field(default_factory=dict)

    def coordinates(self) -> Optional[Coordinates]:
        """좌표 Value Object 반환."""
        if self.positn_pstn_lat is None or self.positn_pstn_lot is None:
            return None
        return Coordinates(
            latitude=self.positn_pstn_lat,
            longitude=self.positn_pstn_lot
        )
```

**설계 판단**:

| 판단 | 근거 |
|------|------|
| `frozen=True` | Entity지만 조회 전용이므로 불변으로 설계 |
| `coordinates()` 메서드 | 좌표 유효성 검증 후 VO 반환 — null 안전성 |
| `metadata` 필드 | 소스별 확장 데이터를 유연하게 저장 |

```python
# domain/value_objects/coordinates.py
@dataclass(frozen=True)
class Coordinates:
    """위도/경도 Value Object."""
    latitude: float
    longitude: float
```

```python
# domain/enums/store_category.py
class StoreCategory(str, Enum):
    REFILL_ZERO = "refill_zero"      # 제로웨이스트샵
    CAFE_BAKERY = "cafe_bakery"
    VEGAN_DINING = "vegan_dining"
    UPCYCLE_RECYCLE = "upcycle_recycle"
    PUBLIC_DROPBOX = "public_dropbox" # 무인 수거함
    GENERAL = "general"
```

### 3.2 Application Layer

Application 계층은 **Use Case를 오케스트레이션**합니다. Port를 통해 Infrastructure에 의존하지 않습니다.

#### 계층 구성 원칙

```
┌─────────────────────────────────────────────────────────┐
│  Application Layer                                       │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐ │
│  │    DTO     │  │  Service   │  │   Query/Command    │ │
│  │ (데이터전달)│◄─│ (순수로직) │◄─│  (오케스트레이션)  │ │
│  └────────────┘  └────────────┘  └─────────┬──────────┘ │
│                                            │             │
│                                            ▼             │
│                                  ┌────────────────────┐ │
│                                  │       Port         │ │
│                                  │   (인터페이스)     │ │
│                                  └────────────────────┘ │
└─────────────────────────────────────────────────────────┘
                                            ▲
                                            │ implements
                              ┌─────────────┴─────────────┐
                              │      Infrastructure       │
                              │        Adapter            │
                              └───────────────────────────┘
```

**구성 요소 역할**:

| 구성 요소 | 역할 | 예시 |
|----------|------|------|
| **DTO** | 계층 간 데이터 전달 | `LocationEntry`, `SearchRequest` |
| **Service** | 순수 비즈니스 로직 | `ZoomPolicyService`, `CategoryClassifierService` |
| **Query** | Use Case 오케스트레이션 | `GetNearbyCentersQuery` |
| **Port** | 외부 시스템 추상화 | `LocationReader` |

#### Port 정의

```python
# application/nearby/ports/location_reader.py
class LocationReader(ABC):
    """위치 데이터를 읽기 위한 Port."""

    @abstractmethod
    async def find_within_radius(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int = 100,
    ) -> Sequence[Tuple[NormalizedSite, float]]:
        """반경 내 위치 사이트와 거리(km)를 반환."""
        raise NotImplementedError

    @abstractmethod
    async def count_sites(self) -> int:
        """총 사이트 수를 반환."""
        raise NotImplementedError
```

#### Service 구현

Service는 **순수 로직**만 담당하며, Port에 의존하지 않습니다.

```python
# application/nearby/services/zoom_policy.py
class ZoomPolicyService:
    """줌 레벨에 따른 검색 반경 및 결과 제한 정책."""

    ZOOM_RADIUS_TABLE = {
        1: 80000,   # 카카오맵 14 (세계) → 80km
        14: 800,    # 카카오맵 1 (거리) → 800m
        # ...
    }

    @staticmethod
    def radius_from_zoom(zoom: int | None) -> int:
        """줌 레벨에 따른 검색 반경 (미터) 반환."""
        if zoom is None:
            return 5000  # 기본값 5km
        normalized = ZoomPolicyService._normalize_zoom(zoom)
        return ZOOM_RADIUS_TABLE.get(normalized, 5000)

    @staticmethod
    def _normalize_zoom(zoom: int) -> int:
        """카카오맵 줌 레벨을 내부 스케일로 변환."""
        # 카카오맵: 1(확대) ~ 14(축소)
        # 내부: 1(축소) ~ 20(확대)
        clamped = max(1, min(zoom, 14))
        ratio = (14 - clamped) / 13
        return int(1 + (19 * ratio) + 0.5)
```

```python
# application/nearby/services/category_classifier.py
class CategoryClassifierService:
    """위치 사이트의 카테고리를 분류하는 서비스."""

    STORE_PATTERNS = [
        StoreCategoryPattern(
            StoreCategory.REFILL_ZERO,
            ("제로웨이스트", "리필", "무포장"),
        ),
        StoreCategoryPattern(
            StoreCategory.CAFE_BAKERY,
            ("카페", "커피", "베이커리"),
        ),
        # ...
    ]

    @staticmethod
    def classify(
        site: NormalizedSite,
        metadata: Mapping[str, Any] | None = None,
    ) -> tuple[StoreCategory, list[PickupCategory]]:
        """사이트 정보를 기반으로 카테고리 분류."""
        store = CategoryClassifierService._classify_store(site, metadata or {})
        pickup = CategoryClassifierService._classify_pickup(metadata or {})
        return store, pickup
```

```python
# application/nearby/services/location_entry_builder.py
class LocationEntryBuilder:
    """NormalizedSite → LocationEntry DTO 변환."""

    WEEKDAY_LABELS = (
        ("mon_sals_hr_expln_cn", "월"),
        ("tues_sals_hr_expln_cn", "화"),
        # ...
    )
    TZ = ZoneInfo("Asia/Seoul")

    @staticmethod
    def build(
        site: NormalizedSite,
        distance_km: float,
        metadata: dict[str, Any],
        store_category: StoreCategory,
        pickup_categories: list[PickupCategory],
    ) -> LocationEntry:
        """도메인 엔티티를 DTO로 변환."""
        name = LocationEntryBuilder._first_non_empty(
            metadata.get("display1"),
            site.positn_nm,
            fallback="Zero Waste Spot",
        )
        operating_hours = LocationEntryBuilder._derive_operating_hours(site)

        return LocationEntry(
            id=site.id,
            name=name,
            source=site.source,
            road_address=site.positn_rdnm_addr,
            latitude=site.positn_pstn_lat,
            longitude=site.positn_pstn_lot,
            distance_km=distance_km,
            distance_text=LocationEntryBuilder._format_distance(distance_km),
            store_category=store_category.value,
            pickup_categories=[c.value for c in pickup_categories],
            is_open=operating_hours.get("is_open"),
            is_holiday=operating_hours.get("is_holiday"),
            start_time=operating_hours.get("start_time"),
            end_time=operating_hours.get("end_time"),
            phone=LocationEntryBuilder._derive_phone(site, metadata),
        )
```

#### Query 구현

Query는 **Port와 Service를 조합**하여 Use Case를 완성합니다.

```python
# application/nearby/queries/get_nearby_centers.py
class GetNearbyCentersQuery:
    """주변 재활용 센터를 조회하는 Query."""

    def __init__(
        self,
        location_reader: LocationReader,           # Port
        zoom_policy_service: ZoomPolicyService,    # Service
        category_classifier_service: CategoryClassifierService,
        location_entry_builder: LocationEntryBuilder,
    ) -> None:
        self._location_reader = location_reader
        self._zoom_policy_service = zoom_policy_service
        self._category_classifier_service = category_classifier_service
        self._location_entry_builder = location_entry_builder

    async def execute(self, request: SearchRequest) -> Sequence[LocationEntry]:
        # 1. 정책 적용: 줌 레벨 → 반경/제한
        effective_radius = request.radius or \
            self._zoom_policy_service.radius_from_zoom(request.zoom)
        limit = self._zoom_policy_service.limit_from_zoom(request.zoom)

        # 2. 데이터 조회: Port를 통해 Infrastructure 접근
        rows = await self._location_reader.find_within_radius(
            latitude=request.latitude,
            longitude=request.longitude,
            radius_km=effective_radius / 1000,
            limit=limit,
        )

        # 3. 변환 및 필터링
        entries: list[LocationEntry] = []
        for site, distance in rows:
            metadata = site.metadata or {}

            # 카테고리 분류
            store_cat, pickup_cats = self._category_classifier_service.classify(
                site, metadata
            )

            # 필터 적용
            if request.store_filter and store_cat not in request.store_filter:
                continue
            if request.pickup_filter:
                if not set(pickup_cats) & request.pickup_filter:
                    continue

            # DTO 변환
            entries.append(
                self._location_entry_builder.build(
                    site=site,
                    distance_km=distance,
                    metadata=metadata,
                    store_category=store_cat,
                    pickup_categories=pickup_cats,
                )
            )

        return entries
```

**Query vs Service 역할 분리**:

| 구분 | Query | Service |
|------|-------|---------|
| 역할 | 오케스트레이션 (흐름 제어) | 순수 비즈니스 로직 |
| 의존성 | Port + Service | 없음 (순수 함수) |
| 테스트 | Port Mock 필요 | Mock 불필요 |
| 변경 빈도 | Use Case 변경 시 | 비즈니스 규칙 변경 시 |

### 3.3 Infrastructure Layer

Infrastructure 계층은 **Port의 구현체(Adapter)**를 제공합니다.

```python
# infrastructure/persistence_postgres/location_reader_sqla.py
class SqlaLocationReader(LocationReader):
    """SQLAlchemy를 사용하여 위치 데이터를 읽는 Adapter."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_within_radius(
        self,
        *,
        latitude: float,
        longitude: float,
        radius_km: float,
        limit: int = 100,
    ) -> Sequence[Tuple[NormalizedSite, float]]:
        try:
            # PostGIS earthdistance 확장 사용
            distance_expr = self._earthdistance_expr(latitude, longitude)
            return await self._execute_query(distance_expr, radius_km, limit)
        except DBAPIError:
            # 확장 미설치 시 Haversine 폴백
            distance_expr = self._haversine_expr(latitude, longitude)
            return await self._execute_query(distance_expr, radius_km, limit)

    @staticmethod
    def _earthdistance_expr(lat: float, lon: float):
        """PostGIS earth_distance 함수 사용."""
        return (
            func.earth_distance(
                func.ll_to_earth(lat, lon),
                func.ll_to_earth(
                    NormalizedLocationSite.positn_pstn_lat,
                    NormalizedLocationSite.positn_pstn_lot,
                ),
            ) / 1000.0
        ).label("distance_km")

    @staticmethod
    def _haversine_expr(lat: float, lon: float):
        """Haversine 공식 (PostGIS 없을 때 폴백)."""
        cosine = func.cos(func.radians(lat)) * func.cos(
            func.radians(NormalizedLocationSite.positn_pstn_lat)
        ) * func.cos(
            func.radians(NormalizedLocationSite.positn_pstn_lot) - func.radians(lon)
        ) + func.sin(func.radians(lat)) * func.sin(
            func.radians(NormalizedLocationSite.positn_pstn_lat)
        )
        clamped = func.least(1.0, func.greatest(-1.0, cosine))
        return (6371.0 * func.acos(clamped)).label("distance_km")

    def _to_domain(self, site: NormalizedLocationSite) -> NormalizedSite:
        """ORM 모델 → 도메인 엔티티 변환."""
        metadata = {}
        if site.source_metadata:
            try:
                metadata = json.loads(site.source_metadata)
            except (TypeError, json.JSONDecodeError):
                pass

        return NormalizedSite(
            id=int(site.positn_sn),
            source=site.source,
            source_key=site.source_pk,
            positn_nm=site.positn_nm,
            positn_pstn_lat=site.positn_pstn_lat,
            positn_pstn_lot=site.positn_pstn_lot,
            # ... 나머지 필드
            metadata=metadata,
        )
```

**Graceful Degradation 패턴**:

```
┌─────────────────────────────────────────────────┐
│  find_within_radius()                           │
│                                                 │
│  try:                                           │
│      PostGIS earth_distance ───────► 빠름, 정확 │
│  except DBAPIError:                             │
│      Haversine fallback ───────────► 느림, 호환 │
└─────────────────────────────────────────────────┘
```

PostGIS 확장 미설치 환경에서도 동작 보장.

### 3.4 Presentation Layer

Presentation 계층은 **HTTP 요청/응답 처리**만 담당합니다.

```python
# presentation/http/controllers/location.py
router = APIRouter(prefix="/locations", tags=["locations"])

@router.get("/centers", response_model=list[LocationEntry])
async def centers(
    query: Annotated[GetNearbyCentersQuery, Depends(get_nearby_centers_query)],
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int | None = Query(None, ge=100, le=50000),
    zoom: int | None = Query(None, ge=1, le=20),
    store_category: str = Query("all"),
    pickup_category: str = Query("all"),
) -> list[LocationEntry]:
    """주변 재활용 센터를 조회합니다."""

    # 1. 파라미터 파싱
    store_filter = _parse_store_category_param(store_category)
    pickup_filter = _parse_pickup_category_param(pickup_category)

    # 2. DTO 생성
    request = SearchRequest(
        latitude=lat,
        longitude=lon,
        radius=radius,
        zoom=zoom,
        store_filter=store_filter,
        pickup_filter=pickup_filter,
    )

    # 3. Query 실행 (DI로 주입됨)
    entries = await query.execute(request)

    # 4. 응답 변환
    return [
        LocationEntry(
            id=e.id,
            name=e.name,
            source=e.source,
            road_address=e.road_address,
            # ... 나머지 필드
        )
        for e in entries
    ]


def _parse_store_category_param(raw: str) -> set[StoreCategory] | None:
    """store_category 쿼리 파라미터 파싱."""
    if not raw or raw.lower() == "all":
        return None
    categories = set()
    for token in raw.split(","):
        value = token.strip()
        try:
            categories.add(StoreCategory(value))
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid store_category '{value}'",
            ) from exc
    return categories or None
```

**Controller 책임**:

| 책임 | 설명 |
|------|------|
| 요청 파싱 | Query Parameter → DTO |
| 유효성 검증 | FastAPI `Query()` 제약 조건 |
| Use Case 호출 | Query 실행 위임 |
| 응답 변환 | DTO → Pydantic Schema |
| 에러 처리 | HTTPException 변환 |

---

## 4. 의존성 주입 (DI)

FastAPI의 `Depends()`를 활용한 DI 컨테이너를 구성했습니다.

```python
# setup/dependencies.py

def get_location_reader(
    session: Annotated[AsyncSession, Depends(get_db_session)]
) -> SqlaLocationReader:
    """LocationReader Port → SqlaLocationReader Adapter."""
    return SqlaLocationReader(session)


def get_zoom_policy_service() -> ZoomPolicyService:
    return ZoomPolicyService()


def get_category_classifier_service() -> CategoryClassifierService:
    return CategoryClassifierService()


def get_location_entry_builder() -> LocationEntryBuilder:
    return LocationEntryBuilder()


def get_nearby_centers_query(
    location_reader: Annotated[SqlaLocationReader, Depends(get_location_reader)],
    zoom_policy: Annotated[ZoomPolicyService, Depends(get_zoom_policy_service)],
    classifier: Annotated[CategoryClassifierService, Depends(get_category_classifier_service)],
    builder: Annotated[LocationEntryBuilder, Depends(get_location_entry_builder)],
) -> GetNearbyCentersQuery:
    """Query에 모든 의존성 주입."""
    return GetNearbyCentersQuery(
        location_reader,
        zoom_policy,
        classifier,
        builder,
    )
```

**DI 흐름**:

```
Controller
    │
    ▼ Depends(get_nearby_centers_query)
┌───────────────────────────────────────┐
│  GetNearbyCentersQuery                │
│    ├── LocationReader (Port)          │
│    │       └── SqlaLocationReader     │◄── Depends(get_location_reader)
│    ├── ZoomPolicyService              │◄── Depends(get_zoom_policy_service)
│    ├── CategoryClassifierService      │◄── Depends(get_category_classifier)
│    └── LocationEntryBuilder           │◄── Depends(get_location_entry_builder)
└───────────────────────────────────────┘
```

---

## 5. 아키텍처 다이어그램

### 전체 계층 구조

```
┌─────────────────────────────────────────────────────────────┐
│                    Presentation Layer                        │
│  ┌────────────────────────────────────────────────────────┐ │
│  │  HTTP Controller                                        │ │
│  │  GET /api/v1/locations/centers                         │ │
│  └────────────────────────┬───────────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────┘
                            │ Depends()
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  GetNearbyCentersQuery (오케스트레이션)               │  │
│  │    ├── ZoomPolicyService (정책)                      │  │
│  │    ├── CategoryClassifierService (분류)              │  │
│  │    ├── LocationEntryBuilder (변환)                   │  │
│  │    └── LocationReader ◄─────────────── Port          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │ implements
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Infrastructure Layer                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SqlaLocationReader (Adapter)                         │  │
│  │    ├── PostGIS earth_distance                        │  │
│  │    └── Haversine fallback                            │  │
│  └──────────────────────────┬───────────────────────────┘  │
└─────────────────────────────┼───────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │   PostgreSQL    │
                    │   + PostGIS     │
                    └─────────────────┘
```

### 의존성 방향

```
        ┌───────────────────────────────────────┐
        │          Domain Layer                 │
        │  NormalizedSite, Coordinates, Enums   │
        └───────────────────▲───────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │        Application Layer              │
        │  Query, Services, DTO, Port           │
        └───────────────────▲───────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │       Infrastructure Layer            │
        │  SqlaLocationReader (implements Port) │
        └───────────────────▲───────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │        Presentation Layer             │
        │  HTTP Controller                      │
        └───────────────────────────────────────┘

        ※ 화살표 방향 = 의존성 방향 (안쪽으로)
```

---

## 6. 테스트 전략

### Mock 기반 단위 테스트

Port를 통해 의존성을 주입받으므로, Mock으로 쉽게 교체 가능합니다.

```python
# tests/test_queries.py
@pytest.mark.asyncio
async def test_execute_filters_by_store_category(
    mock_location_reader: AsyncMock,
    sample_site: NormalizedSite,
) -> None:
    """store_filter 적용 시 해당 카테고리만 반환."""
    # Arrange: Mock 설정
    mock_location_reader.find_within_radius.return_value = [(sample_site, 1.0)]

    query = GetNearbyCentersQuery(
        location_reader=mock_location_reader,  # Mock 주입
        zoom_policy_service=ZoomPolicyService(),
        category_classifier_service=CategoryClassifierService(),
        location_entry_builder=LocationEntryBuilder(),
    )

    # Act: 카페/베이커리만 필터링
    request = SearchRequest(
        latitude=37.5, longitude=127.0,
        store_filter={StoreCategory.CAFE_BAKERY},
    )
    result = await query.execute(request)

    # Assert: sample_site는 REFILL_ZERO이므로 필터링됨
    assert len(result) == 0
```

### Service 단위 테스트

Service는 순수 함수이므로 Mock 없이 테스트합니다.

```python
# tests/test_services.py
class TestZoomPolicyService:
    def test_radius_from_zoom_1(self) -> None:
        """카카오맵 줌 1 (확대) → 반경 800m."""
        assert ZoomPolicyService.radius_from_zoom(1) == 800

    def test_radius_from_zoom_14(self) -> None:
        """카카오맵 줌 14 (축소) → 반경 80km."""
        assert ZoomPolicyService.radius_from_zoom(14) == 80000


class TestCategoryClassifierService:
    def test_classify_refill_zero(self) -> None:
        """'제로웨이스트' 키워드 → REFILL_ZERO."""
        site = NormalizedSite(
            id=1, source="test", source_key="TEST",
            positn_nm="제로웨이스트샵",
        )
        store, _ = CategoryClassifierService.classify(site)
        assert store == StoreCategory.REFILL_ZERO
```

---

## 7. 파일 매핑 테이블

### Legacy → Clean Architecture

| Legacy (`domains/location`) | Clean Architecture (`apps/location`) |
|-----------------------------|-------------------------------------|
| `api/v1/endpoints/location.py` | `presentation/http/controllers/location.py` |
| `services/location.py::LocationService.nearby_centers()` | `application/nearby/queries/get_nearby_centers.py` |
| `services/location.py::LocationService._to_entry()` | `application/nearby/services/location_entry_builder.py` |
| `services/category_classifier.py` | `application/nearby/services/category_classifier.py` |
| `services/zoom_policy.py` | `application/nearby/services/zoom_policy.py` |
| `repositories/normalized_site_repository.py` | `infrastructure/persistence_postgres/location_reader_sqla.py` |
| `models/normalized_site.py` | `infrastructure/persistence_postgres/models.py` |
| `domain/entities.py` | `domain/entities/normalized_site.py` |
| `domain/value_objects.py` | `domain/value_objects/coordinates.py` + `domain/enums/` |
| `schemas/location.py` | `presentation/http/schemas/location.py` |

### Port-Adapter 매핑

| Port | Adapter | 역할 |
|------|---------|------|
| `LocationReader` | `SqlaLocationReader` | 반경 내 위치 조회 |

### SOLID 원칙 적용

| 원칙 | 적용 |
|------|------|
| **SRP** | Query는 오케스트레이션, Service는 순수 로직 |
| **OCP** | 새 Adapter 추가 시 기존 코드 수정 없음 |
| **LSP** | Port 구현체는 동일 계약 준수 |
| **ISP** | `LocationReader`는 읽기 연산만 정의 |
| **DIP** | Application이 Port 정의, Infrastructure가 구현 |

---

## 8. 미구현 사항

현재 마이그레이션에서 의도적으로 제외한 기능:

| 기능 | 레거시 | Clean Architecture | 사유 |
|------|--------|-------------------|------|
| **인증** | `get_current_user` | 미구현 | 공개 API로 운영 결정 |
| **Metrics 엔드포인트** | `/locations/metrics` | 미구현 | 우선순위 낮음 |
| **Redis 캐시** | `RedisCache` | 미구현 | 추후 로컬 캐시로 전환 예정 |

---

## 9. Trade-off

| 장점 | 단점 |
|------|------|
| 테스트 용이 (Mock 주입) | 파일 수 증가 (6개 → 17개) |
| 변경 격리 | 초기 학습 곡선 |
| DB 교체 용이 (Port/Adapter) | 보일러플레이트 코드 |
| 명확한 책임 분리 | 단순 기능도 계층 필요 |

---

## 10. 배포 검증

```bash
# Pod 엔트리포인트 확인
$ kubectl exec -n location location-api-xxx -- cat /proc/1/cmdline
/usr/local/bin/python3.11 uvicorn apps.location.main:app --host 0.0.0.0 --port 8000

# 헬스 체크
$ kubectl exec -n location location-api-xxx -- python3 -c \
    "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
{"status":"healthy","service":"location-api"}

# 디렉토리 구조 확인
$ kubectl exec -n location location-api-xxx -- ls /app/apps/location/
application  domain  infrastructure  main.py  presentation  setup  tests
```

---

## References

### 프로젝트

- [GitHub: eco2-team/backend](https://github.com/eco2-team/backend/tree/develop)
- [Service: frontend.dev.growbin.app](https://frontend.dev.growbin.app)

### 관련 블로그

- [Clean Architecture #11: Character 도메인 마이그레이션](https://rooftopsnow.tistory.com/135)
- [Clean Architecture #7~10: Application/Infrastructure/Presentation Layer 정제](https://rooftopsnow.tistory.com/129)
- [Local Cache Event Broadcast](https://rooftopsnow.tistory.com/69)

### 참고 자료

- [fastapi-clean-example](https://github.com/ivan-borovets/fastapi-clean-example)
- Robert C. Martin, "Clean Architecture" (2017)
