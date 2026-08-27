# LLM 백엔드 2종 — OpenAI 호환 API와 Claude Code CLI(구독 인증)
from __future__ import annotations

import os
import shutil
import subprocess

import httpx

DEFAULT_TIMEOUT = 60.0


class LLMError(RuntimeError):
    """LLM 호출 실패 — 원인과 해결책을 담은 메시지로 던진다."""


class LLMClient:
    """OpenAI 호환 /chat/completions 클라이언트.

    환경 변수:
      TRIAGE_API_BASE  기본 https://api.openai.com/v1 (vLLM: http://localhost:8000/v1)
      TRIAGE_API_KEY   API 키 (로컬 서버면 아무 값)
      TRIAGE_MODEL     기본 모델명
    """

    def __init__(self, api_base: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        """인자가 없으면 TRIAGE_* 환경 변수에서 설정을 읽는다."""
        self.api_base = (api_base or os.environ.get("TRIAGE_API_BASE", "https://api.openai.com/v1")).rstrip("/")
        self.api_key = api_key or os.environ.get("TRIAGE_API_KEY", "")
        self.model = model or os.environ.get("TRIAGE_MODEL", "gpt-4o-mini")

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """단일 user 메시지로 응답 텍스트를 받는다. temperature 0 = 재현성 우선."""
        if not self.api_key and "api.openai.com" in self.api_base:
            raise LLMError(
                "TRIAGE_API_KEY가 설정되지 않았습니다. "
                "키를 넣거나 TRIAGE_API_BASE를 로컬 서버 주소로 바꾸세요."
            )
        try:
            resp = httpx.post(
                f"{self.api_base}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key or 'local'}"},
                json={
                    "model": model or self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"LLM API가 {e.response.status_code}를 반환했습니다: {e.response.text[:200]}. "
                f"TRIAGE_API_BASE({self.api_base})와 모델명({model or self.model})을 확인하세요."
            ) from e
        except httpx.HTTPError as e:
            raise LLMError(f"LLM API({self.api_base})에 연결할 수 없습니다: {e}.") from e


class ClaudeCLIClient:
    """Claude Code CLI(`claude -p`)를 백엔드로 쓰는 클라이언트.

    API 키 없이 Claude 구독(Pro/Max) 인증으로 동작한다. Claude Code 설치·로그인 필요.
    """

    def __init__(self, model: str | None = None) -> None:
        """claude 실행 파일을 찾고 기본 모델(sonnet)을 설정한다. 없으면 설치 안내와 함께 실패."""
        self.model = model or "sonnet"
        self._bin = shutil.which("claude")
        if not self._bin:
            raise LLMError(
                "claude 명령을 찾을 수 없습니다. Claude Code를 설치하고 로그인하세요: "
                "npm install -g @anthropic-ai/claude-code && claude"
            )

    def chat(self, prompt: str, model: str | None = None, temperature: float = 0.0) -> str:
        """`claude -p`를 호출해 응답을 받는다. 프롬프트는 stdin으로 전달한다 (Windows 인자 깨짐 회피)."""
        try:
            proc = subprocess.run(
                [self._bin, "-p", "--model", model or self.model],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=180,
            )
        except subprocess.TimeoutExpired as e:
            raise LLMError("claude CLI 호출이 180초를 넘어 중단됐습니다.") from e
        if proc.returncode != 0:
            raise LLMError(
                f"claude CLI가 실패했습니다 (exit {proc.returncode}): {proc.stderr.strip()[:200]}."
            )
        return proc.stdout.strip()
