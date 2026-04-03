"""
router.py — Smart AI routing engine for Nova-NextGen Gateway.

Routing decision order:
  1. Explicit preferred_backend in request → use it (skip detection)
  2. Explicit task_type in request → follow routing rules
  3. task_type == "auto" → keyword detection on prompt text
  4. Availability check → if preferred backend is down, use fallback
  5. Default → Ollama with qwen3-coder:30b

Keyword detection maps prompt vocabulary to task types.

Author: Jordan Koch
"""

import logging
from typing import Optional
from . import config
from .backends.base import BaseBackend

logger = logging.getLogger(__name__)

# Keyword → task_type detection. Checked in order; first match wins.
_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["generate image", "draw", "paint", "render", "dalle", "midjourney",
      "stable diffusion", "create an image", "make a picture", "artwork", "illustration"], "image"),
    (["swift", ".swift", "xcode", "swiftui", "uikit", "appkit", "ios", "macos app",
      "cocoa", "objective-c", ".m file", "@objc", "viewcontroller"], "swift"),
    (["write code", "debug", "function", "class", "struct", "algorithm",
      "implement", "refactor", "unit test", "bug", "compile", "syntax",
      "python", "javascript", "typescript", "rust", "go lang", "kotlin",
      "java ", "c++", "c#", ".py", ".js", ".ts", ".rs", ".go"], "coding"),
    (["why does", "explain why", "reason", "analyze", "think through",
      "step by step", "logic", "proof", "argument", "evaluate", "assess",
      "compare", "should i", "tradeoff", "pros and cons"], "reasoning"),
    (["what is in this image", "describe this image", "look at", "see in",
      "what do you see", "image shows", "picture of"], "vision"),
    (["write a story", "poem", "creative writing", "fiction", "narrative",
      "brainstorm", "ideas for", "marketing copy", "blog post", "essay"], "creative"),
    (["summarize this entire", "full document", "long text", "complete transcript",
      "entire conversation", "whole document"], "long_context"),
]


def detect_task_type(prompt: str) -> str:
    """Detect task type from prompt keywords. Returns 'general' if no match."""
    lower = prompt.lower()
    for keywords, task_type in _KEYWORD_RULES:
        if any(kw in lower for kw in keywords):
            return task_type
    return "general"


class Router:
    def __init__(self, backends: dict[str, BaseBackend]):
        self._backends = backends

    async def resolve(
        self,
        prompt: str,
        task_type: str = "auto",
        preferred_backend: Optional[str] = None,
        model_override: Optional[str] = None,
    ) -> tuple[BaseBackend, Optional[str], str, bool]:
        """
        Returns (backend, model, resolved_task_type, fallback_used).
        """
        # If caller forced a specific backend, honor it
        if preferred_backend and preferred_backend in self._backends:
            backend = self._backends[preferred_backend]
            available, _ = await backend.health_check()
            if available:
                return backend, model_override, task_type, False
            logger.warning(f"Router: forced backend '{preferred_backend}' is unavailable")

        # Auto-detect task type from prompt if not specified
        if task_type == "auto":
            task_type = detect_task_type(prompt)
            logger.debug(f"Router: auto-detected task_type='{task_type}'")

        # Find matching routing rule
        rule = self._find_rule(task_type)

        # Try preferred backend from rule
        if rule:
            preferred_name = rule.get("preferred", config.default_backend())
            model = model_override or rule.get("model") or rule.get("fallback_model")
            backend = self._backends.get(preferred_name)
            if backend:
                available, _ = await backend.health_check()
                if available:
                    return backend, model, task_type, False

            # Try fallback from rule
            fallback_name = rule.get("fallback")
            if fallback_name and fallback_name in self._backends:
                fb_backend = self._backends[fallback_name]
                fb_available, _ = await fb_backend.health_check()
                if fb_available:
                    fb_model = model_override or rule.get("fallback_model")
                    logger.info(f"Router: fell back from '{preferred_name}' → '{fallback_name}'")
                    return fb_backend, fb_model, task_type, True

        # Last resort: first available backend
        for name, backend in self._backends.items():
            available, _ = await backend.health_check()
            if available:
                logger.warning(f"Router: all rules exhausted, using '{name}' as last resort")
                return backend, model_override, task_type, True

        raise RuntimeError("No AI backends are currently available. Check that Ollama or MLXCode is running.")

    def _find_rule(self, task_type: str) -> Optional[dict]:
        for rule in config.routing_rules():
            if rule.get("task_type") == task_type:
                return rule
        return None

    async def all_statuses(self) -> list[dict]:
        results = []
        for name, backend in self._backends.items():
            available, latency = await backend.health_check()
            results.append({
                "name": name,
                "available": available,
                "url": backend.url,
                "latency_ms": round(latency, 1) if available else None,
            })
        return results
