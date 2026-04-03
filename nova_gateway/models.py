"""
models.py — Pydantic request/response models for Nova-NextGen Gateway.

Author: Jordan Koch
"""

from __future__ import annotations
from typing import Optional, Any
from pydantic import BaseModel, Field
from enum import Enum


class TaskType(str, Enum):
    coding = "coding"
    swift = "swift"
    reasoning = "reasoning"
    analysis = "analysis"
    image = "image"
    vision = "vision"
    creative = "creative"
    long_context = "long_context"
    general = "general"
    auto = "auto"


class QueryRequest(BaseModel):
    query: str = Field(..., description="The prompt or query to process")
    task_type: TaskType = Field(TaskType.auto, description="Task type for routing")
    preferred_backend: Optional[str] = Field(None, description="Override backend: ollama, mlxcode, swarmui, comfyui")
    model: Optional[str] = Field(None, description="Override specific model (Ollama only)")
    session_id: Optional[str] = Field(None, description="Session ID for shared context")
    context_keys: list[str] = Field(default_factory=list, description="Context keys to inject from shared memory")
    validate_with: Optional[int] = Field(None, ge=2, le=3, description="Run through N backends for consensus")
    stream: bool = Field(False, description="Stream response (Ollama only)")
    options: dict[str, Any] = Field(default_factory=dict, description="Backend-specific options")


class QueryResponse(BaseModel):
    response: str
    backend_used: str
    model_used: Optional[str] = None
    task_type: str
    session_id: Optional[str] = None
    tokens_per_second: Optional[float] = None
    token_count: Optional[int] = None
    validated: bool = False
    consensus_score: Optional[float] = None
    fallback_used: bool = False
    error: Optional[str] = None


class ContextWriteRequest(BaseModel):
    session_id: str
    key: str
    value: str
    ttl_seconds: Optional[int] = None


class ContextReadRequest(BaseModel):
    session_id: str
    key: str


class ContextEntry(BaseModel):
    session_id: str
    key: str
    value: str
    created_at: str
    expires_at: Optional[str] = None


class BackendStatus(BaseModel):
    name: str
    available: bool
    url: str
    latency_ms: Optional[float] = None
    details: dict[str, Any] = Field(default_factory=dict)


class GatewayStatus(BaseModel):
    status: str = "running"
    version: str = "1.0.0"
    port: int
    uptime_seconds: int
    backends: list[BackendStatus]
    active_sessions: int
    total_queries: int


class ValidationResult(BaseModel):
    consensus: bool
    score: float
    responses: list[str]
    backends_used: list[str]
    recommended: str
