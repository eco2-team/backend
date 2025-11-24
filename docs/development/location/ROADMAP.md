# Location 서비스 향후 계획 - Kakao Map REST API

현재 Location 도메인은 내부 DB에 저장된 제로웨이스트/리필샵 좌표를 기반으로 반경 검색 API만 제공합니다.  
카카오 로컬 API는 **향후 기능 확장** 시점에서 다음 영역을 강화하기 위해 도입할 예정입니다.

## 1. REST API 연동 범위 (계획)

| 기능 | Kakao API | 목적 |
| --- | --- | --- |
| 좌표 → 행정동 코드 | `GET /v2/local/geo/coord2regioncode` | 지도를 이동할 때 현재 중심의 행정동 라벨을 실시간 표시, 백엔드 로그/검색 조건에 안정적인 동 코드를 남김 |
| 좌표 → 도로명/지번주소 | `GET /v2/local/geo/coord2address` | 선택한 지점을 주소 문자열로 보여주고, 사용자가 “이 위치로 검색”을 누를 때 주소/좌표를 함께 전달 |
| (옵션) 좌표계 변환 | `output_coord=TM/WTM/KATEC` | KAKAO 지도 좌표와 Location DB(TMS) 간 변환을 일관되게 처리 |
| (옵션) 키워드/카테고리 검색 | `GET /v2/local/search/*` | 우리 DB에 아직 없는 지역을 Kakao 데이터로 보강하거나, 사용자 요청이 많은 지역을 선별하는 지표로 활용 |

## 2. 구현 전략

1. **환경 변수**  
   - `LOCATION_KAKAO_REST_API_KEY` 환경 변수를 도입하고, 초기에는 Auth 서비스에서 이미 사용 중인 REST 키를 재활용.  
   - prod/dev 모두 External Secret에 동일 키를 주입한다.

2. **클라이언트 모듈**  
   - `domains/location/clients/kakao.py` 형태로 httpx 기반 REST 클라이언트를 두고, FastAPI Service 계층에서 의존성 주입한다.

3. **API 추가**  
   - `/api/v1/locations/region`, `/address` 등의 엔드포인트를 추가하여 프런트가 지도 중심 좌표를 보낼 때 행정동·주소를 즉시 받을 수 있도록 한다.

4. **프런트 연동**  
   - Kakao JS SDK로 지도/좌표만 처리하고, REST API 호출은 백엔드에 위임하여 REST 키를 외부에 노출하지 않는다.

5. **모니터링 & 쿼터 관리**  
   - 일 100K 기본 쿼터를 초과할 수 있으므로 CloudWatch Metric 혹은 별도 로그로 호출량을 집계한다.  
   - 필요 시 Kakao 콘솔에서 별도 앱을 생성하거나 유상 플랜을 검토한다.

## 3. 현재 상태

- 코드 레벨에서는 Kakao 연동 모듈을 제외한 **기본 반경 검색 기능만 유지**합니다.
- 위 표의 항목은 추후 Location 서비스가 안정화된 후 단계적으로 도입합니다.

