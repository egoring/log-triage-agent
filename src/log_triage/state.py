# 그래프 전체를 흐르는 상태 정의 — 노드는 이 상태의 일부만 갱신해 돌려준다
from __future__ import annotations

from typing import TypedDict


class TriageState(TypedDict, total=False):
    """트리아지 그래프의 공유 상태.

    raw_logs: 입력 로그 원문
    classification: classify 노드 결과 (severity/category/summary)
    analysis: root_cause 또는 digest 노드 결과
    report: 최종 마크다운 보고서 (report 노드가 코드로 조립)
    retries: classify 재시도 횟수
    error: 마지막 실패 원인 (재시도 판단용)
    """

    raw_logs: str
    classification: dict | None
    analysis: dict | None
    report: str
    retries: int
    error: str | None
