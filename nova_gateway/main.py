"""
main.py — Nova-NextGen Unified AI Gateway
Port: 34750

Endpoints:
  POST /api/ai/query          — Route a query to the best available AI backend
  GET  /api/ai/status         — Gateway + all backend health status
  GET  /api/ai/backends       — List backends and availability
  POST /api/ai/validate       — Run cross-model consensus validation
  POST /api/context/write     — Write a key/value to shared context
  GET  /api/context/read      — Read a key from shared context
  GET  /api/context/session   — Read all context for a session
  DELETE /api/context/session — Clear a session's context
  GET  /api/analytics/recent  — Recent query log
  GET  /api/analytics/stats   — Aggregate stats
  GET  /health                — Simple health check

Author: Jordan Koch
"""

import time
import uuid
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .models import (
    QueryRequest, QueryResponse, ContextWriteRequest,
    BackendStatus, GatewayStatus, ValidationResult
)
from .backends import OllamaBackend, MLXCodeBackend, SwarmUIBackend, ComfyUIBackend
from .context import ContextStore
from .router import Router
from .validation import ConsensusValidator

# ── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("nova_gateway")

# ── App globals ──────────────────────────────────────────────────────────────

_start_time = time.monotonic()
_context_store: Optional[ContextStore] = None
_router: Optional[Router] = None
_validator: Optional[ConsensusValidator] = None
_backends: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _context_store, _router, _validator, _backends

    cfg = config.load()
    logger.info(f"Nova-NextGen Gateway starting on port {config.gateway_port()}")

    # Initialise backends
    b_cfg = cfg.get("backends", {})

    _backends = {
        "ollama":   OllamaBackend(
            url=b_cfg.get("ollama", {}).get("url", "http://localhost:11434"),
            default_model=b_cfg.get("ollama", {}).get("default_model", "qwen3-coder:30b")
        ),
        "mlxcode":  MLXCodeBackend(url=b_cfg.get("mlxcode", {}).get("url", "http://localhost:37422")),
        "swarmui":  SwarmUIBackend(url=b_cfg.get("swarmui", {}).get("url", "http://localhost:7801")),
        "comfyui":  ComfyUIBackend(url=b_cfg.get("comfyui", {}).get("url", "http://localhost:8188")),
    }

    # Start context store
    _context_store = ContextStore()
    await _context_store.start()

    _router = Router(_backends)
    _validator = ConsensusValidator(_backends)

    # Log backend availability at startup
    statuses = await _router.all_statuses()
    for s in statuses:
        icon = "✓" if s["available"] else "✗"
        latency = f" ({s['latency_ms']}ms)" if s["available"] else ""
        logger.info(f"  {icon} {s['name']:10} {s['url']}{latency}")

    logger.info(f"Nova-NextGen Gateway ready — http://0.0.0.0:{config.gateway_port()}")
    yield

    # Shutdown
    logger.info("Nova-NextGen Gateway shutting down...")
    await _context_store.stop()
    for backend in _backends.values():
        await backend.close()


