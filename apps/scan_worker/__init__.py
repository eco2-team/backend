"""Scan Worker - Clean Architecture.

4-Stage Pipeline:
1. Vision: 이미지 분석 (GPT-5.2 / Gemini 3.0 Pro)
2. Rule: 배출 규정 검색 (RAG)
3. Answer: 답변 생성 (GPT-5.2-mini / Gemini 3.0 Flash)
4. Reward: 캐릭터 보상 (gRPC)
"""
