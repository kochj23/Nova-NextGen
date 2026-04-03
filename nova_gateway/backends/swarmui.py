"""
swarmui.py — SwarmUI backend integration (port 7801).

SwarmUI handles image generation. When running, it exposes a REST API.
Tasks: image, art, render, generate_image, draw, picture, photo

Author: Jordan Koch
"""

import time
import logging
import asyncio
from typing import Optional, Any
from .base import BaseBackend

logger = logging.getLogger(__name__)


class SwarmUIBackend(BaseBackend):
    name = "swarmui"

    def __init__(self, url: str = "http://localhost:7801"):
        super().__init__(url, timeout=120.0)
        self._session_id: Optional[str] = None

    async def _get_session(self) -> str:
        if self._session_id:
            return self._session_id
        r = await self._client.post(f"{self.url}/API/GetNewSession", json={}, timeout=10.0)
        r.raise_for_status()
        self._session_id = r.json().get("session_id", "")
        return self._session_id

    async def query(self, prompt: str, model: Optional[str] = None, **kwargs) -> dict[str, Any]:
        """Generate an image from a text prompt."""
        try:
            session_id = await self._get_session()
            payload = {
                "session_id": session_id,
                "prompt": prompt,
                "negativeprompt": kwargs.get("negative_prompt", ""),
                "images": kwargs.get("count", 1),
                "width": kwargs.get("width", 512),
                "height": kwargs.get("height", 512),
                "steps": kwargs.get("steps", 20),
                "cfgscale": kwargs.get("cfg_scale", 7.0),
                "model": model or "",
            }
            start = time.monotonic()
            r = await self._client.post(
                f"{self.url}/API/GenerateText2Image",
                json=payload,
                timeout=120.0
            )
            r.raise_for_status()
            data = r.json()
            elapsed = (time.monotonic() - start) * 1000

            images = data.get("images", [])
            return {
                "response": f"Image generated. URLs: {', '.join(images)}",
                "images": images,
                "model_used": model or "swarmui-default",
                "latency_ms": elapsed,
            }
        except Exception as e:
            logger.error(f"SwarmUI query failed: {e}")
            raise

    async def health_check(self) -> tuple[bool, float]:
        start = time.monotonic()
        try:
            r = await self._client.get(f"{self.url}/API/GetServerStatus", timeout=3.0)
            latency = (time.monotonic() - start) * 1000
            return r.status_code == 200, latency
        except Exception:
            return False, 0.0
