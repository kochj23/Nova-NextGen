"""
openwebui.py — OpenWebUI backend (port 3000).

OpenWebUI is a feature-rich web interface for Ollama with built-in RAG,
document processing, conversation history, and model management.

Best for:
  - Document-grounded queries (RAG mode)
  - Long multi-turn conversations
  - Tasks that benefit from retrieval-augmented generation
  - Routing: task_type "document", "rag", "research"

API (OpenAI-compatible):
  POST /api/chat/completions     — primary chat endpoint
  GET  /api/models               — list available models
  GET  /api/version              — version / health check

Author: Jordan Koch
"""

import time
import logging
from typing import Optional, Any
from .base import BaseBackend

logger = logging.getLogger(__name__)


class OpenWebUIBackend(BaseBackend):
    name = "openwebui"

    def __init__(self, url: str = "http://localhost:3000", default_model: str = "qwen3:30b"):
        super().__init__(url, timeout=120.0)
        self.default_model = default_model

    async def query(self, prompt: str, model: Optional[str] = None, **kwargs) -> dict[str, Any]:
        target_model = model or self.default_model

        messages = []
        if "system" in kwargs:
            messages.append({"role": "system", "content": kwargs["system"]})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": kwargs.get("temperature", 0.7),
            "stream": False,
        }
        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        start = time.monotonic()
        try:
            r = await self._client.post(
                f"{self.url}/api/chat/completions",
                json=payload,
                timeout=120.0
            )
            r.raise_for_status()
            data = r.json()
            elapsed = (time.monotonic() - start) * 1000

            response_text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            ).strip()

            usage = data.get("usage", {})
            total_tokens = usage.get("completion_tokens", 0)
            tps = (total_tokens / (elapsed / 1000)) if elapsed > 0 and total_tokens else None

            return {
                "response": response_text,
                "model_used": f"{self.name}/{target_model}",
                "tokens_per_second": tps,
                "token_count": total_tokens,
                "latency_ms": elapsed,
            }
        except Exception as e:
            logger.error(f"OpenWebUI query failed (model={target_model}): {type(e).__name__}: {e}")
            raise

    async def list_models(self) -> list[str]:
        try:
            data = await self._get("/api/models")
            return [m.get("id", m.get("name", "")) for m in data.get("data", [])]
        except Exception:
            return []

    async def health_check(self) -> tuple[bool, float]:
        start = time.monotonic()
        try:
            r = await self._client.get(f"{self.url}/api/version", timeout=3.0)
            latency = (time.monotonic() - start) * 1000
            return r.status_code == 200, latency
        except Exception:
            pass
        # Fallback: try root
        try:
            r = await self._client.get(f"{self.url}/", timeout=3.0)
            latency = (time.monotonic() - start) * 1000
            return r.status_code < 500, latency
        except Exception:
            return False, 0.0
