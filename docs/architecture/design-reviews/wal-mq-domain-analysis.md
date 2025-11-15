# WAL + MQ 적용 도메인 분석

## 🎯 평가 기준

WAL + MQ 이중 영속화가 적합한 조건:

```yaml
✅ 필수 조건:
  1. 비동기 처리 가능 (즉시 응답 불필요)
  2. 시간이 오래 걸림 (> 1초)
  3. 외부 서비스 의존 (API, AI, S3 등)
  4. 데이터 손실 불가
  5. 재시도 필요

✅ 선택 조건:
  6. 순서 보장 중요
  7. 높은 트래픽
  8. I/O 집약적
```

---

## 📊 도메인별 분석

### 1. auth (인증/인가)

```yaml
특징:
  - JWT 발급/검증
  - 로그인/로그아웃
  - OAuth2 소셜 로그인
  
처리 시간:
  - JWT 발급: 10-50ms
  - 로그인: 50-200ms
  
비동기 가능:
  ❌ 실시간 동기 응답 필수
  
평가: ❌ 부적합
이유:
  - 빠른 응답 필수 (< 100ms)
  - 사용자 대기 불가
  - Redis BlackList로 충분
```

### 2. my (마이페이지/사용자정보)

```yaml
특징:
  - 프로필 조회
  - 활동 내역
  - 캐릭터 상태
  
처리 시간:
  - 조회: 10-50ms
  - 업데이트: 50-100ms
  
비동기 가능:
  ⚠️ 일부 업데이트만 가능 (프로필 이미지 등)
  
평가: △ 선택적 적용
적용 가능:
  - 프로필 이미지 업로드
  - 배경 이미지 업로드
  
권장:
  - 조회: 동기
  - 이미지 업로드: 비동기 (WAL + MQ)
```

### 3. scan (폐기물 스캔/분석) ⭐⭐⭐

```yaml
특징:
  - 이미지 업로드 (5-20MB)
  - AI 이미지 분석
  - 폐기물 분류
  - 처리 방법 제안
  
처리 시간:
  - 이미지 업로드 S3: 2-5초
  - AI 분석: 5-30초
  - 총: 10-35초 ⚠️
  
비동기 필수:
  ✅ 사용자는 업로드만 하고 대기
  ✅ 백그라운드 처리
  ✅ 푸시 알림으로 결과 전달
  
평가: ✅✅✅ 최적 (최우선)

작업 흐름:
  1. 사용자: 이미지 업로드
     → API: RabbitMQ에 태스크 추가
     → 즉시 응답: task_id 반환 (< 100ms)
  
  2. Worker-Storage (백그라운드):
     → SQLite WAL에 기록
     → S3 업로드 (2-5초)
     → RabbitMQ에 AI 분석 요청
  
  3. Worker-AI (백그라운드):
     → SQLite WAL에 기록
     → AI 모델 호출 (5-30초)
     → PostgreSQL에 결과 저장
     → 푸시 알림 발송
  
  4. 사용자: 푸시 알림 수신
     → 결과 조회

장점:
  ✅ 사용자 대기 시간 최소화
  ✅ 이미지 손실 방지 (WAL + MQ)
  ✅ 재시도 가능 (AI 실패 시)
  ✅ 순서 보장 (FIFO)
```

### 4. character (캐릭터/미션)

```yaml
특징:
  - 캐릭터 육성
  - 미션 완료
  - 리워드 지급
  - 레벨업 계산
  
처리 시간:
  - 상태 조회: 10-50ms
  - 리워드 지급: 100-500ms
  - 레벨업 계산: 50-200ms
  
비동기 가능:
  ✅ 일부 작업 (리워드, 레벨업)
  
평가: △ 선택적 적용 (3순위)

비동기 적용 대상:
  1. 일일 미션 완료 리워드
     → 즉시 응답 후 백그라운드 지급
  
  2. 레벨업 계산
     → 경험치 누적은 동기
     → 레벨업 효과는 비동기
  
  3. 배치 이벤트 리워드
     → 대량 사용자에게 일괄 지급

작업 흐름:
  1. 사용자: 미션 완료
     → API: RabbitMQ에 태스크 추가
     → 즉시 응답: "처리 중" (< 100ms)
  
  2. Worker (백그라운드):
     → SQLite WAL에 기록
     → 리워드 계산
     → PostgreSQL 업데이트
     → 푸시 알림 (리워드 지급 완료)

장점:
  ✅ 복잡한 계산 비동기 처리
  ✅ 대량 리워드 지급 안정적
```

