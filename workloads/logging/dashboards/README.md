# Kibana Dashboards

Kibana Saved Objects를 NDJSON 형식으로 관리합니다.

## 대시보드 목록

### 1. SRE/운영 대시보드 (`sre-operations.ndjson`)

운영팀을 위한 서비스 상태 모니터링 대시보드입니다.

**포함 패널:**
- Error Rate by Service (서비스별 에러 발생률 추이)
- Log Volume by Level (로그 레벨별 분포)
- Service Health (서비스별 로그 볼륨)
- Top Errors (최근 에러 목록)

**기본 시간 범위:** 24시간

### 2. 개발자 대시보드 (`developer-debug.ndjson`)

개발자를 위한 디버깅 대시보드입니다.

**포함 패널:**
- Errors by Type (에러 타입별 분포)
- Recent Errors (최근 에러 상세)
- Trace ID Search (분산 추적 검색)
- Debug Log Stream (DEBUG 레벨 로그 스트림)

**기본 시간 범위:** 6시간

### 3. 비즈니스 대시보드 (`business-metrics.ndjson`)

비즈니스 메트릭을 추적하는 대시보드입니다.

**포함 패널:**
- Daily Active Logins (일별 로그인 수, 프로바이더별)
- Character Rewards Granted (캐릭터 보상 카운터)
- Location Searches (위치 검색 카운터)
- Feature Usage (채팅/이미지 업로드 사용량)

**기본 시간 범위:** 7일

## 사용법

### Import

```bash
# Kibana API로 import
curl -X POST "https://kibana.example.com/api/saved_objects/_import" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: multipart/form-data" \
  --form file=@sre-operations.ndjson
```

### Export (업데이트 시)

```bash
# Kibana에서 수정 후 export
curl -X POST "https://kibana.example.com/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type": ["dashboard", "visualization", "search", "index-pattern"]}' \
  > updated-dashboard.ndjson
```

## 의존성

모든 대시보드는 `logs-app-*` Data View(Index Pattern)를 사용합니다.
이 Data View는 각 NDJSON 파일에 포함되어 있습니다.

## 필드 참조

대시보드에서 사용하는 주요 필드:

| 필드 | 타입 | 설명 |
|------|------|------|
| `@timestamp` | date | 로그 발생 시간 |
| `log.level` | keyword | INFO, WARNING, ERROR 등 |
| `service.name` | keyword | 서비스 이름 (auth-api 등) |
| `message` | text | 로그 메시지 |
| `trace.id` | keyword | 분산 추적 ID |
| `labels.*` | object | 추가 메타데이터 |
