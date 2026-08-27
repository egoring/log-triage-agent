# CLI 진입점 — 로그 파일 하나를 트리아지해 보고서를 stdout에 쓴다
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .graph import run_triage
from .llm import ClaudeCLIClient, LLMClient, LLMError


def main() -> None:
    """로그 파일을 읽어 선택한 백엔드로 트리아지를 실행한다."""
    parser = argparse.ArgumentParser(description="서버 로그를 LangGraph 에이전트로 트리아지한다.")
    parser.add_argument("logfile", help="분석할 로그 파일 경로")
    parser.add_argument(
        "--backend",
        choices=["api", "claude-cli"],
        default="api",
        help="api=OpenAI 호환(TRIAGE_* 환경 변수) / claude-cli=Claude 구독으로 `claude -p` 호출",
    )
    parser.add_argument("--model", default=None, help="모델명 (백엔드별 기본값 있음)")
    args = parser.parse_args()

    path = Path(args.logfile)
    if not path.exists():
        print(f"[중단] 로그 파일이 없습니다: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        client = ClaudeCLIClient(model=args.model) if args.backend == "claude-cli" else LLMClient(model=args.model)
        result = run_triage(client, path.read_text(encoding="utf-8"), model=args.model)
    except LLMError as e:
        print(f"[중단] {e}", file=sys.stderr)
        sys.exit(1)

    print(result["report"])


if __name__ == "__main__":
    main()
