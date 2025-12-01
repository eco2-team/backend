# Chat API 로컬 테스트 가이드

## 한눈에 보기

- **기본 포트**: `8030`
- **Swagger**: `http://localhost:8030/api/v1/chat/docs`
- **세션 저장소**: 없음 (요청 단위 Stateless 처리)
- **Auth 우회**: `CHAT_AUTH_DISABLED=true` (기본값 true)
- **OpenAI**: `OPENAI_API_KEY` 가 필수 (분류/RAG/자연어 답변 전 단계에서 사용)

## 1. 사전 준비

```bash
cd /Users/mango/workspace/SeSACTHON/backend
source .venv/bin/activate
pip install -r domains/chat/requirements.txt
pytest domains/chat/tests
```

### 환경 변수

```bash
export CHAT_AUTH_DISABLED=true
export OPENAI_API_KEY=<key>  # Vision · Text 파이프라인 모두 GPT 호출
```

## 2. FastAPI 실행

```bash
uvicorn domains.chat.main:app --reload --port 8030
```

## 3. 기본 점검

```bash
curl -s http://localhost:8030/health | jq

curl -X POST http://localhost:8030/api/v1/chat/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"페트병 어떻게 버려?", "temperature":0.2}' | jq

curl -s http://localhost:8030/api/v1/chat/suggestions | jq
```

## 4. 텍스트/이미지 파이프라인

- 텍스트 요청: GPT-5.1 기반 텍스트 분류 → Lite RAG → 자연어 답변 생성 순으로 처리됩니다.
- `image_url` 포함 시 Vision 분류부터 동일한 파이프라인을 실행합니다.
- 모든 단계에서 `OPENAI_API_KEY` 가 필요하며, 실패 시에만 기본 답변으로 폴백합니다.

## 5. Auth 토글

- 기본값 `CHAT_AUTH_DISABLED=true` 상태에서는 JWT 없이 `/api/v1/chat/*` 요청이 허용됩니다.
- 실제 사용자 권한 흐름을 검증하려면 `CHAT_AUTH_DISABLED=false` 로 실행하고 Auth 스택에서 발급받은 `s_access` 쿠키를 첨부하세요.

## 6. Troubleshooting

| 증상 | 해결책 |
| --- | --- |
| 응답이 항상 동일 | OpenAI 키 누락 또는 파이프라인 오류 시 fallback 문구만 반환됩니다. |
| 401 Unauthorized | Auth 우회 플래그를 true 로 돌리거나 실제 쿠키를 포함하세요. |

