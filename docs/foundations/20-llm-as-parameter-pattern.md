# Dependency Injection for LLM (모델 주입 패턴)

> LLM 모델을 함수의 파라미터로 전달하여 에이전트 로직과 모델 선택을 분리하는 설계 패턴

## 용어 정의

> ⚠️ **Note**: 이 문서에서 설명하는 패턴은 **공식적인 명칭이 없습니다.**
> 기존 소프트웨어 설계 패턴(Dependency Injection, Strategy Pattern)을 LLM 컨텍스트에 적용한 것입니다.

**이 패턴을 설명하는 다양한 표현:**
- **Dependency Injection for LLM** - DI 패턴의 LLM 적용
- **Strategy Pattern for Model Selection** - 전략 패턴 관점
- **Provider Abstraction** - 프로바이더 추상화
- **Pluggable LLM Backend** - 교체 가능한 LLM 백엔드
- **Model as Configuration** - 모델을 설정으로 취급

**실제 구현 사례:**
- Cursor IDE - API 요청 시 `model` 파라미터로 전달
- LangChain - `llm` 파라미터로 모델 객체 주입
- CrewAI - Agent 생성 시 `llm` 인자 지정
- 당근 LLM Router - API 호출 시 `model` 필드로 지정

## 개요

LLM-as-Parameter 패턴은 AI 에이전트나 LLM 기반 애플리케이션에서 **모델 선택을 외부화**하는 설계 패턴이다. 이 패턴에서 LLM은 에이전트 내부에서 고정되지 않고, 함수 호출 시 파라미터로 전달된다.

## 핵심 원칙

### 의존성 역전 원칙 (Dependency Inversion)

```
전통적 접근 (High Coupling)
────────────────────────────
Agent → GPT-4 (직접 의존)

LLM-as-Parameter (Low Coupling)
───────────────────────────────
Agent → LLM Interface ← GPT-4
                       ← Claude
                       ← Gemini
```

에이전트가 구체적인 LLM 구현체가 아닌 **추상화된 인터페이스**에 의존하게 함으로써 결합도를 낮춘다.

## 패턴 구조

### 기본 구조

```python
# ❌ Anti-pattern: 모델 하드코딩
class ChatAgent:
    def __init__(self):
        self.llm = OpenAI(model="gpt-4")  # 하드코딩된 의존성
    
    def chat(self, message: str) -> str:
        return self.llm.complete(message)

# ✅ LLM-as-Parameter 패턴
class ChatAgent:
    def __init__(self, llm: LLMInterface):  # 주입받은 LLM
        self.llm = llm
    
    def chat(self, message: str) -> str:
        return self.llm.complete(message)

# 사용 시점에 모델 결정
agent = ChatAgent(llm=OpenAI(model="gpt-4"))
agent = ChatAgent(llm=Anthropic(model="claude-3-opus"))
```

### API 레벨 적용

```python
# HTTP API 엔드포인트에서 모델을 파라미터로 받음
@app.post("/v1/agents/run")
async def run_agent(request: AgentRunRequest):
    """
    Request Body:
    {
        "prompt": "...",
        "model": "claude-4-sonnet",  ← 클라이언트가 모델 선택
        "tools": [...]
    }
    """
    agent = create_agent(model=request.model)
    return await agent.run(request.prompt)
```

## 실제 구현 사례

### 1. Cursor IDE

Cursor는 대표적인 LLM-as-Parameter 패턴 구현체다.

**프론트엔드 (Model Selector UI)**
```typescript
// IDE UI에서 모델 선택
interface ModelSelectorProps {
  selectedModel: string;
  onModelChange: (model: string) => void;
  availableModels: Model[];
}

const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedModel,
  onModelChange,
  availableModels
}) => (
  <Select value={selectedModel} onChange={onModelChange}>
    {availableModels.map(model => (
      <Option key={model.id} value={model.id}>
        {model.name}
      </Option>
    ))}
  </Select>
);
```

**백엔드 (Cloud Agents API)**
```json
POST /v0/agents
{
    "prompt": {
        "text": "Create a REST API for user management"
    },
    "model": "claude-4-sonnet",
    "source": {
        "repository": "https://github.com/example/project"
    }
}
```

