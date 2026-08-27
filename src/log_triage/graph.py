# LangGraph 그래프 조립 — 조건 분기와 재시도 루프를 하나의 StateGraph로 엮는다
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import make_nodes, route_after_classify
from .state import TriageState


def build_graph(client, model: str | None = None):
    """트리아지 그래프를 컴파일해 돌려준다.

    구조: classify → (critical) root_cause → report
                   → (그 외)    digest     → report
                   → (파싱 실패) classify 재시도 → 상한 소진 시 report(실패 안내)
    """
    nodes = make_nodes(client, model=model)
    g = StateGraph(TriageState)
    for name in ("classify", "root_cause", "digest", "report"):
        g.add_node(name, nodes[name])
    g.set_entry_point("classify")
    g.add_conditional_edges(
        "classify",
        route_after_classify,
        {"root_cause": "root_cause", "digest": "digest", "classify": "classify", "give_up": "report"},
    )
    g.add_edge("root_cause", "report")
    g.add_edge("digest", "report")
    g.add_edge("report", END)
    return g.compile()


def run_triage(client, raw_logs: str, model: str | None = None) -> dict:
    """로그 원문 하나를 트리아지해 최종 상태(보고서 포함)를 돌려준다."""
    graph = build_graph(client, model=model)
    return graph.invoke({"raw_logs": raw_logs, "retries": 0})
