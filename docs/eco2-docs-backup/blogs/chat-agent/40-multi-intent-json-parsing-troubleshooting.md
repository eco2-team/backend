# Multi-Intent JSON 파싱 트러블슈팅

> **작성일**: 2026-01-19
> **환경**: dev (ap-northeast-2)
> **목적**: Multi-Intent 분류기의 `additional_intents` 추출 실패 문제 해결

---

## 1. 개요

### 1.1. 배경

Chat Worker의 Multi-Intent 분류 기능에서 복합 질문 감지는 성공하지만, `additional_intents` 배열이 항상 빈 배열로 반환되는 문제가 발생했다.

**주요 이슈:**
- `has_multi_intent: true`로 감지되지만 `additional_intents: []` 반환
- LLM 응답의 JSON 파싱 실패
- Worker 로그에서 warning 메시지 확인됨

### 1.2. 영향 범위

- Chat Worker: `intent_classifier_service.py`
- Value Objects: `chat_intent.py`
- LangGraph Pipeline: Multi-Intent 분기 라우팅

---

## 2. 관측된 문제

### 2.1. 증상

```bash
# E2E 테스트 실행
curl -s -X POST "https://api.dev.growbin.app/api/v1/chat/$CHAT_ID/messages" \
  -H "Cookie: s_access=$TOKEN" \
  -d '{"message": "플라스틱 분리배출 방법이랑 근처 수거함 위치도 알려줘"}'
```

**예상 결과:**
```json
{
  "intent": "waste",
  "has_multi_intent": true,
  "additional_intents": ["location"]
}
```

**실제 결과:**
```json
{
  "intent": "waste",
  "has_multi_intent": true,
  "additional_intents": []
}
```

→ **`additional_intents`가 항상 빈 배열로 반환됨**

### 2.2. Worker 로그 분석

```bash
kubectl logs -n chat deploy/chat-worker -c chat-worker --tail=200 | grep -iE 'warning|error|failed'
```

**발견된 Warning:**
```
[WARNING] Failed to parse multi-intent response: ```json "is_multi": true,
```

→ **LLM 응답이 마크다운 코드블록으로 감싸져 있어 JSON 파싱 실패**

---

## 3. 원인 분석

### 3.1. 문제 지점 추적

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         데이터 흐름 추적                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   User Query                                                                │
│   └─▶ IntentClassifierService.classify()                                   │
│       └─▶ Rule-based Detection  ✅ 정상                                     │
│       └─▶ _detect_multi_intent()  ✅ LLM 호출 성공                          │
│       └─▶ parse_multi_detect_response()  ❌ JSON 파싱 실패                  │
│           └─▶ json.loads() 실패 (마크다운 블록 포함)                         │
│           └─▶ catch → MultiIntentResult(is_multi=True, categories=[])       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 3.2. 근본 원인: LLM 응답 형식

**LLM 실제 응답:**
```
```json
{
  "is_multi": true,
  "categories": ["waste", "location"],
  "confidence": 0.93
}
```
```

**문제 코드 (intent_classifier_service.py:320-325):**
```python
def parse_multi_detect_response(self, response: str) -> MultiIntentResult:
    try:
        data = json.loads(response)  # ❌ 마크다운 블록 포함 시 실패
        return MultiIntentResult(
            is_multi=data.get("is_multi", False),
            categories=data.get("categories", []),
            confidence=data.get("confidence", 0.0),
        )
    except json.JSONDecodeError:
        # 파싱 실패 시 빈 categories 반환
        return MultiIntentResult(is_multi=True, categories=[], confidence=0.0)
```

### 3.3. 추가 발견: ChatIntent.simple() 메서드 누락

Multi-Intent 분류 후 개별 Intent 생성 시 `ChatIntent.simple()` 팩토리 메서드 호출:

```python
# classify_intent_command.py:282
chat_intent = ChatIntent.simple(
    intent=classified_intent,
    confidence=confidence,
    complexity=QueryComplexity.SIMPLE,
)
```

**문제:** `ChatIntent` 클래스에 `simple()` 메서드가 정의되어 있지 않음

---

## 4. 해결 방안

### 4.1. JSON 추출 헬퍼 메서드 추가

**수정 파일:** `apps/chat_worker/application/services/intent_classifier_service.py`

```python
def _extract_json_from_response(self, response: str) -> str:
    """LLM 응답에서 JSON 부분만 추출.

    LLM이 ```json ... ``` 형태로 응답하는 경우 마크다운 블록을 제거하고
    순수 JSON 문자열만 반환합니다.

    Args:
        response: LLM 원본 응답

    Returns:
        순수 JSON 문자열
    """
    text = response.strip()

    # 마크다운 코드블록 제거 (```json ... ``` 또는 ``` ... ```)
    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]  # 첫 줄(```json) 제거
        else:
            text = text[3:]  # ``` 만 있는 경우

        # 끝의 ``` 제거
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]

        text = text.strip()

    # JSON 객체 시작/끝 위치 찾기
    start_idx = text.find("{")
    end_idx = text.rfind("}")

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        text = text[start_idx : end_idx + 1]

    return text