**API 응답 스펙**
```
POST /v0/agents
Request Body:
  - prompt (required): 실행할 프롬프트
  - model (optional): 사용할 LLM (예: claude-4-sonnet)
    지정하지 않으면 가장 적합한 모델을 자동으로 선택
  - source (required): 소스 저장소 정보
```

### 2. LangChain

LangChain은 `llm` 파라미터를 통해 모델을 주입받는다.

```python
from langchain.agents import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

# 동일한 에이전트 로직, 다른 모델
def create_coding_agent(model: str):
    if model.startswith("gpt"):
        llm = ChatOpenAI(model=model)
    elif model.startswith("claude"):
        llm = ChatAnthropic(model=model)
    else:
        raise ValueError(f"Unsupported model: {model}")
    
    return create_react_agent(
        llm=llm,  # 파라미터로 전달
        tools=[code_executor, file_manager, searcher],
        prompt=REACT_PROMPT
    )

# 런타임에 모델 결정
agent = create_coding_agent(model="gpt-4-turbo")
agent = create_coding_agent(model="claude-3-sonnet")
```

### 3. CrewAI

멀티에이전트 시스템에서 각 에이전트에 다른 모델 할당.

```python
from crewai import Agent, Task, Crew

# 연구 작업에는 GPT-4 (추론 능력)
researcher = Agent(
    role="Senior Researcher",
    goal="Research emerging technologies",
    llm="gpt-4",  # 파라미터로 모델 지정
    tools=[web_search, arxiv_search]
)

# 작문 작업에는 Claude (자연어 생성 능력)
writer = Agent(
    role="Technical Writer",
    goal="Create comprehensive documentation",
    llm="claude-3-opus",  # 다른 모델 지정
    tools=[document_writer]
)

# 리뷰 작업에는 경량 모델 (비용 최적화)
reviewer = Agent(
    role="Quality Reviewer",
    goal="Review and improve content",
    llm="gpt-3.5-turbo",  # 비용 효율적 모델
    tools=[grammar_checker]
)
```

### 4. 당근 LLM Router

플랫폼 레벨에서 모델을 파라미터로 받아 라우팅.

```python
from openai import OpenAI

# 당근 LLM Router는 OpenAI SDK 인터페이스 사용
client = OpenAI(base_url="https://llm-router.karrot.ai")

# model 파라미터로 원하는 모델 지정
# Router가 자동으로 해당 Provider로 라우팅
response = client.chat.completions.create(
    model="claude-4.5-sonnet",  # Anthropic으로 라우팅
    messages=[{"role": "user", "content": "안녕하세요"}]
)

response = client.chat.completions.create(
    model="gpt-5.2",  # OpenAI로 라우팅
    messages=[{"role": "user", "content": "Hello"}]
)
```

## 패턴 장점

### 1. 유연성 (Flexibility)

```python
# 동일 코드로 다양한 모델 테스트
for model in ["gpt-4", "claude-3-opus", "gemini-pro"]:
    result = agent.run(prompt, model=model)
    evaluate(result, model)
```

### 2. 테스트 용이성 (Testability)

```python
# Mock LLM으로 단위 테스트
class MockLLM(LLMInterface):
    def complete(self, prompt):
        return "Mocked response"

def test_agent_logic():
    agent = ChatAgent(llm=MockLLM())
    result = agent.chat("test")
    assert result == "Mocked response"
```

### 3. 비용 최적화 (Cost Optimization)

```python
def select_model_by_complexity(task):
    """작업 복잡도에 따라 모델 선택"""
    if task.complexity == "low":
        return "gpt-3.5-turbo"  # $0.0005/1K tokens
    elif task.complexity == "medium":
        return "gpt-4-turbo"    # $0.01/1K tokens
    else:
        return "claude-3-opus"   # $0.015/1K tokens

# 비용 효율적 모델 자동 선택
model = select_model_by_complexity(task)
result = agent.run(task.prompt, model=model)
```

