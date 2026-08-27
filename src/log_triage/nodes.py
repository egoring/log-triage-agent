# 그래프 노드 구현 — 판단(분류·분석)은 LLM이, 보고서 조립은 코드가 맡는다
from __future__ import annotations

import json
import re

MAX_RETRIES = 2          # classify 총 시도 상한 (최초 시도 포함)
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

CLASSIFY_PROMPT = """당신은 서버 로그 트리아지 담당자입니다. 아래 로그를 읽고 JSON 하나로만 답하세요.

형식: {{"severity": "critical|warning|normal", "category": "한 단어 분류", "summary": "한 문장 요약"}}

- critical: 서비스 장애·데이터 손실·에러 폭증 등 즉시 대응이 필요한 상황
- warning: 즉시 장애는 아니지만 방치하면 위험한 징후 (지연 증가, 재시도 급증 등)
- normal: 특이사항 없는 평시 로그

로그:
{logs}"""

ROOT_CAUSE_PROMPT = """당신은 시니어 SRE입니다. 아래 장애 로그의 근본 원인을 분석해 JSON 하나로만 답하세요.

형식: {{"cause": "근본 원인 한 문장", "evidence": ["근거가 된 로그 라인", ...], "actions": ["권장 조치", ...]}}

분류 요약: {summary}

로그:
{logs}"""

DIGEST_PROMPT = """아래 평시 서버 로그에서 참고할 만한 포인트만 뽑아 JSON 하나로만 답하세요.

형식: {{"highlights": ["포인트 한 문장", ...]}} (최대 3개, 없으면 빈 배열)

로그:
{logs}"""


def parse_json_block(text: str) -> dict:
    """응답에서 첫 JSON 객체를 추출한다 — 코드펜스·잡담이 섞여도 견딘다."""
    m = _JSON_RE.search(text)
    if not m:
        raise ValueError(f"응답에서 JSON을 찾지 못했습니다: {text[:120]}")
    return json.loads(m.group())


def make_nodes(client, model: str | None = None) -> dict:
    """LLM 클라이언트를 주입받아 노드 함수들을 만든다 (테스트에서 모의 클라이언트로 교체)."""

    def classify(state: dict) -> dict:
        """로그를 severity 3단계로 분류한다. 파싱 실패 시 error를 남겨 재시도 루프로 보낸다."""
        raw = client.chat(CLASSIFY_PROMPT.format(logs=state["raw_logs"]), model=model)
        try:
            data = parse_json_block(raw)
            if data.get("severity") not in ("critical", "warning", "normal"):
                raise ValueError(f"severity 값이 유효하지 않습니다: {data.get('severity')}")
        except (ValueError, json.JSONDecodeError) as e:
            return {"classification": None, "error": str(e), "retries": state.get("retries", 0) + 1}
        return {"classification": data, "error": None}

    def root_cause(state: dict) -> dict:
        """critical 경로 — 근본 원인·근거·권장 조치를 뽑는다."""
        raw = client.chat(
            ROOT_CAUSE_PROMPT.format(summary=state["classification"]["summary"], logs=state["raw_logs"]),
            model=model,
        )
        return {"analysis": parse_json_block(raw)}

    def digest(state: dict) -> dict:
        """warning·normal 경로 — 참고 포인트만 간추린다."""
        raw = client.chat(DIGEST_PROMPT.format(logs=state["raw_logs"]), model=model)
        return {"analysis": parse_json_block(raw)}

    def report(state: dict) -> dict:
        """최종 보고서를 마크다운으로 조립한다 — LLM 없이 결정적으로."""
        c = state.get("classification")
        if c is None:
            return {"report": (
                "# 트리아지 실패\n\n"
                f"분류 시도 {MAX_RETRIES}회를 모두 소진했습니다.\n"
                f"마지막 오류: {state.get('error')}\n\n로그를 직접 확인하세요."
            )}
        a = state.get("analysis") or {}
        lines = [
            f"# 로그 트리아지 보고서 — {c['severity'].upper()}",
            "",
            f"- **분류**: {c.get('category', '-')}",
            f"- **요약**: {c.get('summary', '-')}",
            "",
        ]
        if c["severity"] == "critical":
            lines += [f"## 근본 원인\n\n{a.get('cause', '-')}", "", "## 근거"]
            lines += [f"- `{ev}`" for ev in a.get("evidence", [])]
            lines += ["", "## 권장 조치"]
            lines += [f"{i}. {act}" for i, act in enumerate(a.get("actions", []), 1)]
        else:
            lines += ["## 참고 포인트"]
            hl = a.get("highlights", [])
            lines += [f"- {h}" for h in hl] if hl else ["- 특이사항 없음"]
        return {"report": "\n".join(lines)}

    return {"classify": classify, "root_cause": root_cause, "digest": digest, "report": report}


def route_after_classify(state: dict) -> str:
    """classify 결과에 따른 분기 — 성공 시 심각도별 경로, 실패 시 재시도 또는 포기."""
    c = state.get("classification")
    if c is not None:
        return "root_cause" if c["severity"] == "critical" else "digest"
    if state.get("retries", 0) < MAX_RETRIES:
        return "classify"          # 재시도 루프
    return "give_up"               # 상한 소진 -> 실패 보고서로 직행
