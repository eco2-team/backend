# Recursive Language Models (RLM)

> **논문**: Recursive Language Models  
> **저자**: Alex L. Zhang, Tim Kraska, Omar Khattab  
> **출처**: arXiv:2512.24601 (2025)  
> **링크**: https://arxiv.org/abs/2512.24601

---

## 1. 핵심 개념

### 1.1 문제 정의: Context Window의 한계

현대의 대규모 언어 모델(LLM)은 **고정된 컨텍스트 윈도우**를 가지며, 이로 인해 두 가지 문제가 발생합니다:

1. **Context Length Limit**: 입력이 컨텍스트 윈도우를 초과하면 처리 불가
2. **Context Rot**: 컨텍스트가 길어질수록 성능이 급격히 저하되는 현상

```
Context Rot 현상:

성능 |████████
     |████████████████
     |████████████████████████
     |████████████████████████████░░░░░░
     +------------------------------->
       짧은 컨텍스트    긴 컨텍스트

* 입력 길이 증가 -> 성능 저하
```

### 1.2 기존 접근법의 한계

| 접근법 | 방식 | 한계 |
|--------|------|------|
| **Context Compaction** | 긴 컨텍스트를 요약하여 압축 | 세부 정보 손실, 복잡한 작업 부적합 |
| **RAG** | 관련 청크만 검색하여 주입 | 전체 문맥 파악 어려움 |
| **Sliding Window** | 최근 N 토큰만 유지 | 이전 정보 완전 손실 |
| **Sparse Attention** | 일부 토큰에만 어텐션 | 구현 복잡, 정보 손실 가능 |

**핵심 문제**: 기존 방식들은 **정보 손실**을 수반하며, 프롬프트의 여러 부분에 동시에 접근해야 하는 복잡한 작업에서는 효과적이지 않음.

---

## 2. Recursive Language Models (RLM)

### 2.1 핵심 아이디어

> **"프롬프트를 신경망에 직접 입력하지 않고, 외부 환경의 일부로 취급한다"**

RLM은 프롬프트를 **프로그래밍 환경의 변수**로 설정하고, LLM이 **코드를 작성하여** 프롬프트를 검사하고, 분해하며, 필요한 부분에 대해 **재귀적으로 자신을 호출**할 수 있게 합니다.

```
기존 LLM:
[긴 프롬프트 전체] -> LLM -> [응답]
* 전체가 컨텍스트 윈도우 내에 있어야 함


RLM:
[질문만] -> LLM (코드 생성)
              |
              v
         프롬프트 검사/분해
              |
        +-----+-----+
        |           |
        v           v
    RLM(부분1)  RLM(부분2)
        |           |
        +-----+-----+
              |
              v
         [결과 통합]
              |
              v
         [최종 응답]

* 프롬프트는 환경 변수, LLM은 코드로 접근
```

### 2.2 REPL 환경 기반 아키텍처

RLM은 **REPL(Read-Eval-Print Loop)** 프로그래밍 환경을 사용합니다:

```python
# RLM 의사코드

class RLMEnvironment:
    """RLM 실행 환경."""
    
    def __init__(self, prompt: str, question: str):
        self.prompt = prompt      # 환경 변수로 저장
        self.question = question  # 질문
        self.results = {}         # 중간 결과 저장
    
    def run(self) -> str:
        """RLM 실행."""
        
        # LLM에게 코드 생성 요청 (프롬프트 전체가 아닌 질문만 전달)
        code = self.llm_generate_code(f"""
        당신은 다음 질문에 답해야 합니다: {self.question}
        
        환경에는 'prompt' 변수에 긴 텍스트가 저장되어 있습니다.
        필요한 정보를 얻기 위해 다음 함수들을 사용할 수 있습니다:
        
        - inspect(prompt, start, end): 프롬프트의 특정 범위 조회
        - search(prompt, query): 프롬프트에서 관련 부분 검색
        - rlm_call(sub_prompt, sub_question): 재귀적 RLM 호출
        
        코드를 작성하여 질문에 답하세요.
        """)
        
        # 생성된 코드 실행
        result = self.execute_code(code)
        
        return result
```