### 5. location (위치/지도)

```yaml
특징:
  - 재활용 센터 검색
  - 거리 계산
  - 외부 지도 API 호출
  
처리 시간:
  - 검색: 10-50ms (캐시)
  - 외부 API: 200-500ms
  - 거리 계산: 10-20ms
  
비동기 가능:
  △ 실시간 조회 필요하지만 캐싱 가능
  
평가: △ 선택적 캐싱 (5순위)

비동기 적용 대상:
  1. 지도 데이터 갱신
     → 일일 배치로 업데이트
  
  2. 거리 계산 캐싱
     → 자주 검색되는 위치 사전 계산

작업 흐름:
  1. 사용자: 위치 검색
     → API: 캐시 확인
     → 캐시 히트: 즉시 응답 (< 50ms)
     → 캐시 미스: 외부 API + 캐싱
  
  2. Worker (백그라운드, 선택):
     → 인기 위치 사전 계산
     → Redis에 캐싱

권장:
  - 조회: 동기 (캐시 활용)
  - 데이터 갱신: 비동기 배치
```

### 6. info (재활용 정보)

```yaml
특징:
  - 재활용 가이드 조회
  - 분리배출 정보
  - 정적 컨텐츠
  
처리 시간:
  - 조회: 10-50ms
  
비동기 가능:
  ❌ 조회 중심, 실시간 응답 필요
  
평가: ❌ 부적합
이유:
  - 대부분 SELECT
  - 정적 데이터
  - 빠른 응답 필요
  - CDN 캐싱으로 충분
```

### 7. chat (챗봇/LLM) ⭐⭐

```yaml
특징:
  - GPT API 호출
  - 자연어 처리
  - 대화 기록 저장
  
처리 시간:
  - GPT API: 5-15초 (모델 크기에 따라)
  - 대화 저장: 50-100ms
  
비동기 가능:
  ✅ 타이핑 인디케이터 + 백그라운드 처리
  ⚠️ 스트리밍 vs 배치 선택
  
평가: ✅✅ 적합 (2순위)

작업 흐름 (배치 모드):
  1. 사용자: 질문 전송
     → API: RabbitMQ에 태스크 추가
     → 즉시 응답: "생각 중..." (< 100ms)
  
  2. Worker-AI (백그라운드):
     → SQLite WAL에 기록
     → GPT API 호출 (5-15초)
     → PostgreSQL에 대화 저장
     → WebSocket으로 응답 전송
  
  3. 사용자: 실시간 응답 수신

작업 흐름 (스트리밍 모드, 대안):
  → WebSocket 직접 연결
  → GPT 스트리밍 응답
  → 완료 후 PostgreSQL 저장
  (WAL + MQ 불필요)

권장:
  - 스트리밍: WebSocket 직접 (실시간)
  - 배치: WAL + MQ (대량 처리)
  - 히스토리 저장: 비동기
```

---

## 🎯 최종 권장 사항

### 우선순위 적용

```yaml
최우선 (필수):
  1. scan (폐기물 스캔/분석) ⭐⭐⭐
     → Worker-Storage: 이미지 업로드
     → Worker-AI: AI 분석
     
     적용 작업:
       - image_uploader (이미지 S3 업로드)
       - waste_analyzer (AI 폐기물 분류)
       - result_saver (분석 결과 저장)

2순위 (권장):
  2. chat (챗봇) ⭐⭐
     → Worker-AI: GPT 호출
     
     적용 작업:
       - chat_responder (GPT API 호출)
       - history_saver (대화 기록 저장)
     
     단, 스트리밍이면 WebSocket 직접 고려

3순위 (선택):
  3. character (리워드 처리) ⭐
     → Worker (범용): 리워드 계산
     
     적용 작업:
       - reward_distributor (리워드 일괄 지급)
       - level_calculator (레벨업 계산)

부분 적용:
  4. my (프로필 이미지) △
     → Worker-Storage: 이미지 업로드만
     
  5. location (배치 갱신) △
     → Cron Job으로 충분

미적용:
  ❌ auth: 실시간 동기 필수
  ❌ info: 조회 중심, 정적 데이터
```

---

## 🏗️ 아키텍처 재구성

### Worker 노드 역할 분담

