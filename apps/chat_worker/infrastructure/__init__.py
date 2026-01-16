"""Chat Worker Infrastructure Layer.

Port 구현체 (Adapters) 제공.

구조:
- llm/: LLM 클라이언트 (OpenAI, Gemini) + 정책
- orchestration/: 파이프라인 오케스트레이션 (LangGraph)
- retrieval/: RAG 검색 (JSON)
- events/: 이벤트 발행 (Redis Streams)
- integrations/: 외부 서비스 연동 (Character, Location gRPC)
- interaction/: Human-in-the-Loop (입력 요청, 상태 저장)
- assets/: 정적 자산 (프롬프트, 규정 JSON)
"""