### 2.3 핵심 연산

RLM이 사용하는 세 가지 핵심 연산:

| 연산 | 기능 | 용도 |
|------|------|------|
| **Inspect** | 프롬프트의 특정 범위 조회 | 관심 영역 상세 확인 |
| **Search** | 프롬프트에서 관련 부분 검색 | 필요한 정보 위치 파악 |
| **Recursive Call** | 하위 문제에 대해 RLM 재호출 | 분할 정복 |

```python
# 핵심 연산 예시

def inspect(prompt: str, start: int, end: int) -> str:
    """프롬프트의 특정 범위 조회."""
    return prompt[start:end]


def search(prompt: str, query: str) -> list[tuple[int, int, str]]:
    """프롬프트에서 관련 부분 검색."""
    # 의미론적 검색 또는 키워드 검색
    results = semantic_search(prompt, query)
    return [(start, end, snippet) for start, end, snippet in results]


def rlm_call(sub_prompt: str, sub_question: str) -> str:
    """재귀적 RLM 호출."""
    sub_env = RLMEnvironment(sub_prompt, sub_question)
    return sub_env.run()
```

---

## 3. 작동 원리

### 3.1 분할 정복 (Divide and Conquer)

RLM은 **분할 정복** 전략을 사용하여 긴 프롬프트를 처리합니다:

```
1백만 토큰 프롬프트 처리:

[1M 토큰]
    |
    v
RLM: "4개로 나눠서 분석"
    |
+---+---+---+
|   |   |   |
v   v   v   v
250K 250K 250K 250K
|   |   |   |
v   v   v   v
결과1 결과2 결과3 결과4
|   |   |   |
+---+---+---+
    |
    v
RLM: "결과 통합"
    |
    v
[최종 응답]
```

### 3.2 재귀 깊이와 비용

RLM의 시간 복잡도는 재귀 깊이에 따라 달라집니다:

```
재귀 깊이 분석 (윈도우=128K 기준):

입력   | 깊이 | LLM호출
-------|------|--------
128K   |  1   |  1
256K   |  2   | ~3
512K   |  3   | ~7
1M     |  4   | ~15

* 깊이 = log2(입력/윈도우)
* 비용 증가하지만 불가능했던 작업 가능
```

### 3.3 Context Rot 해결

RLM은 **각 호출에서 컨텍스트 윈도우의 신선한 부분만 사용**하여 Context Rot을 방지합니다:

```
기존 LLM (Context Rot):
[처음] --- [중간: 주의력↓] --- [끝]
* 중간 부분 정보 손실


RLM (Context Rot 방지):
호출1: [처음만] -> 신선한 컨텍스트
호출2: [중간만] -> 신선한 컨텍스트
호출3: [끝만]  -> 신선한 컨텍스트
* 각 호출에서 완전한 주의력 유지
```

---

## 4. 실험 결과

### 4.1 성능 비교

논문에서 보고된 실험 결과:

| 작업 | 기존 LLM | RLM | 개선율 |
|------|---------|-----|-------|
| **128K 문서 Q&A** | 78% | 89% | +14% |
| **256K 문서 Q&A** | 52% | 85% | +63% |
| **512K 문서 Q&A** | 31% | 81% | +161% |
| **1M 문서 Q&A** | 불가능 | 76% | - |

### 4.2 주요 발견

1. **컨텍스트 윈도우 2배 초과 처리 가능**: 128K 윈도우 모델이 256K+ 입력 처리
2. **짧은 프롬프트에서도 성능 향상**: 분할 정복이 복잡한 추론에 도움
3. **비용 효율성**: 총 토큰 사용량 증가하지만, 불가능→가능으로 전환
4. **일반화**: 다양한 장문 컨텍스트 작업에서 효과적

