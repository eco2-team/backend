#!/usr/bin/env python3
"""LangGraph 시각화 스크립트.

현재 chat_worker의 그래프 구조를 시각화하여 PNG로 저장합니다.

Usage:
    python scripts/visualize_langgraph.py

Output:
    ~/Downloads/langgraph_chat_worker.png
"""

from pathlib import Path
from typing import Literal

from langgraph.graph import END, START, StateGraph


def create_visualization_graph():
    """시각화용 그래프 생성 (모든 노드 포함)."""

    # 간단한 상태 정의
    from typing import TypedDict

    class SimpleState(TypedDict):
        intent: str

    # Passthrough 노드 함수들
    def intent_node(state: SimpleState) -> SimpleState:
        return state

    def vision_node(state: SimpleState) -> SimpleState:
        return state

    def router_node(state: SimpleState) -> SimpleState:
        return state

    def waste_rag_node(state: SimpleState) -> SimpleState:
        return state

    def feedback_node(state: SimpleState) -> SimpleState:
        return state

    def character_node(state: SimpleState) -> SimpleState:
        return state

    def location_node(state: SimpleState) -> SimpleState:
        return state

    def web_search_node(state: SimpleState) -> SimpleState:
        return state

    def bulk_waste_node(state: SimpleState) -> SimpleState:
        return state

    def weather_node(state: SimpleState) -> SimpleState:
        return state

    def collection_point_node(state: SimpleState) -> SimpleState:
        return state

    def recyclable_price_node(state: SimpleState) -> SimpleState:
        return state

    def image_generation_node(state: SimpleState) -> SimpleState:
        return state

    def general_node(state: SimpleState) -> SimpleState:
        return state

    def aggregator_node(state: SimpleState) -> SimpleState:
        return state

    def summarize_node(state: SimpleState) -> SimpleState:
        return state

    def answer_node(state: SimpleState) -> SimpleState:
        return state

    # 라우팅 함수
    def route_after_intent(state: SimpleState) -> Literal["vision", "router"]:
        # 시각화용: 항상 router로
        return "router"

    def route_by_intent(
        state: SimpleState,
    ) -> Literal[
        "waste_rag",
        "character",
        "location",
        "web_search",
        "bulk_waste",
        "recyclable_price",
        "collection_point",
        "image_generation",
        "general",
    ]:
        intent = state.get("intent", "general")
        if intent == "waste":
            return "waste_rag"
        elif intent == "character":
            return "character"
        elif intent == "location":
            return "location"
        elif intent == "web_search":
            return "web_search"
        elif intent == "bulk_waste":
            return "bulk_waste"
        elif intent == "recyclable_price":
            return "recyclable_price"
        elif intent == "collection_point":
            return "collection_point"
        elif intent == "image_generation":
            return "image_generation"
        return "general"

    def route_after_feedback(state: SimpleState) -> Literal["aggregator"]:
        return "aggregator"

    # 그래프 생성
    graph = StateGraph(SimpleState)

    # 노드 등록
    graph.add_node("intent", intent_node)
    graph.add_node("vision", vision_node)
    graph.add_node("router", router_node)
    graph.add_node("waste_rag", waste_rag_node)
    graph.add_node("feedback", feedback_node)
    graph.add_node("character", character_node)
    graph.add_node("location", location_node)
    graph.add_node("web_search", web_search_node)
    graph.add_node("bulk_waste", bulk_waste_node)
    graph.add_node("weather", weather_node)
    graph.add_node("collection_point", collection_point_node)
    graph.add_node("recyclable_price", recyclable_price_node)
    graph.add_node("image_generation", image_generation_node)
    graph.add_node("general", general_node)
    graph.add_node("aggregator", aggregator_node)
    graph.add_node("summarize", summarize_node)
    graph.add_node("answer", answer_node)

    # 엣지 연결
    graph.set_entry_point("intent")

    # Intent → Vision or Router (조건부)
    graph.add_conditional_edges(
        "intent",
        route_after_intent,
        {
            "vision": "vision",
            "router": "router",
        },
    )

    # Vision → Router
    graph.add_edge("vision", "router")

    # Router → 각 서브에이전트 (조건부)
    graph.add_conditional_edges(
        "router",
        route_by_intent,
        {
            "waste_rag": "waste_rag",
            "character": "character",
            "location": "location",
            "web_search": "web_search",
            "bulk_waste": "bulk_waste",
            "recyclable_price": "recyclable_price",
            "collection_point": "collection_point",
            "image_generation": "image_generation",
            "general": "general",
        },
    )

    # waste_rag → feedback → aggregator
    graph.add_edge("waste_rag", "feedback")
    graph.add_conditional_edges(
        "feedback",
        route_after_feedback,
        {"aggregator": "aggregator"},
    )

    # 다른 서브에이전트 → aggregator
    for node_name in [
        "character",
        "location",
        "web_search",
        "bulk_waste",
        "weather",
        "collection_point",
        "recyclable_price",
        "image_generation",
        "general",
    ]:
        graph.add_edge(node_name, "aggregator")

    # aggregator → summarize → answer → END
    graph.add_edge("aggregator", "summarize")
    graph.add_edge("summarize", "answer")
    graph.add_edge("answer", END)

    return graph.compile()


def main():
    """메인 함수."""
    print("LangGraph 시각화 시작...")

    # 그래프 생성
    graph = create_visualization_graph()

    # 출력 경로
    output_dir = Path.home() / "Downloads"
    output_dir.mkdir(exist_ok=True)

    # 1. Mermaid 다이어그램 출력
    mermaid_code = graph.get_graph().draw_mermaid()
    print("\n=== Mermaid Diagram ===")
    print(mermaid_code)

    # Mermaid 코드 저장
    mermaid_path = output_dir / "langgraph_chat_worker.mmd"
    mermaid_path.write_text(mermaid_code)
    print(f"\nMermaid 코드 저장: {mermaid_path}")

    # 2. PNG 렌더링 (Mermaid.Ink API 사용 - 기본값)
    try:
        png_data = graph.get_graph().draw_mermaid_png()

        png_path = output_dir / "langgraph_chat_worker.png"
        png_path.write_bytes(png_data)
        print(f"PNG 이미지 저장: {png_path}")

    except Exception as e:
        print(f"PNG 렌더링 실패: {e}")
        print("Mermaid 코드를 https://mermaid.live 에서 직접 렌더링하세요.")

    print("\n완료!")


if __name__ == "__main__":
    main()