### 4. 장애 격리 (Fault Isolation)

```python
async def run_with_fallback(prompt, primary_model, fallback_models):
    """Fallback 체인으로 안정성 확보"""
    models = [primary_model] + fallback_models
    
    for model in models:
        try:
            return await agent.run(prompt, model=model)
        except (RateLimitError, ServiceUnavailableError):
            logger.warning(f"{model} failed, trying next")
            continue
    
    raise AllModelsFailed("All models in fallback chain failed")

# 사용 예
result = await run_with_fallback(
    prompt="Complex analysis",
    primary_model="claude-3-opus",
    fallback_models=["gpt-4", "gemini-pro"]
)
```

### 5. A/B 테스트

```python
def ab_test_models(prompt, user_id):
    """사용자 기반 A/B 테스트"""
    if hash(user_id) % 100 < 50:
        model = "gpt-4"
        variant = "A"
    else:
        model = "claude-3-opus"
        variant = "B"
    
    result = agent.run(prompt, model=model)
    track_metrics(variant, result)
    return result
```

## 구현 가이드

### Step 1: 인터페이스 정의

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class Message(BaseModel):
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str
    tool_calls: Optional[List[Dict]] = None

class LLMInterface(ABC):
    """Model-Agnostic LLM 인터페이스"""
    
    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        **kwargs
    ) -> Message:
        """기본 채팅 완성"""
        pass
    
    @abstractmethod
    async def complete_with_tools(
        self,
        messages: List[Message],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> Message:
        """도구 호출이 가능한 채팅 완성"""
        pass
```

### Step 2: Provider 구현체 작성

```python
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic

class OpenAIProvider(LLMInterface):
    def __init__(self, model: str):
        self.client = AsyncOpenAI()
        self.model = model
    
    async def complete(self, messages: List[Message], **kwargs) -> Message:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[m.dict() for m in messages],
            **kwargs
        )
        return Message(
            role="assistant",
            content=response.choices[0].message.content
        )

class AnthropicProvider(LLMInterface):
    def __init__(self, model: str):
        self.client = AsyncAnthropic()
        self.model = model
    
    async def complete(self, messages: List[Message], **kwargs) -> Message:
        response = await self.client.messages.create(
            model=self.model,
            messages=self._convert_messages(messages),
            **kwargs
        )
        return Message(
            role="assistant",
            content=response.content[0].text
        )
```

### Step 3: Factory 패턴으로 생성

```python
class LLMFactory:
    """모델명으로 적절한 Provider 인스턴스 생성"""
    
    MODEL_MAPPING = {
        "gpt-4": ("openai", OpenAIProvider),
        "gpt-4-turbo": ("openai", OpenAIProvider),
        "gpt-3.5-turbo": ("openai", OpenAIProvider),
        "claude-3-opus": ("anthropic", AnthropicProvider),
        "claude-3-sonnet": ("anthropic", AnthropicProvider),
        "claude-3-haiku": ("anthropic", AnthropicProvider),
    }
    
    @classmethod
    def create(cls, model: str) -> LLMInterface:
        if model not in cls.MODEL_MAPPING:
            raise ValueError(f"Unknown model: {model}")
        
        _, provider_class = cls.MODEL_MAPPING[model]
        return provider_class(model=model)

# 사용
llm = LLMFactory.create("claude-3-opus")
```

### Step 4: Agent에서 사용

```python
class ReActAgent:
    """LLM-as-Parameter를 적용한 ReAct Agent"""
    
    def __init__(self, tools: List[Tool]):
        self.tools = {t.name: t for t in tools}
    
    async def run(
        self,
        prompt: str,
        model: str,  # 파라미터로 모델 받음
        max_iterations: int = 10
    ) -> str:
        llm = LLMFactory.create(model)
        messages = [Message(role="user", content=prompt)]
        
        for i in range(max_iterations):
            # Think
            response = await llm.complete_with_tools(
                messages=messages,
                tools=[t.schema for t in self.tools.values()]
            )
            
            if response.tool_calls:
                # Act
                for tool_call in response.tool_calls:
                    tool = self.tools[tool_call["name"]]
                    result = await tool.execute(tool_call["arguments"])
                    
                    # Observe
                    messages.append(Message(
                        role="tool",
                        content=result
                    ))
            else:
                return response.content
        
        return "Max iterations reached"
