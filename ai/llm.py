"""Client LLM lokal (Ollama) dengan retry & penanganan offline yang ramah."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from config import config


@dataclass
class LlmResult:
    ok: bool
    text: str = ""
    error: str = ""
    model: str = ""


class LlmUnavailable(Exception):
    """Ollama tidak berjalan / tidak dapat dihubungi."""


def _extract_json(text: str) -> dict[str, Any]:
    """Ambil blok JSON pertama dari teks model (tahan markdown ```json)."""
    text = text.strip()
    # cari blok ```json ... ```
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        # cari object { ... } utuh pertama
        s = text.find("{")
        e = text.rfind("}")
        if s != -1 and e != -1 and e > s:
            text = text[s : e + 1]
    return json.loads(text)


class LlmClient:
    """Konsumen API Ollama (chat completions)."""

    def __init__(self, model: str | None = None, host: str | None = None) -> None:
        self.model = model or config.OLLAMA_MODEL
        self.host = (host or config.OLLAMA_HOST).rstrip("/")

    def _available(self) -> bool:
        import requests

        try:
            r = requests.get(f"{self.host}/api/tags", timeout=3)
            return r.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 700,
        retries: int = 2,
    ) -> LlmResult:
        """Panggil model dan kembalikan hasil. Raise LlmUnavailable bila offline."""
        import requests

        if not self._available():
            raise LlmUnavailable(
                f"Ollama tidak berjalan di {self.host}. Jalankan `ollama serve` "
                f"& pastikan model '{self.model}' tersedia (`ollama pull {self.model}`)."
            )

        url = f"{self.host}/api/chat"
        last_err = ""
        for attempt in range(retries + 1):
            try:
                body = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_tokens},
                }
                r = requests.post(url, json=body, timeout=120)
                r.raise_for_status()
                data = r.json()
                content = data.get("message", {}).get("content", "")
                return LlmResult(ok=True, text=content, model=self.model)
            except requests.HTTPError as e:
                last_err = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
        return LlmResult(ok=False, error=last_err, model=self.model)