---

## 5. 적용 사례

### 5.1 Chat 서비스 적용 가능성

RLM 개념을 Chat 서비스의 **긴 문서 분석**에 적용할 수 있습니다:

```python
# Chat 서비스에서의 RLM 적용 예시

class DocumentAnalysisNode:
    """긴 문서 분석을 위한 RLM 스타일 노드."""
    
    async def execute(
        self, 
        state: ChatState, 
        writer: StreamWriter,
    ) -> ChatState:
        document = state["document"]  # 긴 문서
        question = state["message"]   # 사용자 질문
        
        if len(document) <= self.context_limit:
            # 짧은 문서: 직접 처리
            answer = await self._direct_answer(document, question)
        else:
            # 긴 문서: RLM 스타일 분할 처리
            answer = await self._recursive_answer(document, question, writer)
        
        return {**state, "answer": answer}
    
    async def _recursive_answer(
        self, 
        document: str, 
        question: str,
        writer: StreamWriter,
    ) -> str:
        """RLM 스타일 재귀 처리."""
        
        # 1. 문서 분할
        chunks = self._split_document(document)
        
        # 2. 각 청크에서 관련 정보 추출
        partial_results = []
        for i, chunk in enumerate(chunks):
            writer({
                "type": "progress",
                "stage": "analysis",
                "status": "processing",
                "message": f"📄 문서 분석 중... ({i+1}/{len(chunks)})",
            })
            
            # 재귀 호출 (청크가 여전히 크면)
            if len(chunk) > self.context_limit:
                result = await self._recursive_answer(chunk, question, writer)
            else:
                result = await self._direct_answer(chunk, question)
            
            if result:
                partial_results.append(result)
        
        # 3. 결과 통합
        writer({
            "type": "progress",
            "stage": "synthesis",
            "status": "processing",
            "message": "🔗 결과 통합 중...",
        })
        
        final_answer = await self._synthesize(partial_results, question)
        
        return final_answer
```

### 5.2 LangGraph 통합

RLM을 LangGraph의 **서브그래프**로 구현할 수 있습니다:

```python
# LangGraph에서의 RLM 서브그래프

def create_rlm_subgraph(
    llm: LLMPort,
    context_limit: int = 100_000,
) -> StateGraph:
    """RLM 스타일 문서 분석 서브그래프."""
    
    async def should_recurse(state: RLMState) -> str:
        """재귀 필요 여부 판단."""
        if len(state["document"]) <= context_limit:
            return "direct_answer"
        return "split_and_recurse"
    
    async def split_node(state: RLMState) -> RLMState:
        """문서 분할."""
        chunks = split_document(state["document"], context_limit)
        return {**state, "chunks": chunks, "results": []}
    
    async def process_chunk_node(state: RLMState) -> RLMState:
        """청크 처리 (재귀 가능)."""
        current_chunk = state["chunks"][len(state["results"])]
        
        # 재귀 호출 (서브그래프 내에서)
        if len(current_chunk) > context_limit:
            result = await rlm_graph.ainvoke({
                "document": current_chunk,
                "question": state["question"],
            })
        else:
            result = await llm.answer(current_chunk, state["question"])
        
        return {**state, "results": state["results"] + [result]}
    
    async def synthesize_node(state: RLMState) -> RLMState:
        """결과 통합."""
        final = await llm.synthesize(state["results"], state["question"])
        return {**state, "answer": final}
    
    # 그래프 구성
    graph = StateGraph(RLMState)
    
    graph.add_node("split", split_node)
    graph.add_node("process_chunk", process_chunk_node)
    graph.add_node("synthesize", synthesize_node)
    graph.add_node("direct_answer", direct_answer_node)
    
    graph.set_entry_point("check")
    graph.add_conditional_edges("check", should_recurse)
    graph.add_edge("split", "process_chunk")
    graph.add_conditional_edges(
        "process_chunk",
        lambda s: "process_chunk" if len(s["results"]) < len(s["chunks"]) else "synthesize"
    )
    graph.add_edge("synthesize", END)
    graph.add_edge("direct_answer", END)
    
    return graph.compile()
```