app = FastAPI(
    title="Nova-NextGen AI Gateway",
    description="Unified AI routing layer for Jordan Koch's local AI ecosystem.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "uptime_seconds": int(time.monotonic() - _start_time)}


@app.post("/api/ai/query", response_model=QueryResponse)
async def query(req: QueryRequest):
    session_id = req.session_id or str(uuid.uuid4())

    # Inject shared context into prompt if requested
    prompt = req.query
    if req.context_keys and _context_store:
        injections = []
        for key in req.context_keys:
            val = await _context_store.read(session_id, key)
            if val:
                injections.append(f"[Context: {key}] {val}")
        if injections:
            prompt = "\n".join(injections) + "\n\n" + prompt

    try:
        backend, model, resolved_task, fallback_used = await _router.resolve(
            prompt=prompt,
            task_type=req.task_type.value,
            preferred_backend=req.preferred_backend,
            model_override=req.model,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # Run validation if requested
    if req.validate_with and req.validate_with >= 2:
        try:
            result = await backend.query(prompt, model=model, **req.options)
            consensus_data = await _validator.validate(
                prompt=prompt,
                primary_response=result["response"],
                primary_backend=backend.name,
                n_validators=req.validate_with,
                model_override=model,
                **req.options,
            )
            response_text = consensus_data["recommended"]
            validated = True
            consensus_score = consensus_data["score"]
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Validation error: {e}")
    else:
        try:
            result = await backend.query(prompt, model=model, **req.options)
        except Exception as e:
            logger.error(f"Backend '{backend.name}' query failed: {e}")
            raise HTTPException(status_code=502, detail=f"Backend error: {e}")
        response_text = result.get("response", "")
        validated = False
        consensus_score = None

    # Log to analytics
    if _context_store:
        await _context_store.log_query(
            session_id=session_id,
            task_type=resolved_task,
            backend_used=backend.name,
            model_used=result.get("model_used"),
            prompt_length=len(prompt),
            response_length=len(response_text),
            latency_ms=result.get("latency_ms", 0),
            fallback_used=fallback_used,
            validated=validated,
        )

    return QueryResponse(
        response=response_text,
        backend_used=backend.name,
        model_used=result.get("model_used"),
        task_type=resolved_task,
        session_id=session_id,
        tokens_per_second=result.get("tokens_per_second"),
        token_count=result.get("token_count"),
        validated=validated,
        consensus_score=consensus_score,
        fallback_used=fallback_used,
    )


@app.get("/api/ai/status", response_model=GatewayStatus)
async def gateway_status():
    statuses = await _router.all_statuses()
    backend_statuses = [
        BackendStatus(
            name=s["name"],
            available=s["available"],
            url=s["url"],
            latency_ms=s.get("latency_ms"),
        )
        for s in statuses
    ]
    db_stats = await _context_store.stats() if _context_store else {}
    return GatewayStatus(
        port=config.gateway_port(),
        uptime_seconds=int(time.monotonic() - _start_time),
        backends=backend_statuses,
        active_sessions=db_stats.get("active_sessions", 0),
        total_queries=db_stats.get("total_queries", 0),
    )


@app.get("/api/ai/backends")
async def list_backends():
    return await _router.all_statuses()


@app.post("/api/ai/validate", response_model=ValidationResult)
async def validate(req: QueryRequest):
    n = req.validate_with or 2
    if n < 2:
        raise HTTPException(status_code=400, detail="validate_with must be >= 2")

    try:
        backend, model, _, _ = await _router.resolve(
            prompt=req.query,
            task_type=req.task_type.value,
            preferred_backend=req.preferred_backend,
        )
        first = await backend.query(req.query, model=model)
        result = await _validator.validate(
            prompt=req.query,
            primary_response=first["response"],
            primary_backend=backend.name,
            n_validators=n,
            model_override=model,
        )
        return ValidationResult(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Context endpoints ────────────────────────────────────────────────────────

@app.post("/api/context/write")
async def context_write(req: ContextWriteRequest):
    await _context_store.write(req.session_id, req.key, req.value, req.ttl_seconds)
    return {"status": "ok", "session_id": req.session_id, "key": req.key}


@app.get("/api/context/read")
async def context_read(session_id: str = Query(...), key: str = Query(...)):
    value = await _context_store.read(session_id, key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Key '{key}' not found in session '{session_id}'")
    return {"session_id": session_id, "key": key, "value": value}


@app.get("/api/context/session")
async def context_session(session_id: str = Query(...)):
    entries = await _context_store.read_all(session_id)
    return {"session_id": session_id, "entries": entries, "count": len(entries)}


@app.delete("/api/context/session")
async def context_clear(session_id: str = Query(...)):
    await _context_store.delete_session(session_id)
    return {"status": "cleared", "session_id": session_id}


# ── Analytics ────────────────────────────────────────────────────────────────

@app.get("/api/analytics/recent")
async def analytics_recent(limit: int = Query(20, ge=1, le=100)):
    rows = await _context_store.recent_queries(limit)
    return {"queries": rows, "count": len(rows)}


@app.get("/api/analytics/stats")
async def analytics_stats():
    stats = await _context_store.stats()
    stats["uptime_seconds"] = int(time.monotonic() - _start_time)
    return stats