```

### 4.2. 파싱 메서드 수정

```python
def parse_multi_detect_response(self, response: str) -> MultiIntentResult:
    try:
        cleaned = self._extract_json_from_response(response)  # ✅ 헬퍼 사용
        data = json.loads(cleaned)
        return MultiIntentResult(
            is_multi=data.get("is_multi", False),
            categories=data.get("categories", []),
            confidence=data.get("confidence", 0.0),
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse multi-intent response: {e}")
        return MultiIntentResult(is_multi=True, categories=[], confidence=0.0)


def parse_decompose_response(self, response: str) -> list[DecomposedIntent]:
    try:
        cleaned = self._extract_json_from_response(response)  # ✅ 동일 적용
        data = json.loads(cleaned)
        # ...
```

### 4.3. ChatIntent.simple() 팩토리 메서드 추가

**수정 파일:** `apps/chat_worker/domain/value_objects/chat_intent.py`

```python
@classmethod
def simple(
    cls,
    intent: str | Intent,
    confidence: float = 1.0,
    complexity: QueryComplexity = QueryComplexity.SIMPLE,
) -> "ChatIntent":
    """지정된 의도로 ChatIntent 생성 (팩토리 메서드).

    Args:
        intent: 의도 (문자열 또는 Intent enum)
        confidence: 신뢰도 (0.0 ~ 1.0)
        complexity: 복잡도 (기본: SIMPLE)

    Returns:
        ChatIntent 인스턴스
    """
    if isinstance(intent, str):
        intent = Intent.from_string(intent)
    return cls(
        intent=intent,
        complexity=complexity,
        confidence=confidence,
    )
```

---

## 5. 커밋 및 배포

### 5.1. PR #435: JSON 파싱 수정

```bash
git checkout -b fix/multi-intent-json-parsing
# intent_classifier_service.py 수정
git add apps/chat_worker/application/services/intent_classifier_service.py
git commit -m "fix(chat-worker): extract JSON from markdown-wrapped LLM response

- Add _extract_json_from_response() helper method
- Handle ```json ... ``` code blocks in LLM responses
- Apply to parse_multi_detect_response() and parse_decompose_response()

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push origin fix/multi-intent-json-parsing
gh pr create --title "fix(chat-worker): Multi-Intent JSON 파싱 수정" --body "..."
gh pr merge --squash
```

### 5.2. PR #436: ChatIntent.simple() 추가

```bash
git checkout -b fix/chat-intent-simple-factory
# chat_intent.py 수정
git add apps/chat_worker/domain/value_objects/chat_intent.py
git commit -m "feat(chat-worker): add ChatIntent.simple() factory method

- Add simple() classmethod for creating ChatIntent with string intent
- Support Intent enum conversion from string

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
git push origin fix/chat-intent-simple-factory
gh pr create --title "feat(chat-worker): ChatIntent.simple() 팩토리 추가" --body "..."
gh pr merge --squash
```

### 5.3. 클러스터 배포

```bash
# ArgoCD Hard Refresh
kubectl label application -n argocd dev-chat-worker \
  argocd.argoproj.io/refresh=hard --overwrite

# Deployment 삭제 (Self-Heal 트리거)
kubectl delete deploy chat-worker -n chat

# Rollout 대기
kubectl rollout status deploy/chat-worker -n chat --timeout=120s
```

---

## 6. 핵심 교훈

### 6.1. LLM 응답 형식 불확실성

> **"LLM 응답은 항상 래핑될 수 있다"**

LLM이 JSON을 반환할 때 마크다운 코드블록으로 감싸는 경우가 빈번함.
모든 LLM 응답 파싱 로직에 전처리 단계 필수.

### 6.2. 방어적 파싱

> **"파싱 실패 시 기본값 반환보다 복구 시도"**

단순히 빈 배열 반환하지 않고, 다양한 형식에서 JSON 추출 시도.

### 6.3. 팩토리 메서드 일관성

> **"Value Object 생성은 팩토리 메서드로 통일"**

`ChatIntent.simple()`, `ChatIntent.simple_waste()` 등 용도별 팩토리 제공.

---

## 7. 관련 문서

- [37-sse-event-bus-troubleshooting.md](./37-sse-event-bus-troubleshooting.md) - SSE 이벤트 파이프라인
- [SKILL.md: chat-agent-flow](./.claude/skills/chat-agent-flow/SKILL.md) - Chat Agent 아키텍처

---

## 8. 참고 자료

- [LangGraph Multi-Intent Routing](https://langchain-ai.github.io/langgraph/)
- [OpenAI JSON Mode](https://platform.openai.com/docs/guides/json-mode)
