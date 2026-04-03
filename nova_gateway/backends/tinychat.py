"""
tinychat.py — TinyChat backend (port 8000).

TinyChat is a lightweight OpenAI-compatible proxy to local Ollama models,
running as a Docker container. It is the fastest backend for simple tasks.

TinyChat API (custom SSE format):
  POST /api/chat/stream  — SSE stream, payload: {"messages": [...], "model"?: "..."}
  GET  /api/config       — lists available_models and default_model
  GET  /api/health       — liveness check
  GET  /api/version      — version info

Note: TinyChat's Docker container connects to its own Ollama instance.
      To add models, exec into the container: docker exec -it tinychat ollama pull <model>
      Or configure OLLAMA_HOST in the container to point to host.docker.internal:11434

Author: Jordan Koch
"""

import time
import json
import logging
from typing import Optional, Any
from .base import BaseBackend

logger = logging.getLogger(__name__)


class TinyChatBackend(BaseBackend):
    name = "tinychat"

    def __init__(self, url: str = "http://localhost:8000", default_model: str = "qwen3:30b"):
        super().__init__(url, timeout=60.0)
        self.default_model = default_model
        self._available_models: list[str] = []

    async def _get_available_model(self) -> str:
        """Return the best available model from TinyChat's config."""
        if not self._available_models:
            try:
                data = await self._get("/api/config")
                self._available_models = data.get("available_models", [])
            except Exception:
                pass

        # Preference order
        preferred = [self.default_model, "qwen3:30b", "qwen3:8b", "qwen3-vl:4b", "mistral:latest"]
        for p in preferred:
            if p in self._available_models:
                return p
        # Return whatever is first available
        return self._available_models[0] if self._available_models else self.default_model

    async def query(self, prompt: str, model: Optional[str] = None, **kwargs) -> dict[str, Any]:
        target_model = model or await self._get_available_model()

        messages = []
        if "system" in kwargs:
            messages.append({"role": "system", "content": kwargs["system"]})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "messages": messages,
            "model": target_model,
        }
        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]

        start = time.monotonic()
        try:
            r = await self._client.post(
                f"{self.url}/api/chat/stream",
                json=payload,
                timeout=60.0
            )
            r.raise_for_status()
            elapsed = (time.monotonic() - start) * 1000

            # Parse SSE lines: "data: <json>\n"
            response_text = ""
            error_msg = None
            for line in r.text.splitlines():
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if not raw or raw == "[DONE]":
                    continue
                try:
                    chunk = json.loads(raw)
                    # Check for error
                    if "error" in chunk:
                        err = chunk["error"]
                        if isinstance(err, str):
                            try:
                                err = json.loads(err)
                            except Exception:
                                pass
                        if isinstance(err, dict):
                            error_msg = err.get("error", {}).get("message", str(err))
                        else:
                            error_msg = str(err)
                        break
                    # Extract delta content
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        response_text += content
                    # Some TinyChat versions put content directly
                    if not content and "content" in chunk:
                        response_text += chunk["content"]
                except json.JSONDecodeError:
                    pass

            if error_msg:
                logger.error(f"TinyChat model error (model={target_model}): {error_msg}")
                raise RuntimeError(f"TinyChat: {error_msg}")

            return {
                "response": response_text.strip(),
                "model_used": target_model,
                "latency_ms": elapsed,
            }
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"TinyChat query failed (model={target_model}): {type(e).__name__}: {e}")
            raise

    async def health_check(self) -> tuple[bool, float]:
        """Health check: verify the HTTP service is up and at least one model is configured."""
        start = time.monotonic()
        try:
            r = await self._client.get(f"{self.url}/api/health", timeout=3.0)
            latency = (time.monotonic() - start) * 1000
            if r.status_code == 200:
                # Cache available models while we're here
                try:
                    cfg = await self._get("/api/config")
                    self._available_models = cfg.get("available_models", [])
                except Exception:
                    pass
                return True, latency
        except Exception:
            pass
        # Fallback to root
        try:
            r = await self._client.get(f"{self.url}/", timeout=3.0)
            latency = (time.monotonic() - start) * 1000
            return r.status_code < 500, latency
        except Exception:
            return False, 0.0
