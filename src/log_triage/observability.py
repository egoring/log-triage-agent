# Langfuse 관측 연동 (선택 기능) — 미설정이면 완전 무동작, 설정하면 노드 단위 트레이스 전송
from __future__ import annotations

import os
from datetime import datetime, timezone


def _now() -> datetime:
    """UTC 현재 시각 — Langfuse 스팬 타임스탬프용."""
    return datetime.now(timezone.utc)


class NullTracer:
    """관측 미설정 시 쓰는 무동작 트레이서 — 호출 비용이 사실상 0이다."""

    def start(self, name: str, input: dict) -> None:
        """트레이스 시작 (무동작)."""

    def span(self, name: str, output: dict, started_at: datetime, ended_at: datetime) -> None:
        """노드 스팬 기록 (무동작)."""

    def end(self, output: dict) -> None:
        """트레이스 종료 (무동작)."""


class LangfuseTracer:
    """Langfuse v2 SDK로 트레이스·스팬을 전송하는 트레이서.

    환경 변수(LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST)는
    Langfuse SDK가 직접 읽는다. end()에서 flush까지 해 단명 프로세스(CLI)에서도
    이벤트가 유실되지 않는다.
    """

    def __init__(self) -> None:
        """Langfuse 클라이언트를 만든다. SDK 미설치면 설치 안내와 함께 실패한다."""
        try:
            from langfuse import Langfuse
        except ImportError as e:
            raise RuntimeError(
                "langfuse 패키지가 없습니다. 관측 기능을 쓰려면 `pip install -e '.[obs]'`로 설치하세요."
            ) from e
        self._client = Langfuse()
        self._trace = None

    def start(self, name: str, input: dict) -> None:
        """루트 트레이스를 연다."""
        self._trace = self._client.trace(name=name, input=input)

    def span(self, name: str, output: dict, started_at: datetime, ended_at: datetime) -> None:
        """노드 하나의 실행을 스팬으로 기록한다 (이름·출력 요약·시작/종료 시각)."""
        if self._trace is not None:
            self._trace.span(name=name, output=output, start_time=started_at, end_time=ended_at)

    def end(self, output: dict) -> None:
        """트레이스에 최종 결과를 기록하고 flush한다."""
        if self._trace is not None:
            self._trace.update(output=output)
        self._client.flush()


def tracer_from_env():
    """LANGFUSE_SECRET_KEY가 있으면 LangfuseTracer, 없으면 NullTracer를 돌려준다.

    관측은 어디까지나 선택 기능 — 키가 없다고 실행이 막히면 안 된다.
    """
    if os.environ.get("LANGFUSE_SECRET_KEY"):
        return LangfuseTracer()
    return NullTracer()