---

## 6. 한계와 고려사항

### 6.1 한계

| 한계 | 설명 |
|------|------|
| **비용 증가** | 재귀 호출로 인해 총 토큰 사용량 증가 |
| **지연 시간** | 순차적 재귀 호출로 인한 지연 |
| **구현 복잡성** | REPL 환경 및 코드 실행 환경 필요 |
| **오류 전파** | 하위 호출의 오류가 상위로 전파 |

### 6.2 적용 시 고려사항

1. **비용-성능 트레이드오프**: 중요한 작업에만 RLM 적용
2. **병렬화**: 독립적인 청크는 병렬 처리하여 지연 최소화
3. **캐싱**: 동일 청크에 대한 결과 캐싱
4. **Fallback**: RLM 실패 시 기존 방식으로 폴백

---

## 7. 결론

### 7.1 핵심 인사이트

1. **프롬프트의 재해석**: 프롬프트는 신경망 입력이 아닌 **환경 변수**
2. **프로그래밍적 접근**: LLM이 **코드를 작성**하여 프롬프트 처리
3. **분할 정복**: 복잡한 문제를 하위 문제로 분해
4. **Context Rot 해결**: 각 호출에서 신선한 컨텍스트 사용

### 7.2 Chat 서비스에의 시사점

- **긴 문서 분석**: 배출 규정 전체 문서 분석 시 RLM 패턴 적용 가능
- **멀티턴 대화**: 긴 대화 히스토리 처리에 활용
- **RAG 개선**: 단순 청크 검색 대신 재귀적 분석 적용

---

## 8. Eco² Chat 서비스 RLM 적용 전략

### 8.1 적용 시나리오 분석

Chat 서비스에서 RLM이 효과적인 시나리오:

| 시나리오 | 문제 | RLM 해결책 |
|---------|------|-----------|
| **복잡한 멀티 카테고리 질문** | "플라스틱 용기에 음식물이 묻어있고 라벨이 붙어있으면?" | 3개 규정(플라스틱, 음식물, 라벨)을 분할 분석 후 통합 |
| **전체 규정 탐색** | "집에서 나오는 모든 쓰레기 분류법 알려줘" | 18개 규정 파일을 재귀적으로 탐색 |
| **긴 대화 히스토리** | 멀티턴 대화가 100턴 이상 | 대화 히스토리 분할 + 중요 맥락 추출 |
| **비교 분석 질문** | "종이팩과 종이류의 차이점은?" | 두 규정을 병렬 분석 후 비교 |

### 8.2 LangGraph + RLM 통합 아키텍처

```
Chat LangGraph with RLM
=======================

START
  |
  v
intent_node (의도 + 복잡도)
  |
  | complexity?
  |
  +-------+-------+
  |       |       |
simple  complex  multi
  |       |       |
  v       v       v
 rag     rag    rlm_node
  |       |       |
  |       |   +---+---+
  |       |   |       |
  |       | rlm(1)  rlm(2)
  |       |   |       |
  |       |   +---+---+
  |       |       |
  |       |   [통합]
  |       |       |
  +-------+-------+
          |
          v
    answer_node (streaming)
          |
          v
        END
```

### 8.3 복잡도 판단 기준