```

### Step 5: API 엔드포인트 노출

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class AgentRequest(BaseModel):
    prompt: str
    model: str = "claude-3-sonnet"  # 기본값
    max_iterations: int = 10

class AgentResponse(BaseModel):
    result: str
    model_used: str
    iterations: int

@app.post("/v1/agent/run")
async def run_agent(request: AgentRequest) -> AgentResponse:
    agent = ReActAgent(tools=[...])
    
    result = await agent.run(
        prompt=request.prompt,
        model=request.model,  # 클라이언트가 선택한 모델
        max_iterations=request.max_iterations
    )
    
    return AgentResponse(
        result=result,
        model_used=request.model,
        iterations=agent.iteration_count
    )
```

## Auto Mode 구현

사용자가 모델을 지정하지 않을 때 자동으로 최적 모델을 선택하는 기능.

```python
class AutoModelSelector:
    """작업 특성에 따른 자동 모델 선택"""
    
    def __init__(self):
        self.classifier = TaskClassifier()
    
    async def select(self, prompt: str, context: Dict) -> str:
        """프롬프트 분석 후 최적 모델 반환"""
        task_type = await self.classifier.classify(prompt)
        
        model_preferences = {
            "coding": "claude-3-sonnet",      # 코드 생성에 강함
            "reasoning": "gpt-4",              # 복잡한 추론
            "creative": "claude-3-opus",       # 창의적 작업
            "simple_qa": "gpt-3.5-turbo",     # 비용 효율적
            "math": "gpt-4-turbo",            # 수학 문제
        }
        
        return model_preferences.get(task_type, "claude-3-sonnet")

# API에서 Auto Mode 지원
@app.post("/v1/agent/run")
async def run_agent(request: AgentRequest) -> AgentResponse:
    if request.model == "auto":
        model = await auto_selector.select(request.prompt, {})
    else:
        model = request.model
    
    result = await agent.run(prompt=request.prompt, model=model)
    return AgentResponse(result=result, model_used=model, ...)
```

## 안티패턴

### ❌ 모델 하드코딩

```python
# Bad: 모델이 코드에 하드코딩됨
class Agent:
    def __init__(self):
        self.llm = OpenAI(model="gpt-4")
```

### ❌ 환경변수로 고정

```python
# Bad: 환경변수로 전역 설정
MODEL = os.getenv("LLM_MODEL", "gpt-4")

class Agent:
    def __init__(self):
        self.llm = OpenAI(model=MODEL)  # 여전히 런타임 변경 불가
```

### ❌ 조건문 분기 과다

```python
# Bad: 모든 모델을 조건문으로 처리
def chat(prompt, model):
    if model == "gpt-4":
        return openai_chat(prompt)
    elif model == "gpt-3.5":
        return openai_chat_35(prompt)
    elif model == "claude":
        return anthropic_chat(prompt)
    # ... 무한 확장
```

### ✅ 권장 패턴

```python
# Good: 인터페이스 + Factory
llm = LLMFactory.create(model)
result = await llm.complete(messages)
```

## 관련 패턴

- **Strategy Pattern**: LLM 선택 전략을 런타임에 교체
- **Factory Pattern**: 모델명으로 적절한 Provider 인스턴스 생성
- **Dependency Injection**: 외부에서 LLM 의존성 주입
- **Circuit Breaker**: 모델 장애 시 자동 전환

## 참고 자료

- [Cursor Cloud Agents API](https://cursor.com/docs/cloud-agent/api/endpoints)
- [LangChain Agent Types](https://python.langchain.com/docs/modules/agents/)
- [Clean Architecture - Robert C. Martin](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- [Dependency Injection Explained](https://martinfowler.com/articles/injection.html)

## 관련 문서

- [19-model-agnostic-agent-architecture.md](./19-model-agnostic-agent-architecture.md) - 전체 아키텍처 개요

