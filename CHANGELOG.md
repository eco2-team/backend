# Changelog

Eco² Backend 프로젝트의 모든 주목할 만한 변경사항을 기록합니다.

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.0.0/)를 따르며,
버전 관리는 [Semantic Versioning](https://semver.org/lang/ko/)을 준수합니다.

---

## [1.1.0-pre] - 2026-01-21

### 🚀 Highlights
> **Chat Agent 전환**: Celery 기반 단순 파이프라인에서 LangGraph 기반 Multi-Agent 아키텍처로 전면 전환.
> 9개 Intent 분류, Function Calling Agents, 이미지 생성, Token Streaming 등 차세대 대화형 AI 시스템 구축.

### Added
- **LangGraph 기반 Multi-Agent 아키텍처**
  - **Intent Classification Node**: 사용자 메시지를 9개 Intent로 분류 (WASTE, CHARACTER, WEATHER, LOCATION, INFO, NEWS, IMAGE_GENERATION, GENERAL, GREETING)
  - **Domain Agent Router**: Intent별 전문 Agent로 라우팅하는 Conditional Edge 구현
  - **Multi-Intent 지원**: 단일 메시지에서 복수 Intent 추출 및 순차 처리
  - **State Management**: ChatState 기반 대화 컨텍스트 관리 (user_location, character_id 등)

- **Function Calling Agents**
  - **Location Agent**: Kakao Local API 연동, 주소 → 좌표 변환 (geocoding)
  - **Weather Agent**: 기상청 API 연동, 위치 기반 날씨 정보 제공
  - **News Agent**: Info API 연동, 환경 뉴스 검색
  - **GPT-5.2 / Gemini 3 네이티브 Function Calling** 적용

- **이미지 생성 파이프라인**
  - **Gemini 기반 이미지 생성**: `gemini-2.0-flash-exp` 모델 활용
  - **gRPC 이미지 업로드**: Images API와 gRPC 통신으로 S3 업로드 후 CDN URL 반환
  - **Character Reference 지원**: 캐릭터 이름 감지 및 이미지 생성 컨텍스트 전달
  - **Token Explosion 방지**: Base64 이미지를 프롬프트에서 제외하는 안전 장치

- **Token Streaming 개선**
  - **stream_mode=messages**: LangGraph 메시지 스트리밍 모드 적용
  - **LangChain LLM 직접 호출**: answer_node에서 토큰 단위 스트리밍
  - **Event Router Unicode 수정**: 한글 토큰 인코딩 문제 해결
  - **Pub/Sub Retry Logic**: 발행 실패 시 재시도 로직 추가

- **PostgreSQL 메시지 영속화**
  - **chat-persistence-consumer**: Redis Streams → PostgreSQL 메시지 저장 Consumer 배포
  - **LangGraph Checkpointer**: PostgreSQL 기반 체크포인트 저장/복구 구현
  - **checkpoint_writes 스키마**: task_path 컬럼 추가

- **분산 트레이싱 확장**
  - **E2E 트레이싱**: Chat API → RabbitMQ → Chat Worker → Event Router → SSE Gateway 전 구간 추적
  - **LangSmith 연동**: LangGraph 실행 트레이스 수집
  - **OpenTelemetry Middleware**: 요청/응답 자동 계측

- **Observability 강화**
  - **25-Node Cluster Grafana 대시보드**: 전체 노드 모니터링 대시보드 추가
  - **Chat Worker Metrics**: Intent 분류, Agent 실행, 토큰 생성 메트릭

### Changed
- **Intent 통합**: WEB_SEARCH → GENERAL로 통합, 네이티브 web_search tool 사용
- **Model-Centric Intent Classification**: with_structured_output 기반 JSON 스키마 분류
- **이미지 생성 전용 모델**: OpenAI → Gemini 전환 (비용 및 품질 최적화)
- **Chat API 스펙 정렬**: Frontend 요구사항에 맞춰 cursor 기반 페이지네이션 적용
- **S3 Upload 비동기화**: boto3 → aioboto3 마이그레이션

### Fixed
- **SSE Pub/Sub Race Condition**: `subscribed_event.set()` 타이밍 수정으로 이벤트 누락 방지
- **Gemini API 호출**: `Part.from_text()` 키워드 인자, async iterator 처리 수정
- **OpenAI Responses API**: image_generation tool 포맷 수정
- **Token Duplication**: answer_node에서 토큰 발행 단일화
- **max_tokens 처리**: None 값 API 호출 제외
- **Multi-Intent JSON 파싱**: Markdown 코드 블록 제거 로직 추가

### Infrastructure
- **chat-worker 노드**: TaskIQ + RabbitMQ 기반 비동기 작업 처리
- **chat-persistence-consumer**: Redis Streams Consumer 전용 배포
- **NetworkPolicy 확장**: chat → images gRPC, event-router namespace egress 허용
- **ConfigMap 분리**: 이미지 생성 프롬프트 파일 외부화

---

## [1.0.9] - 2026-01-18

### 🚀 Highlights
> **Info 서비스 프로비저닝**: 환경 뉴스 수집 및 제공을 위한 Info API/Worker 3-Tier 아키텍처 구축.
> **Claude Code Context 마이그레이션**: Cursor 기반 개발 환경에서 Claude Code Skills로 전환.

### Added
- **Info API 3-Tier Architecture**
  - **Info API**: FastAPI 기반 뉴스 조회 REST API
  - **Info Worker**: Celery Beat 기반 뉴스 수집 스케줄러
  - **PostgreSQL 영속화**: 뉴스 데이터 저장
  - **Redis 캐싱**: 조회 성능 최적화

- **News Service 개발**
  - **NewsData API 연동**: 환경 관련 뉴스 자동 수집
  - **카테고리 분류**: 뉴스 카테고리 list 타입 처리
  - **Cursor 기반 페이지네이션**: 대용량 뉴스 목록 처리

- **Claude Code Skills 도입**
  - **chat-agent-flow Skill**: E2E 테스트 및 트러블슈팅 가이드
  - **프로젝트 특화 가이드**: Redis Streams 아키텍처 문서화

- **RabbitMQ Topology**
  - **info.collect_news 큐**: Celery Beat 작업 큐 CR 추가
  - **Worker 사용자 권한**: eco2 vhost 접근 권한 설정

### Changed
- **개발 환경 전환**: Cursor → Claude Code Context 마이그레이션
- **CORS 설정**: dev frontend origin 추가
- **Database 설정**: eco2 → ecoeco 데이터베이스명 수정

### Fixed
- **Celery Beat 안정화**
  - Standalone beat sidecar 분리 (embedded -B 플래그 문제 해결)
  - emptyDir 볼륨으로 beat schedule 파일 관리
  - /proc 파일시스템 기반 liveness probe
- **asyncpg DSN 호환성**: SQLAlchemy DSN 형식 변환
- **Info Worker 배포**: Secret key 참조, 환경변수 prefix 수정
- **NetworkPolicy**: info namespace RabbitMQ/전체 egress 허용

### Infrastructure
- **info namespace**: API 및 Worker 전용 네임스페이스
- **ArgoCD ApplicationSet**: info API, info-worker 자동 배포
- **ServiceMonitor**: info 서비스 메트릭 수집

---

## [1.0.8] - 2026-01-15

### 🚀 Highlights
> **Clean Architecture 마이그레이션**: 레거시 `domains/` 구조에서 `apps/` 기반 3-tier 아키텍처로 전면 전환.
> 도메인별 독립성 강화 및 CI/CD 파이프라인 정비.

### Added
- **RabbitMQ Named Exchange 기반 이벤트 라우팅**
  - **reward.events Fanout Exchange**: 1:N 이벤트 브로드캐스팅
  - **Cross-Domain Task Routing**: AMQP default exchange 활용
  - **Topology CR 기반 큐 관리**: task_create_missing_queues=False

- **Character Worker 독립화**
  - **Gevent Pool 호환**: 동기 DB 세션 사용
  - **Redis 캐시 Lazy Loading**: 초기화 예외 처리 강화
  - **reward_character_task autodiscover**: 태스크 자동 등록

- **Multi-Model Image Generation**
  - **Provider 인식 이미지 생성**: OpenAI/Gemini 자동 선택
  - **Character Reference 컨텍스트**: 캐릭터 기반 이미지 생성 지원

### Changed
- **디렉토리 구조 전환**: `domains/` → `apps/` 마이그레이션
  - 모든 도메인 서비스 apps/ 하위로 이동
  - `domains/_base` 제거
  - 레거시 `domains/` 디렉토리 삭제
- **CI 파이프라인 수정**
  - `apps/` 경로 기반 트리거
  - chat, chat_worker PR 트리거 추가
- **DB/Redis 연결 정규화**
  - POSTGRES_HOST 통일
  - Redis master pod DNS 직접 참조
- **네이밍 통일**: `image` → `images` 전체 변경

### Fixed
- **Celery 큐 바인딩 문제**
  - Queue에 no_declare=True 추가
  - task_queues 정의로 Topology CR 큐 사용
  - 기본 exchange 사용으로 routing 수정
- **RabbitMQ TTL Mismatch**: 자동 큐 생성 비활성화
- **scan-worker 직렬화 에러**: kombu publish 수정
- **character-worker gevent 호환**: 동기 DB 세션 전환
- **SSE Gateway CORS**: credentials와 함께 특정 origin 설정
- **Redis 연결 재시도**: 이미지 서비스 설정 개선

### Infrastructure
- **users namespace**: dockerhub-secret ExternalSecret 추가
- **images namespace**: NetworkPolicy 전체 파일 업데이트
- **Secrets 정비**: image → images 시크릿 네이밍 통일

---

## [1.0.7] - 2025-12-28

### Added
- **Redis Streams 기반 SSE 아키텍처 전면 개편**
  - **Event Bus Layer 도입**: Redis Streams(내구성) + Pub/Sub(실시간) + State KV(복구) 3-tier 이벤트 아키텍처 구현
  - **Event Router 컴포넌트**: Consumer Group(`XREADGROUP`) 기반 Streams 소비, Pub/Sub Fan-out, State KV 갱신을 담당하는 독립 서비스 신규 개발
  - **SSE Gateway 컴포넌트**: Pub/Sub 구독 기반 실시간 이벤트 전달, State KV 재접속 복구, Streams Catch-up 메커니즘 구현
  - **Redis Pub/Sub 전용 노드**: 실시간 이벤트 Fan-out 전용 Redis 인스턴스(`k8s-redis-pubsub`) 프로비저닝
  - **Event Router 전용 노드**: Event Bus Layer 전용 노드(`k8s-event-router`) 프로비저닝

- **KEDA 이벤트 드리븐 오토스케일링**
  - **scan-worker ScaledObject**: RabbitMQ 큐 길이 기반 스케일링 (vision, answer, rule 큐 모니터링)
  - **event-router ScaledObject**: Redis Streams pending 메시지 기반 스케일링 (Prometheus 연동)
  - **character-match-worker ScaledObject**: RabbitMQ character.match 큐 기반 스케일링

- **Observability 강화**
  - **Event Router Metrics**: 이벤트 처리량, Pub/Sub 발행, State 갱신, Reclaimer 상태 Prometheus 메트릭
  - **SSE Gateway Metrics**: 활성 연결 수, 연결 duration, 이벤트 분배, Pub/Sub 수신 메트릭
  - **scan-sse-pipeline 대시보드**: Grafana 통합 대시보드 (Scan API, Event Router, SSE Gateway, Redis Streams)
  - **ServiceMonitor 추가**: `event-router`, `sse-gateway` Prometheus 메트릭 수집

- **분산 트레이싱 확장**
  - **OpenTelemetry 계측**: Event Router, SSE Gateway에 OTLP/HTTP 트레이싱 적용
  - **Redis 자동 계측**: scan-api, scan-worker에 Redis 작업 트레이싱 추가
  - **OpenAI API 계측**: scan-worker에 OpenAI 호출 트레이싱 추가

- **부하 테스트 및 성능 검증**
  - **k6 테스트 스크립트**: `k6-sse-load-test.js` 50/250/300 VU 부하 테스트
  - **50 VU 완료율**: 35% → 86.3% (KEDA) → **99.7%** (Event Bus)
  - **300 VU 부하 테스트**: 1,365 요청, 67.3% 완료율, 3.1 req/s 처리량

### Changed
- **Worker State 갱신 권한 이전**: scan-worker가 직접 State KV를 갱신하던 로직을 제거, Event Router가 단일 권위로 State 관리
- **SSE Gateway 아키텍처**: StatefulSet + Consistent Hash 기반 → Deployment + Pub/Sub 기반으로 전환
- **CI 파이프라인 분리**: `ci-sse-components.yml` 신규 생성, event-router/sse-gateway 전용 빌드 파이프라인
- **Redis 인스턴스 분리**: Streams(내구성) / Pub/Sub(실시간) / Cache(LRU) 용도별 분리 운영
- **scan-worker KEDA maxReplicas**: 5 → 3 (노드 리소스 제약 반영)

### Fixed
- **SSE 이벤트 누락 문제 해결**: Pub/Sub 구독 타이밍과 State KV 조회 간 Race Condition 수정
- **Event Router 멱등성**: Lua Script 기반 중복 이벤트 필터링 및 순서 보장
- **SSE Gateway Streams Catch-up**: 재접속 시 누락 이벤트 Redis Streams에서 복구
- **KEDA ScaledObject 트리거**: Prometheus 쿼리 메트릭명 수정 (`redis_stream_group_messages_pending`)
- **ServiceMonitor namespace 설정**: `prometheus` 네임스페이스에서 메트릭 수집하도록 변경

### Infrastructure
- **신규 노드 프로비저닝**
  - `k8s-event-router` (t3.small): Event Bus Layer 전용
  - `k8s-redis-pubsub` (t3.medium): Redis Pub/Sub 전용
- **Redis Operator 확장**: `pubsub-redis` RedisFailover CR 추가 (3 masters, 3 sentinels)
- **NetworkPolicy 확장**: KEDA → Prometheus egress 허용

### Performance
| VU | 아키텍처 | 완료율 | 처리량 | 비고 |
|----|----------|--------|--------|------|
| 50 | Celery Events | 실패 | - | 503 에러 폭증 |
| 50 | Redis Streams | 35% | - | 초기 마이그레이션 |
| 50 | KEDA 스케일링 | 86.3% | - | Worker 자동 확장 |
| 50 | Event Bus | **99.7%** | 3.3 req/s | 현재 아키텍처 |
| 250 | Event Bus | 83.3% | 3.4 req/s | 3 Worker 제한 |
| 300 | Event Bus | 67.3% | 3.1 req/s | Worker 병목 |

---

## [1.0.6] - 2025-12-11

### Added
- **Observability Stack 전면 강화**
  - **Kiali & Jaeger 도입:** Service Mesh 토폴로지 시각화(Kiali) 및 분산 트레이싱(Jaeger) 구축 (`istio-system` 네임스페이스)
  - **OpenTelemetry Auto-Instrumentation:** 모든 백엔드 서비스(FastAPI)에 OpenTelemetry 적용하여 DB, Redis, 외부 API 호출까지 자동 추적
  - **Service Topology Visualization:** 외부 의존성(Google/Kakao OAuth, OpenAI, AWS S3/CloudFront)을 Istio `ServiceEntry`로 정의하여 Kiali 그래프에 명확히 시각화
  - **Trace Sampling 전략:** 개발 환경(`dev`)의 모든 트레이스를 수집하도록 Global Sampling 100% 설정

### Changed
- **Network Policy 강화**
  - Observability 도구(Kiali, Jaeger, Prometheus) 간의 통신 및 수집을 허용하는 `allow-observability` 정책 추가
- **DNS 및 라우팅**
  - `kiali.dev.growbin.app`, `jaeger.dev.growbin.app` 도메인 및 ExternalDNS 등록
- **Deployment 메타데이터 표준화**
  - 모든 워크로드에 `version` 라벨을 추가하여 Kiali 그래프의 가독성 향상

## [1.0.5] - 2025-12-11

### Added
- **Istio Service Mesh 전면 도입**
  - **Ingress Gateway Migration:** 기존 ALB + K8s Ingress 구조에서 Istio Gateway + VirtualService 구조로 전환하여 L7 라우팅 및 보안 제어 강화
  - **Auth Offloading:** 애플리케이션 레벨의 JWT 검증 로직을 제거하고, Istio `RequestAuthentication`과 `EnvoyFilter`로 위임하여 인증 구조 단순화
  - **External Authorization (gRPC):** Istio의 `CUSTOM` Authorization 정책을 적용하여, `auth-api` gRPC 서버(Port 9001)를 통해 블랙리스트 및 만료 여부를 중앙 집중적으로 검사
- **Observability Offloading**
  - 애플리케이션 내부의 HTTP 메트릭 수집 미들웨어를 제거하고, Envoy Sidecar가 수집하는 표준 메트릭으로 전환하여 성능 부하 감소

### Changed
- **JWT 보안 알고리즘 강화**
  - 서명 알고리즘을 `HS256` (대칭키)에서 `RS256` (비대칭키)으로 전환하고, `auth-api`에 JWKS (`/.well-known/jwks.json`) 엔드포인트 구현
- **Secret 관리 최적화**
  - `auth-api` 외 타 도메인 서비스들의 환경 변수 및 External Secret에서 불필요한 `JWT_SECRET_KEY` 제거
- **인프라 프로비저닝 자동화**
  - Istio Ingress Gateway를 위한 전용 노드(`k8s-ingress-gateway`, t3.medium)를 Terraform으로 프로비저닝하고, Ansible로 자동 조인 및 Taint 적용

### Fixed
- **사용자 정보 조회 오류 수정** (`user/me`)
  - 다중 소셜 계정 연동 시 특정 상황에서 잘못된 Provider 정보를 반환하던 문제를 해결 (`last_login_at` 기준 최신 계정 우선 선택 로직 적용)
- **배포 및 네트워크 안정성 확보**
  - `my` 서비스의 DB 연결 오류(`ConnectionRefused`) 및 라우팅 경로(`404`) 문제 해결
  - `image` 서비스의 불필요한 Secret 참조로 인한 배포 실패 수정
  - `NetworkPolicy` 적용으로 인한 타 Namespace 서비스(DB, DNS) 접근 차단 문제 해결 (`Egress` 정책 확장)
  - ArgoCD와 Istio 간의 리소스 상태 불일치(Sync Drift) 문제 해결 (`ignoreDifferences` 적용)

---

## [1.0.0] - 2025-12-02

### Added
- **API 연동 완료**
  - Auth, Scan, Chat, Character, Frontend 간 REST 호출 경로를 표준화하고 서비스 간 토큰 규약을 확정
  - Frontend 배포 파이프라인이 develop → main 릴리스 플로우에 자동 연계되도록 GitHub Actions 조정
- **풀 파이프라인 Chat/Scan 대응**
  - Chat 이미지 메시지가 Scan과 동일한 Vision → Lite RAG → Answer 파이프라인을 실행하도록 통합
  - 텍스트-only 요청도 Waste 텍스트 분류 → 규정 매칭 → 답변 생성 플로우를 그대로 사용

### Changed
- **파이프라인 성능 향상**
  - Vision/텍스트 파이프라인을 `asyncio.to_thread`로 감싸 FastAPI 이벤트 루프 블로킹 제거
  - Prompt 포맷과 Lite RAG 캐시 경로 정리로 평균 응답 시간 18% 단축
- **릴리스 전략**
  - main 브랜치에 README만 유지하고 나머지는 develop 내용을 그대로 반영하도록 배포 규칙 명문화
  - Git Tag `v1.0.0` 생성 후 frontend 정적 자산을 즉시 배포

### Fixed
- Chat 이미지 요청 실패 시 사용자 안내 문구를 개선해 재시도 유도
- Presigned URL 업로드 시 Content-Type 서명 검증 로깅 보강

---

## [0.9.0] - 2025-11-30

### Added
- **도메인 API 1차 완성**
  - Scan API: `/api/v1/scan/classify`, `/task/{id}`, `/categories` 구현으로 Vision→RAG→Answer 파이프라인을 서비스화
  - Character API: `/api/v1/character/catalog` 및 내부 보상/온보딩 엔드포인트 정비
  - My 서비스에서 Character 소유권을 직접 조회할 수 있도록 Repository 계층 연동
- **이미지/AI 워크플로우 통합**
  - `_shared/waste_pipeline` 모듈을 각 도메인에서 공통으로 사용
  - 서비스 간 presigned URL, CDN 정규화 전략 정립

### Changed
- **Auth 세션 정책 조정**
  - Access Token 3일, Refresh Token 6일로 연장해 사용자 경험 개선
  - App-of-Apps 기반 GitOps로 dev/prod에 자동 반영
- **Document/Release 프로세스 개선**
  - develop 전체를 main에 동기화하여 API 개발 결과물을 릴리스
  - README는 main 버전을 유지해 배포 안내 일관성 확보

### Security
- **서비스 간 토큰 검증**
  - Character 내부 엔드포인트(`/api/v1/internal/characters/**`)에 `Authorization: Bearer <CHARACTER_SERVICE_TOKEN_SECRET>` 검증 추가
  - Scan ↔ Character 간 공유 토큰을 SSM Parameter + ExternalSecret으로 관리

---

## [0.8.0] - 2025-11-24

### Added
- **API 연동 준비**
  - Character ↔ Scan 보상 인터페이스 초안 및 `CharacterRewardRequest/Response` 스키마 정비
  - Chat 서비스에 `_shared/waste_pipeline`을 도입해 향후 Vision 파이프라인 통합 기반 마련
- **Frontend 배포 파이프라인 초석**
  - GitHub Actions에 frontend 빌드/배포 Job을 추가하고 환경별 Artefact 저장소 지정

### Changed
- develop 브랜치를 main에 릴리스할 때 README는 main 버전을 유지하고 나머지 파일은 develop을 덮어쓰도록 문서화
- Waste 파이프라인 Prompt를 Markdown 기반으로 정리해 diff/리뷰 편의성 향상

### Fixed
- Character Catalog CSV 필드 검증 로직을 강화해 누락된 match 값이 DB로 저장되지 않도록 방지

---

## [0.7.5] - 2025-11-19

### Fixed
- **ArgoCD Deployment CrashLoopBackOff 문제 해결**
  - Ansible의 Deployment 직접 패치 방식이 command/args 충돌 유발
  - ConfigMap(`argocd-cmd-params-cm`) 기반 설정으로 전환
  - `server.insecure=true` 표준 방식 적용
  - `docs/troubleshooting/ARGOCD_DEPLOYMENT_ISSUES.md` 추가

- **ArgoCD ERR_TOO_MANY_REDIRECTS 문제 해결**
  - ALB HTTPS 종료 환경에서 무한 리디렉션 루프 발생
  - insecure 모드 적용으로 HTTP 트래픽 정상 처리
  - Ingress `backend-protocol: HTTP` annotation 문서화

### Changed
- **Ansible ArgoCD Role 전면 개선** (`ansible/roles/argocd/tasks/main.yml`)
  - Deployment 직접 패치 제거 (비표준 방식)
  - ConfigMap 생성/패치/검증 단계 추가
  - 멱등성 보장 및 에러 핸들링 강화
  - 재시작 프로세스 명시화 (rollout restart + rollout status)

### Added
- ArgoCD insecure 모드 설정 검증 단계
- ConfigMap 존재 여부 확인 및 자동 생성 로직
- 트러블슈팅 가이드 참조 (`LOCAL_CLUSTER_BOOTSTRAP.md`)

---

## [0.7.4] - 2025-11-18

### Added
- **Security Group 아키텍처 단순화**
  - Master/Worker SG 분리 구조를 단일 Cluster SG로 통합
  - 순환 참조 완전 제거 (312줄 → 155줄, 50% 감소)
  - 계층별 책임 분리 (SG: 노드 레벨, NetworkPolicy: Pod 레벨)
  - `docs/architecture/SECURITY_GROUP_SIMPLIFICATION.md` 추가

- **Helm/Kustomize 구조 재확립**
  - Platform 계층: Helm Chart 중심 (`platform/helm/`)
  - Workload 계층: Kustomize base/overlay 패턴 (`workloads/`)
  - CRDs 독립 관리: `platform/crds/` 분리
  - 환경별 patch 방식 통일 (JSON → YAML)
  - `docs/gitops/ARGOCD_HELM_KUSTOMIZE_STRUCTURE.md` 최종 확립

### Changed
- Terraform Security Group 모듈 전면 개편
  - `aws_security_group.k8s_cluster` 통합 생성
  - 14개 노드 모두 `cluster_sg_id` 사용
  - SSM Parameter: `cluster-sg-id` 신규 생성

### Fixed
- `terraform destroy` 시 Security Group DependencyViolation 에러 해결
- SG 삭제 15분+ 대기 문제 완전 제거
- Calico CNI 배포 전략 확립
  - Operator 방식 시도 실패 (Ansible Operator + ArgoCD Operator 충돌)
  - Helm Chart 단일 방식으로 통일 (Ansible에서 1회 설치)
  - VXLAN Always + BGP Disabled 설정 고정
  - `docs/troubleshooting/calico-operator-helm-conflict.md` 추가
- Calico Typha 포트 5473 통신 문제 해결
  - Master ↔ Worker Typha 통신 Security Group 규칙 추가
  - Cluster 내부 통신 self 규칙으로 완전 보장
  - `docs/troubleshooting/CALICO_TYPHA_PORT_5473_ISSUE.md` 추가

### Deprecated
- `master_sg_id`, `worker_sg_id` outputs (하위 호환성 유지, `cluster_sg_id` 사용 권장)

---

## [0.7.3] - 2025-11-17

### Added
- **GitOps Architecture 2.0**
  - ArgoCD App-of-Apps 패턴 전면 도입
  - Sync Wave 기반 계층적 배포 (Wave 0~70)
  - Helm + Kustomize 통합 관리

- **Atlantis 통합**
  - PR 기반 Terraform plan/apply 자동화
  - SSH Unification (단일 키 관리)
  - Terraform 워크플로우 표준화

- **문서 체계 재정립**
  - `docs/architecture/` 구조 개편
  - `docs/gitops/` GitOps 전용 문서
  - `docs/deployment/` 배포 가이드 통합

### Changed
- Ansible 역할 최소화 (부트스트랩 전용)
  - kubeadm init/join
  - Calico CNI (VXLAN)
  - ArgoCD Core 설치
  - 이후 모든 리소스는 ArgoCD 관리

- Namespace 전략 정비
  - 13개 Namespace (tier, domain 레이블)
  - NetworkPolicy 기반 격리
  - RBAC 최소 권한 원칙

### Fixed
- ArgoCD ApplicationSet 패턴 안정화
- ExternalSecrets SSM Parameter 주입 최적화

---

## [0.7.2] - 2025-11-14

### Added
- **도메인별 Ingress 분리**
  - API, ArgoCD, Grafana 독립 Ingress
  - Path 기반 라우팅 최적화
  - ACM Certificate 통합 관리

- **Namespace 전략 문서화**
  - `NAMESPACE_STRATEGY_ANALYSIS.md`
  - Tier 기반 격리 정책
  - 도메인 경계 명확화

### Changed
- Terraform S3 Backend 활성화
  - State 원격 저장
  - 협업 환경 개선
  - State Lock 적용

### Fixed
- Helm template name 생성 오류
- Environment variable optional 처리

---

## [0.7.1] - 2025-11-12

### Added
- **Kustomize 전면 도입**
  - base/overlay 패턴 적용
  - 환경별 설정 분리 (dev/staging/prod)
  - ConfigMap/Secret 관리 개선

- **문서 업데이트**
  - `KUSTOMIZE_BASE_OVERLAY_GUIDE.md`
  - README v0.7.1 반영

### Changed
- ArgoCD Application 구조 Kustomize 기반으로 전환
- Helm Values를 Kustomize patch로 관리

---

## [0.7.0] - 2025-11-08

### Added
- **14-Node 아키텍처 완성**
  - Master: 1 (Control Plane + Monitoring)
  - API Nodes: 7 (auth, my, scan, character, location, info, chat)
  - Worker Nodes: 2 (storage, ai)
  - Infrastructure: 4 (postgresql, redis, rabbitmq, monitoring)

- **Phase별 배포 전략**
  - Phase 1: MVP (auth, my, postgresql, redis)
  - Phase 2: Core (scan, character, location)
  - Phase 3: Extended (info, chat)
  - Phase 4: Workers + RabbitMQ + Monitoring

- **모니터링 스택 강화**
  - Prometheus + Grafana 독립 노드
  - 14-Node 최적화 설정
  - ServiceMonitor CRD 활용

### Changed
- Terraform 14-Node 전용 구성
- Ansible 14-Node 지원
- Helm Charts 14-Node 템플릿

### Fixed
- Node labeling 일관성 확보
- Provider ID 자동 설정 (ALB Controller)

---

## [0.6.0] - 2025-11-05

### Added
- **13-Node 아키텍처**
  - 8GB t3.large Master (Control Plane 전용)
  - 도메인별 전용 노드 (auth, my, scan)
  - RabbitMQ 독립 노드

- **WAL (Write-Ahead Logging)**
  - Celery Worker Storage/AI 분리
  - Eventlet Pool (I/O Bound)
  - Prefork Pool (Network Bound)

- **Eco² 브랜딩**
  - 프로젝트명 확정
  - 비전 및 목표 정립

### Changed
- PostgreSQL 메모리 최적화 (4GB → 도메인별 DB)
- Redis 독립 노드화
- 리소스 비용 최적화 ($253 → $245/월)

---

## [0.5.0] - 2025-11-02

### Added
- **13-Node 기준 문서화**
  - 아키텍처 다이어그램
  - 리소스 배분 전략
  - 노드별 역할 정의

- **FastAPI Health Check**
  - `/health` 엔드포인트
  - Liveness/Readiness Probe
  - Kubernetes 통합

### Changed
- Helm Charts 13-Node 템플릿
- ArgoCD 도메인별 Application
- Ansible 13-Node 지원

---

## [0.4.4] - 2025-10-31

### Added
- **분석 및 계획 문서 재구성**
  - Design Reviews 컬렉션
  - Self-Managed K8s 최종 결정
  - EKS vs Self-Managed 비용 분석

### Changed
- 문서 디렉토리 구조 개편
- `docs/archive/design-reviews/` 아카이브

---

## [0.4.2] - 2025-10-29

### Added
- **Troubleshooting 통합**
  - `docs/troubleshooting/TROUBLESHOOTING.md`
  - Rapid Diagnostics Runbook
  - 실측 사례 기반 가이드

### Changed
- 구식 문서 정리
- 중복 문서 아카이브

### Fixed
- PV cleanup for Released/Failed volumes
- VPC 삭제 지연 문제

---

## [0.4.0] - 2025-10-25

### Added
- **Self-Managed Kubernetes 기반 확립**
  - kubeadm 클러스터 구성
  - Terraform + Ansible IaC
  - Calico CNI (VXLAN)

- **마이크로서비스 아키텍처**
  - 7개 도메인 서비스 분리
  - PostgreSQL 도메인별 DB
  - Redis JWT Blacklist

### Changed
- Self-Managed K8s로 확정
- 비용 최적화 ($253 → $180/월)

---

## [0.3.0] - 2025-10-20

### Added
- **GitOps 기반 구축**
  - ArgoCD 도입
  - GitHub Actions CI/CD
  - GHCR 이미지 레지스트리

- **인프라 자동화**
  - Terraform AWS 프로비저닝
  - Ansible 클러스터 설정
  - Infrastructure as Code

### Changed
- Docker Compose에서 Kubernetes로 전환

---

## [0.2.0] - 2025-10-15

### Added
- **초기 서비스 개발**
  - Auth API (JWT 인증)
  - My Page API
  - Scan API (AI 폐기물 분류)

- **데이터 계층**
  - PostgreSQL 멀티 스키마
  - Redis 캐시
  - RabbitMQ 메시지 큐

### Changed
- FastAPI 프레임워크 표준화
- Pydantic V2 마이그레이션

---

## [0.1.0] - 2025-10-10

### Added
- **프로젝트 초기화**
  - Repository 생성
  - 기본 디렉토리 구조
  - README 작성

- **개발 환경 설정**
  - Poetry 의존성 관리
  - Pre-commit hooks
  - Ruff linter

### Changed
- Python 3.11 기준 설정

---

## 버전 관리 정책

### 버전 번호 체계 (MAJOR.MINOR.PATCH)

- **MAJOR**: 호환성이 깨지는 대규모 변경
  - 아키텍처 전면 개편
  - API 하위 호환성 제거

- **MINOR**: 하위 호환 기능 추가
  - 새로운 서비스/기능 추가
  - 인프라 확장
  - 주요 문서 업데이트

- **PATCH**: 하위 호환 버그 수정
  - 설정 최적화
  - 문서 오류 수정
  - 경미한 리팩토링

### 브랜치 전략

- `main`: 프로덕션 안정 버전
- `develop`: 개발 통합 브랜치
- `feature/*`: 기능 개발
- `refactor/*`: 리팩토링
- `hotfix/*`: 긴급 수정

### 릴리스 프로세스

1. `develop` 브랜치에서 기능 개발
2. PR 리뷰 및 테스트
3. `main` 브랜치 머지
4. Git Tag 생성 (v0.x.x)
5. CHANGELOG.md 업데이트
6. GitHub Release 발행

---

**문서 버전**: 1.1.0-pre
**최종 업데이트**: 2026-01-21
**관리자**: Backend Platform Team