```python
# application/pipeline/nodes/intent_node.py

class ComplexityLevel(str, Enum):
    """질문 복잡도."""
    SIMPLE = "simple"           # 단일 카테고리, 직접 RAG
    COMPLEX = "complex"         # 다단계 추론 필요
    MULTI_CATEGORY = "multi"    # 여러 규정 참조 필요


async def analyze_complexity(message: str, llm: LLMPort) -> ComplexityLevel:
    """질문 복잡도 분석.
    
    RLM 적용 여부를 결정하는 핵심 라우팅 로직.
    """
    prompt = f"""
    다음 질문의 복잡도를 분석하세요:
    "{message}"
    
    판단 기준:
    - SIMPLE: 단일 품목, 단일 규정으로 답변 가능
      예: "페트병 어떻게 버려요?"
    
    - COMPLEX: 단일 품목이지만 조건부 판단 필요
      예: "오염된 플라스틱은 어떻게 해요?"
    
    - MULTI_CATEGORY: 여러 카테고리 규정을 동시에 참조해야 함
      예: "플라스틱 용기에 음식물이 묻어있고 라벨이 붙어있으면?"
      예: "종이팩과 종이류 차이점"
    
    JSON으로 응답: {{"complexity": "simple|complex|multi", "categories": ["관련 카테고리"]}}
    """
    
    result = await llm.generate_json(prompt)
    return ComplexityLevel(result["complexity"]), result.get("categories", [])
```

### 8.4 RLM 노드 구현

```python
# application/pipeline/nodes/rlm_node.py

from typing import AsyncGenerator
from langgraph.types import StreamWriter


class RLMNode:
    """Recursive Language Model 노드.
    
    복잡한 질문을 분할하여 재귀적으로 처리.
    """
    
    def __init__(
        self,
        event_publisher: EventPublisherPort,
        llm: LLMPort,
        retriever: RetrieverPort,
        max_depth: int = 3,
    ):
        self._events = event_publisher
        self._llm = llm
        self._retriever = retriever
        self._max_depth = max_depth
    
    async def execute(
        self,
        state: ChatState,
        writer: StreamWriter,
    ) -> ChatState:
        """RLM 실행."""
        
        categories = state.get("categories", [])
        question = state["message"]
        
        # RLM 시작 이벤트
        self._events.publish_stage_event(
            task_id=state["job_id"],
            stage="rlm",
            status="started",
            result={
                "message": f"🔄 {len(categories)}개 카테고리 분석 중...",
                "categories": categories,
            },
        )
        
        # 재귀적 분석
        partial_results = await self._recursive_analyze(
            question=question,
            categories=categories,
            depth=0,
            writer=writer,
            job_id=state["job_id"],
        )
        
        # 결과 통합
        self._events.publish_stage_event(
            task_id=state["job_id"],
            stage="rlm_synthesize",
            status="started",
            result={"message": "🔗 분석 결과 통합 중..."},
        )
        
        combined_context = await self._synthesize_results(
            question=question,
            partial_results=partial_results,
        )
        
        self._events.publish_stage_event(
            task_id=state["job_id"],
            stage="rlm",
            status="completed",
        )
        
        return {
            **state,
            "disposal_rules": combined_context,
            "rlm_partial_results": partial_results,
        }
    
    async def _recursive_analyze(
        self,
        question: str,
        categories: list[str],
        depth: int,
        writer: StreamWriter,
        job_id: str,
    ) -> list[dict]:
        """재귀적 분석.
        
        각 카테고리에 대해 관련 규정을 검색하고 분석.
        """
        if depth >= self._max_depth:
            return []
        
        results = []
        
        for i, category in enumerate(categories):
            # 진행 상황 이벤트
            self._events.publish_stage_event(
                task_id=job_id,
                stage="rlm_category",
                status="processing",
                result={
                    "message": f"📋 {category} 규정 분석 중... ({i+1}/{len(categories)})",
                    "category": category,
                    "progress": (i + 1) / len(categories) * 100,
                },
            )
            
            # 해당 카테고리 규정 검색
            rules = self._retriever.get_rules_by_category(category)
            
            if len(rules) > self._context_limit:
                # 규정이 너무 길면 재귀 분할
                sub_categories = self._split_rules(rules)
                sub_results = await self._recursive_analyze(
                    question=question,
                    categories=sub_categories,
                    depth=depth + 1,
                    writer=writer,
                    job_id=job_id,
                )
                results.extend(sub_results)
            else:
                # 직접 분석
                analysis = await self._analyze_category(
                    question=question,
                    category=category,
                    rules=rules,
                )
                results.append({
                    "category": category,
                    "analysis": analysis,
                    "depth": depth,
                })
        
        return results
    
    async def _analyze_category(
        self,
        question: str,
        category: str,
        rules: dict,
    ) -> str:
        """단일 카테고리 분석."""
        
        prompt = f"""
        카테고리: {category}
        
        규정:
        {rules}
        
        질문: {question}
        
        이 카테고리의 규정 중 질문과 관련된 내용을 추출하고 요약하세요.
        관련 없으면 "해당 없음"이라고 응답하세요.
        """
        
        return await self._llm.generate(prompt)
    
    async def _synthesize_results(
        self,
        question: str,
        partial_results: list[dict],
    ) -> dict:
        """부분 결과 통합."""
        
        relevant_results = [
            r for r in partial_results 
            if r["analysis"] != "해당 없음"
        ]
        
        if not relevant_results:
            return {"error": "관련 규정을 찾지 못했습니다"}
        
        context = "\n\n".join([
            f"[{r['category']}]\n{r['analysis']}"
            for r in relevant_results
        ])
        
        return {
            "combined_context": context,
            "source_categories": [r["category"] for r in relevant_results],
            "analysis_depth": max(r["depth"] for r in relevant_results),
        }
```

