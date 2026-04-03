# Nova-NextGen AI Gateway

A unified FastAPI gateway that routes AI queries across a local AI ecosystem — Ollama, MLXCode, SwarmUI, and ComfyUI — with smart task-based routing, a shared SQLite context bus, and cross-model consensus validation.

![Python](https://img.shields.io/badge/Python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Platform](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-silver)

---

## Overview

Instead of manually deciding which local AI to use for each task, the gateway makes that decision automatically based on what you're asking and what's currently available.

```
Your App / curl
      │
      ▼
Nova-NextGen Gateway  :34750
      │
      ├─ coding/swift  ──►  MLXCode  :37422  (Apple Neural Engine)
      ├─ reasoning     ──►  Ollama deepseek-r1:8b
      ├─ general       ──►  Ollama qwen3-coder:30b
      ├─ vision        ──►  Ollama qwen3-vl:4b
      ├─ image/art     ──►  SwarmUI  :7801  →  ComfyUI  :8188
      └─ [fallback]    ──►  first available backend
```

**Key capabilities:**
- **Auto-routing** — keyword detection maps any prompt to the right backend without configuration
- **Fallback chains** — if MLXCode has no model loaded, coding queries fall to `qwen3-coder:30b` automatically
- **Shared context bus** — SQLite-backed key/value store lets sessions share memory across calls
- **Cross-model validation** — run a query through 2-3 models and score consensus for critical outputs
- **Query analytics** — every query logged with backend, model, latency, fallback, and session
- **LaunchAgent** — auto-starts on login, zero manual management

---

## Requirements

- macOS (Apple Silicon recommended)
- Python 3.12 (not 3.13/3.14 — pydantic-core requires ≤ 3.13)
- At least one backend running: [Ollama](https://ollama.com), [MLXCode](https://github.com/kochj23/MLX-Code), [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI), or [ComfyUI](https://github.com/comfyanonymous/ComfyUI)

---

## Quick Start

```bash
git clone https://github.com/kochj23/Nova-NextGen.git
cd Nova-NextGen
bash install.sh
```

`install.sh` creates a Python 3.12 venv at `~/.nova_gateway/venv`, installs dependencies, and registers a LaunchAgent that starts the gateway on login.

Verify it's running:
```bash
curl http://localhost:34750/health
# {"status":"ok","uptime_seconds":12}
```

---

## Sending Queries

### Minimal — auto-routing
```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Write a Swift function to debounce a Combine publisher"}'
```

Response:
```json
{
  "response": "...",
  "backend_used": "mlxcode",
  "model_used": "mlx-local",
  "task_type": "swift",
  "fallback_used": false,
  "tokens_per_second": 142.3
}
```

### Explicit task type
```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain why quicksort is O(n log n) average case",
    "task_type": "reasoning"
  }'
```

### Force a specific backend and model
```bash
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "...", "preferred_backend": "ollama", "model": "deepseek-r1:8b"}'
```

### With shared context injection
```bash
# Write context
curl -X POST http://localhost:34750/api/context/write \
  -d '{"session_id": "my-session", "key": "meeting_notes", "value": "Q2 planning..."}'

# Query with context injected into prompt
curl -X POST http://localhost:34750/api/ai/query \
  -d '{
    "query": "Summarize the key action items",
    "session_id": "my-session",
    "context_keys": ["meeting_notes"]
  }'
```

### Cross-model validation (consensus)
```bash
curl -X POST http://localhost:34750/api/ai/query \
  -d '{
    "query": "Is this SQL safe from injection: SELECT * FROM users WHERE id = $input",
    "validate_with": 2
  }'
```
Returns `consensus_score` (0.0–1.0). Score ≥ 0.7 = consensus reached.

---

## Task Types

| `task_type` | Preferred Backend | Model |
|---|---|---|
| `coding` | MLXCode → Ollama | qwen3-coder:30b |
| `swift` | MLXCode → Ollama | qwen3-coder:30b |
| `reasoning` | Ollama | deepseek-r1:8b |
| `analysis` | Ollama | deepseek-r1:8b |
| `vision` | Ollama | qwen3-vl:4b |
| `image` | SwarmUI → ComfyUI | — |
| `creative` | Ollama | qwen3-coder:30b |
| `long_context` | Ollama | deepseek-v3.1:671b-cloud |
| `general` | Ollama | qwen3-coder:30b |
| `auto` | *(keyword detection)* | — |

Auto-detection keywords (examples):
- `"write code"`, `"debug"`, `"function"`, `"algorithm"` → `coding`
- `"swift"`, `"xcode"`, `"swiftui"`, `"uikit"` → `swift`
- `"why does"`, `"step by step"`, `"tradeoff"` → `reasoning`
- `"generate image"`, `"draw"`, `"render"` → `image`

---

## API Reference

### `POST /api/ai/query`

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Prompt (1–100,000 chars) |
| `task_type` | enum | `"auto"` | One of the task types above |
| `preferred_backend` | string | null | Force: `ollama`, `mlxcode`, `swarmui`, `comfyui` |
| `model` | string | null | Override Ollama model name |
| `session_id` | string | null | Session for context tracking |
| `context_keys` | string[] | `[]` | Keys to inject from shared context |
| `validate_with` | int | null | 2–3: run consensus validation |
| `stream` | bool | `false` | Streaming (not yet implemented) |
| `options` | object | `{}` | Backend-specific options (temperature, max_tokens, etc.) |

### `GET /api/ai/status`
Full gateway status: uptime, all backend health + latency, session count, total query count.

### `GET /api/ai/backends`
Quick list of each backend with `available`, `url`, `latency_ms`.

### `POST /api/ai/validate`
Same as `/api/ai/query` but always runs multi-backend consensus. Returns `ValidationResult`.

### `POST /api/context/write`
```json
{"session_id": "...", "key": "...", "value": "...", "ttl_seconds": 3600}
```

### `GET /api/context/read?session_id=…&key=…`
Read a single context entry.

### `GET /api/context/session?session_id=…`
Read all context entries for a session.

### `DELETE /api/context/session?session_id=…`
Clear all context for a session.

### `GET /api/analytics/recent?limit=20`
Last N queries from the query log.

### `GET /api/analytics/stats`
Total query count, active sessions, uptime.

---

## Swift Integration

Drop `AIService.swift` into any of your Xcode projects to call the gateway directly:

```swift
// One-line query
let result = try await AIService.shared.query(
    "Explain this Swift code",
    taskType: .swift
)
print(result.response)
print("Backend: \(result.backendUsed), \(result.tokensPerSecond ?? 0) tok/s")

// Write shared context
try await AIService.shared.writeContext(
    session: "proj-abc",
    key: "requirements",
    value: requirementsText
)

// Query with context injected
let summary = try await AIService.shared.query(
    "Generate a test plan",
    session: "proj-abc",
    contextKeys: ["requirements"]
)

// Check gateway availability
if await AIService.shared.isAvailable() {
    // gateway is running
}
```

---

## Configuration

All settings live in `config.yaml`. Changes take effect on gateway restart.

```yaml
gateway:
  port: 34750
  host: "127.0.0.1"   # loopback only — change to 0.0.0.0 for LAN access

backends:
  ollama:
    models:
      coding: "qwen3-coder:30b"   # swap in any installed model
      reasoning: "deepseek-r1:8b"

routing:
  default_backend: "ollama"
  default_model: "qwen3-coder:30b"

validation:
  consensus_threshold: 0.7   # 0.0–1.0; lower = easier consensus
```

---

## Managing the Service

```bash
# Stop
launchctl stop com.nova.gateway

# Start
launchctl start com.nova.gateway

# Disable autostart
launchctl unload ~/Library/LaunchAgents/com.nova.gateway.plist

# Re-enable autostart
launchctl load ~/Library/LaunchAgents/com.nova.gateway.plist

# View live logs
tail -f ~/.nova_gateway/gateway.log

# Manual start (dev mode with reload)
./run.sh --reload --debug
```

---

## Project Structure

```
Nova-NextGen/
├── nova_gateway/
│   ├── main.py              # FastAPI app, all endpoints
│   ├── router.py            # Task detection + backend selection
│   ├── config.py            # Config loader
│   ├── models.py            # Pydantic request/response models
│   ├── backends/
│   │   ├── base.py          # Abstract backend base class
│   │   ├── ollama.py        # Ollama integration
│   │   ├── mlxcode.py       # MLXCode integration
│   │   ├── swarmui.py       # SwarmUI integration
│   │   └── comfyui.py       # ComfyUI integration
│   ├── context/
│   │   └── store.py         # SQLite context/memory bus
│   └── validation/
│       └── consensus.py     # Cross-model consensus scoring
├── AIService.swift          # Swift client for macOS/iOS apps
├── config.yaml              # All configuration
├── requirements.txt
├── run.sh                   # Dev/manual start
└── install.sh               # One-shot setup + LaunchAgent install
```

---

## License

MIT License — Copyright © 2026 Jordan Koch. See [LICENSE](LICENSE).
