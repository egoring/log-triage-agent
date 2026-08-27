# 그래프 라우팅·재시도·보고서 조립 테스트 — 모의 LLM으로 네트워크 없이 검증한다
from __future__ import annotations

import pytest

from log_triage.graph import run_triage
from log_triage.nodes import MAX_RETRIES, parse_json_block, route_after_classify


class ScriptedLLM:
    """정해진 응답을 순서대로 돌려주는 모의 클라이언트."""

    def __init__(self, responses: list[str]) -> None:
        """돌려줄 응답 목록을 받는다."""
        self.responses = list(responses)
        self.calls: list[str] = []

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """호출 프롬프트를 기록하고 다음 응답을 꺼내 준다."""
        self.calls.append(prompt)
        return self.responses.pop(0)


CRITICAL = '{"severity": "critical", "category": "oom", "summary": "워커가 메모리 부족으로 반복 종료"}'
NORMAL = '{"severity": "normal", "category": "routine", "summary": "특이사항 없는 평시 로그"}'
CAUSE = '{"cause": "배치 작업의 메모리 누수", "evidence": ["OOM killed process 4312"], "actions": ["배치 힙 상한 설정", "누수 지점 프로파일링"]}'
HIGHLIGHTS = '{"highlights": ["배포 후 지연 정상 범위 유지"]}'


def test_critical_routes_to_root_cause():
    """critical 분류는 root_cause 경로로 가고 보고서에 원인·조치가 실린다."""
    llm = ScriptedLLM([CRITICAL, CAUSE])
    result = run_triage(llm, "OOM killed process 4312")
    assert "CRITICAL" in result["report"]
    assert "근본 원인" in result["report"]
    assert "배치 힙 상한 설정" in result["report"]
    assert len(llm.calls) == 2  # classify + root_cause, report는 LLM 미사용


def test_normal_routes_to_digest():
    """normal 분류는 digest 경로로 가며 근본 원인 절이 없다."""
    llm = ScriptedLLM([NORMAL, HIGHLIGHTS])
    result = run_triage(llm, "GET /health 200")
    assert "NORMAL" in result["report"]
    assert "참고 포인트" in result["report"]
    assert "근본 원인" not in result["report"]


def test_bad_json_retries_then_succeeds():
    """JSON 파싱 실패 1회 후 재시도로 성공한다."""
    llm = ScriptedLLM(["채점할 수 없습니다", NORMAL, HIGHLIGHTS])
    result = run_triage(llm, "GET /health 200")
    assert "NORMAL" in result["report"]
    assert len(llm.calls) == 3  # 실패 1회 + 재시도 성공 + digest


def test_retry_exhausted_produces_failure_report():
    """시도 상한 소진 시 실패 보고서로 수렴한다."""
    llm = ScriptedLLM(["잡담"] * MAX_RETRIES)
    result = run_triage(llm, "GET /health 200")
    assert "트리아지 실패" in result["report"]
    assert len(llm.calls) == MAX_RETRIES  # 총 시도 상한 (최초 포함)


def test_invalid_severity_counts_as_failure():
    """유효하지 않은 severity 값도 실패로 간주해 재시도한다."""
    llm = ScriptedLLM(['{"severity": "huge", "category": "x", "summary": "y"}', NORMAL, HIGHLIGHTS])
    result = run_triage(llm, "log")
    assert "NORMAL" in result["report"]


def test_route_function_directions():
    """분기 함수가 네 방향(critical·평시·재시도·포기)을 모두 올바르게 고른다."""
    assert route_after_classify({"classification": {"severity": "critical"}}) == "root_cause"
    assert route_after_classify({"classification": {"severity": "warning"}}) == "digest"
    assert route_after_classify({"classification": None, "retries": 1}) == "classify"
    assert route_after_classify({"classification": None, "retries": MAX_RETRIES}) == "give_up"


def test_parse_json_tolerates_code_fence():
    """코드펜스·잡담이 섞인 응답에서도 JSON을 추출한다."""
    raw = f"결과입니다.\n```json\n{NORMAL}\n```"
    assert parse_json_block(raw)["severity"] == "normal"


def test_parse_json_without_object_raises():
    """JSON 객체가 없으면 ValueError를 던진다."""
    with pytest.raises(ValueError, match="JSON"):
        parse_json_block("JSON 없음")


def test_empty_highlights_shows_placeholder():
    """하이라이트가 비면 '특이사항 없음'을 표시한다."""
    llm = ScriptedLLM([NORMAL, '{"highlights": []}'])
    result = run_triage(llm, "log")
    assert "특이사항 없음" in result["report"]