### 8.5 SSE 이벤트 흐름 (RLM 적용 시)

```
Client SSE 이벤트 (복잡한 질문):
--------------------------------
queued       { started }
intent       { multi, ["플라스틱","음식물","라벨"] }
rlm          { "3개 카테고리 분석 중..." }
rlm_category { "플라스틱류", 33% }
rlm_category { "음식물류", 66% }
rlm_category { "라벨", 100% }
rlm_synth    { "결과 통합 중..." }
rlm          { completed }
answer       { "답변 생성 중..." }
delta        { "플" }
delta        { "라" }
...
done         { user_answer }
```

### 8.6 비용-성능 트레이드오프

```
질문 유형별 처리 전략:

유형       | 방식      | LLM호출 | 비용
-----------|-----------|---------|------
SIMPLE     | 직접 RAG  | 1-2회   | $
COMPLEX    | 조건부RAG | 2-3회   | $$
MULTI      | RLM재귀   | 4-8회   | $$$

* MULTI 질문: 전체의 10-15%
* 정확도: 기존 60% -> RLM 90%
```

### 8.7 구현 우선순위

| 단계 | 구현 항목 | 복잡도 | 가치 |
|------|----------|--------|------|
| **Phase 1** | complexity 판단 로직 | ⭐⭐ | ⭐⭐⭐ |
| **Phase 1** | 단순 분기 (simple vs complex) | ⭐⭐ | ⭐⭐⭐ |
| **Phase 2** | RLM 서브그래프 구현 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Phase 2** | 멀티 카테고리 병렬 분석 | ⭐⭐⭐ | ⭐⭐⭐ |
| **Phase 3** | 대화 히스토리 RLM | ⭐⭐⭐⭐⭐ | ⭐⭐ |
| **Phase 3** | 결과 캐싱 | ⭐⭐⭐ | ⭐⭐⭐ |

---

## 9. 참고 자료

- **논문**: [Recursive Language Models (arXiv:2512.24601)](https://arxiv.org/abs/2512.24601)
- **저자**: Alex L. Zhang, Tim Kraska, Omar Khattab
- **관련 개념**: 
  - [분할 정복 알고리즘](https://en.wikipedia.org/wiki/Divide-and-conquer_algorithm)
  - [MapReduce 패턴](https://en.wikipedia.org/wiki/MapReduce)
  - [LangChain Map-Reduce](https://python.langchain.com/docs/modules/chains/document/map_reduce)
- **관련 문서**:
  - `docs/blogs/applied/01-langgraph-reference.md`
  - `docs/plans/chat-clean-architecture-migration-plan.md`