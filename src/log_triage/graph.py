# LangGraph 그래프 조립 — 조건 분기·재시도 루프에 노드 단위 관측(스팬)을 끼워 넣는다
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import make_nodes, route_after_classify
from .observability import NullTracer, _now, tracer_from_env
from .state import TriageState


def _traced(name: str, fn, tracer):
    """노드 함수를 감싸 실행 시간과 출력 요약을 트레이서 스팬으로 보낸다."""

    def wrapped(state: dict) -> dict:
        """원래 노드를 실행하고 시작·종료 시각과 함께 스팬을 기록한다."""
        started = _now()
        out = fn(state)
        summary = {k: v for k, v in out.items() if k != "report"}  # 본문은 크므로 요약만
        if "report" in out:
            summary["report_chars"] = len(out["report"])
        tracer.span(name, summary, started, _now())
        return out

    return wrapped


def build_graph(client, model: str | None = None, tracer=None):
    """트리아지 그래프를 컴파일해 돌려준다.

    구조: classify → (critical) root_cause → report
                   → (그 외)    digest     → report
                   → (파싱 실패) classify 재시도 → 상한 소진 시 report(실패 안내)

    tracer를 주면 노드마다 스팬이 기록된다 (기본 NullTracer — 무동작).
    """
    tracer = tracer or NullTracer()
    nodes = make_nodes(client, model=model)
    g = StateGraph(TriageState)
    for name in ("classify", "root_cause", "digest", "report"):
        g.add_node(name, _traced(name, nodes[name], tracer))
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


def run_triage(client, raw_logs: str, model: str | None = None, tracer=None) -> dict:
    """로그 원문 하나를 트리아지해 최종 상태(보고서 포함)를 돌려준다.

    tracer 미지정 시 환경 변수로 결정한다 — LANGFUSE_SECRET_KEY가 있으면
    Langfuse로 전송, 없으면 무동작.
    """
    tracer = tracer if tracer is not None else tracer_from_env()
    tracer.start("log-triage", {"raw_logs_chars": len(raw_logs)})
    graph = build_graph(client, model=model, tracer=tracer)
    result = graph.invoke({"raw_logs": raw_logs, "retries": 0})
    c = result.get("classification") or {}
    tracer.end({"severity": c.get("severity"), "retries": result.get("retries", 0)})
    return result
