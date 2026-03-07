# Location API 리팩토링 회고

> 2025.12.20

## 목차

1. [배경](#배경)
2. [분석](#분석)
3. [개선 사항](#개선-사항)
4. [실측 데이터](#실측-데이터)
5. [결론](#결론)

---

## 배경

Location API는 재활용 센터와 제로웨이스트 매장 정보를 제공하는 **읽기 전용 서비스**입니다.

### 주요 기능

- 위치 기반 재활용 센터 검색
- 카테고리별 필터링 (store_category, pickup_category)
- 영업시간 정보 제공

### 특징

- 외부 서비스 호출 없음
- DB 쓰기 작업 없음 (SELECT only)
- Race Condition 위험 없음

---

## 분석

### Character API 기준 평가

| 항목 | Location | 비고 |
|------|----------|------|
| Race Condition | ✅ 없음 | 읽기 전용 |
| Dead Code | ⚠️ 있음 | 테스트가 없는 메서드 테스트 |
| 하드코딩 | ✅ 없음 | Settings 사용 |
| 테스트 부족 | ⚠️ 48% | 낮은 커버리지 |
| Circuit Breaker | ➖ 불필요 | 외부 호출 없음 |
| `@staticmethod` 중복 | ⚠️ 있음 | line 224-225 |

### 우선순위 결정

| 순서 | 작업 | 이유 |
|------|------|------|
| P0 | Dead Code 테스트 제거 | 테스트 실패 원인 |
| P1 | 테스트 커버리지 개선 | 코드 품질 |
| P2 | `@staticmethod` 중복 제거 | 코드 정리 |

---

## 개선 사항

### P0: Dead Code 테스트 제거

**문제**: 존재하지 않는 메서드(`geocode`, `reverse_geocode`)를 테스트

```python
# AS-IS: 존재하지 않는 메서드 테스트
def test_geocode_raises_not_implemented(self):
    await service.geocode("서울시 강남구")  # AttributeError
```

**해결**: 해당 테스트 클래스 제거

### P2: `@staticmethod` 중복 제거

```python
# AS-IS
@staticmethod
@staticmethod  # 중복!
def _sanitize_optional_text(...):

# TO-BE
@staticmethod
def _sanitize_optional_text(...):
```

### P1: 테스트 추가

추가된 테스트 케이스:
- `TestNearbyCenters`: 검색 결과 필터링
- `TestMetrics`: 캐시 동작
- `TestDeriveOperatingHours`: 영업시간 파싱
- `TestZoomPolicy`: zoom 레벨 변환
- `TestDerivePhone`: 전화번호 파싱

---

## 실측 데이터

### Radon 복잡도

```
실행: radon cc domains/location/ -a -s -nb

결과:
- B등급 함수: 15개 (헬퍼 메서드)
- C등급 이상: 0개
```

### 테스트 커버리지

```
실행: pytest domains/location/tests/ --cov=domains.location.services

결과:
- location.py: 80%
- category_classifier.py: 86%
- zoom_policy.py: 93%
- 전체: 83%
```

### 테스트 수

| 항목 | 개선 전 | 개선 후 |
|------|---------|---------|
| 테스트 수 | 15개 | 34개 |
| 실패 테스트 | 2개 | 0개 |
| 커버리지 | 48% | 83% |

---

## 결론

### 주요 성과

1. **테스트 정상화**: Dead Code 테스트 제거로 CI 안정화
2. **코드 정리**: `@staticmethod` 중복 제거
3. **커버리지 향상**: 48% → 83%

### 90% 미달성 이유

Location은 **읽기 전용 서비스**로:
- Race Condition 위험 없음
- 외부 서비스 장애 영향 없음
- 버그 발생 시 영향 범위 제한적

따라서 83% 커버리지로 충분하다고 판단.

### 수정된 파일

```
domains/location/
├── services/location.py           # @staticmethod 중복 제거
└── tests/test_location_service.py # 테스트 정리 및 추가
```

---

## Reference

- [PostGIS - Spatial Database](https://postgis.net/)
- [FastAPI Query Parameters](https://fastapi.tiangolo.com/tutorial/query-params/)