```yaml
Worker-Storage (t3.small, 2GB):
  역할: I/O 집약적 작업
  
  담당 도메인:
    1. scan (이미지 업로드) ⭐
       - image_uploader
       - image_resizer
       - thumbnail_generator
    
    2. my (프로필 이미지, 선택)
       - profile_image_uploader
    
  Celery Pool:
    - eventlet (I/O Bound)
    - Concurrency: 100
  
  SQLite WAL:
    - tasks.db (40GB)
    - 이미지 임시 저장

Worker-AI (t3.small, 2GB):
  역할: AI/외부 API 호출
  
  담당 도메인:
    1. scan (AI 분석) ⭐
       - waste_analyzer
       - classification_model
    
    2. chat (GPT 호출) ⭐
       - chat_responder
       - llm_processor
  
  Celery Pool:
    - prefork (Network Bound)
    - Concurrency: 4
  
  SQLite WAL:
    - tasks.db (40GB)
    - AI 요청/응답 임시 저장

RabbitMQ:
  Queues:
    - image_upload_queue (우선순위: 높음)
    - ai_analysis_queue (우선순위: 중간)
    - chat_queue (우선순위: 낮음)
    - reward_queue (우선순위: 낮음)
```

---

## 📊 트래픽 예상

### scan (폐기물 스캔)

```yaml
예상 트래픽:
  - 일간 사용자: 1,000명
  - 1인당 스캔: 3-5회/일
  - 총 스캔: 3,000-5,000회/일
  - 피크: 100-200회/시간

처리 시간:
  - 이미지 업로드: 2-5초
  - AI 분석: 5-30초
  - 총: 10-35초

Worker 용량:
  - Worker-Storage: 100 동시 작업 (eventlet)
    → 초당 20-50 업로드 가능
  
  - Worker-AI: 4 동시 작업 (prefork)
    → 초당 0.1-0.8 분석 (병목!)
    
  ⚠️ Worker-AI 확장 필요할 수 있음
```

### chat (챗봇)

```yaml
예상 트래픽:
  - 일간 사용자: 500명
  - 1인당 대화: 5-10회/일
  - 총 대화: 2,500-5,000회/일
  - 피크: 50-100회/시간

처리 시간:
  - GPT API: 5-15초

Worker 용량:
  - Worker-AI: 4 동시 작업
    → 초당 0.3-0.8 응답
    → 피크 처리 가능
```

---

## 🎯 구현 계획

### Phase 1: scan (최우선)

```bash
# 1. Worker-Storage 배포
- image_uploader 구현
- SQLite WAL 설정
- S3 연동

# 2. Worker-AI 배포
- waste_analyzer 구현
- AI 모델 로딩
- PostgreSQL 연동

# 3. scan-api 수정
- 비동기 엔드포인트
- task_id 반환
- 상태 조회 API
```

### Phase 2: chat (권장)

```bash
# 1. 스트리밍 vs 배치 결정
Option A: WebSocket 스트리밍 (실시간)
Option B: WAL + MQ 배치 (안정성)

# 2. Worker-AI 확장
- chat_responder 구현
- GPT API 연동
- WebSocket 푸시

# 3. chat-api 수정
- 비동기 엔드포인트
- 스트리밍 지원
```

### Phase 3: character (선택)

```bash
# 1. Worker 범용 추가 또는 기존 활용
- reward_distributor 구현
- 대량 지급 배치

# 2. character-api 수정
- 리워드 비동기 처리
- 푸시 알림 연동
```

---

## 📝 결론

### 핵심 적용 도메인

```yaml
✅ scan (폐기물 스캔/분석)
   이유:
     - 이미지 업로드 (느림)
     - AI 분석 (매우 느림, 5-30초)
     - 데이터 손실 불가
     - 사용자 대기 불가
   
   평가: WAL + MQ 필수 ⭐⭐⭐

✅ chat (챗봇/LLM)
   이유:
     - GPT API (느림, 5-15초)
     - 대화 기록 저장
     - 재시도 필요
   
   평가: WAL + MQ 권장 ⭐⭐
   단, 스트리밍이면 WebSocket 직접 고려

△ character (리워드 처리)
   이유:
     - 복잡한 계산
     - 대량 배치 지급
   
   평가: WAL + MQ 선택적 ⭐
```

**최종 권장**: scan을 최우선 적용, chat은 UX에 따라 결정

---

**작성일**: 2025-11-08  
**버전**: v0.6.0 (14-Node)

