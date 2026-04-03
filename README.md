# Nova-NextGen AI Gateway

> A local AI router for macOS — automatically routes queries to the right model across Ollama, MLXCode, SwarmUI, and ComfyUI, with session memory, cross-model consensus, and a Swift client drop-in.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Platform](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-000000?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## What It Is

If you run multiple local AI backends — Ollama, a local LLM app, an image generator — you probably spend time deciding which one to call for each task. Nova-NextGen removes that decision. You send one request to one endpoint, and the gateway picks the right backend based on what you're asking.

```
Your App  ──►  POST /api/ai/query
                      │
              ┌───────▼────────┐
              │  Nova-NextGen  │  :34750
              │   (Router)     │
              └───────┬────────┘
                      │
          ┌───────────┼────────────┬──────────────┐
          ▼           ▼            ▼              ▼
    MLXCode       Ollama        SwarmUI        ComfyUI
    :37422        :11434        :7801          :8188
  (Apple ANE)  (deepseek,     (image         (image
  coding/swift  qwen3, etc.)   generation)   workflows)
```

**What it does:**
- Detects the task type from your prompt (or you specify it explicitly)
- Routes to the best available backend for that task
- Falls back automatically if the preferred backend is down or has no model loaded
- Keeps a SQLite session memory store so context persists across calls
- Optionally runs queries through 2–3 backends and scores how much they agree
- Logs every query for analytics and debugging
- Runs as a macOS LaunchAgent — starts on login, no manual management

---

## Supported Backends

| Backend | Port | Best For | Notes |
|---|---|---|---|
| [Ollama](https://ollama.com) | 11434 | Reasoning, coding, general | Most flexible — runs any model |
| [MLXCode](https://github.com/kochj23/MLX-Code) | 37422 | Swift/coding, fast responses | Uses Apple Neural Engine via MLX |
| [SwarmUI](https://github.com/mcmonkeyprojects/SwarmUI) | 7801 | Image generation | Primary image backend |
| [ComfyUI](https://github.com/comfyanonymous/ComfyUI) | 8188 | Image workflows | Fallback for image generation |

You don't need all four running. The gateway health-checks each backend on startup and per request, routing around anything that's down.

---

## Requirements

- macOS (Apple Silicon recommended, Intel works)
- Python 3.12 — specifically 3.12, not 3.13/3.14 (pydantic-core's Rust bindings don't yet support 3.14)
- At least one supported backend installed and runnable

Install Python 3.12 via Homebrew if needed:
```bash
brew install python@3.12
```

---

## Installation

```bash
git clone https://github.com/kochj23/Nova-NextGen.git
cd Nova-NextGen
bash install.sh
```

`install.sh` does the following:
1. Creates a Python 3.12 virtual environment at `~/.nova_gateway/venv`
2. Installs all dependencies from `requirements.txt`
3. Generates a LaunchAgent plist at `~/Library/LaunchAgents/com.nova.gateway.plist`
4. Loads and starts the LaunchAgent

The gateway starts immediately and restarts automatically on login.

Verify it's running:
```bash
curl http://localhost:34750/health
# → {"status":"ok","uptime_seconds":4}

curl http://localhost:34750/api/ai/backends
# → lists each backend with available/unavailable and latency
```

---

## Quick Start

### Send your first query

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What is the time complexity of merge sort?"}'
```

```json
{
  "response": "Merge sort has a time complexity of O(n log n) in all cases...",
  "backend_used": "ollama",
  "model_used": "deepseek-r1:8b",
  "task_type": "reasoning",
  "session_id": "a3f91c...",
  "tokens_per_second": 38.4,
  "fallback_used": false,
  "validated": false
}
```

The gateway detected `"time complexity"` as a reasoning task and routed to `deepseek-r1:8b` automatically.

---

## Routing

### How auto-routing works

When `task_type` is `"auto"` (the default), the gateway scans the prompt for keywords and maps them to a task type. Routing rules then pick the backend.

**Keyword detection examples:**

| Keywords in prompt | Detected task | Backend |
|---|---|---|
| `swift`, `xcode`, `swiftui`, `uikit`, `appkit` | `swift` | MLXCode → Ollama |
| `write code`, `debug`, `function`, `algorithm`, `refactor` | `coding` | MLXCode → Ollama |
| `why does`, `step by step`, `tradeoff`, `explain why` | `reasoning` | Ollama deepseek-r1 |
| `analyze`, `evaluate`, `assess`, `compare` | `analysis` | Ollama deepseek-r1 |
| `generate image`, `draw`, `render`, `paint`, `artwork` | `image` | SwarmUI → ComfyUI |
| `what is in this image`, `describe this image` | `vision` | Ollama qwen3-vl |
| `write a story`, `poem`, `creative writing`, `brainstorm` | `creative` | Ollama |
| `summarize this entire`, `full document`, `long text` | `long_context` | Ollama deepseek-v3.1 |
| *(no match)* | `general` | Ollama qwen3-coder:30b |

### Explicit task type

Skip detection and route directly:

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Review this function for bugs",
    "task_type": "coding"
  }'
```

### Force a specific backend or model

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Summarize this text",
    "preferred_backend": "ollama",
    "model": "qwen3-coder:30b"
  }'
```

### Routing table

| `task_type` | Preferred Backend | Model | Fallback |
|---|---|---|---|
| `coding` | MLXCode | mlx-local | Ollama qwen3-coder:30b |
| `swift` | MLXCode | mlx-local | Ollama qwen3-coder:30b |
| `reasoning` | Ollama | deepseek-r1:8b | — |
| `analysis` | Ollama | deepseek-r1:8b | — |
| `vision` | Ollama | qwen3-vl:4b | — |
| `image` | SwarmUI | — | ComfyUI |
| `creative` | Ollama | qwen3-coder:30b | — |
| `long_context` | Ollama | deepseek-v3.1:671b-cloud | — |
| `general` | Ollama | qwen3-coder:30b | — |
| `auto` | *(keyword detection picks one above)* | | |

Fallback applies when the preferred backend is unreachable or has no model loaded. If all backends for a task type are down, the gateway returns HTTP 503.

---

## Shared Context Bus

The context store lets you persist information across calls within a session without re-sending it every time.

### Write to context

```bash
curl -X POST http://localhost:34750/api/context/write \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "project-x",
    "key": "requirements",
    "value": "The app must support offline mode, biometric auth, and dark mode.",
    "ttl_seconds": 3600
  }'
```

### Use context in a query

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Write a test plan",
    "session_id": "project-x",
    "context_keys": ["requirements"]
  }'
```

The gateway prepends `[Context: requirements] The app must support...` to the prompt before sending it to the backend. The model sees the context; you don't have to re-send it.

### Read context

```bash
# Read a single key
curl "http://localhost:34750/api/context/read?session_id=project-x&key=requirements"

# Read all keys in a session
curl "http://localhost:34750/api/context/session?session_id=project-x"
```

### Clear a session

```bash
curl -X DELETE "http://localhost:34750/api/context/session?session_id=project-x"
```

**Limits:** key ≤ 256 chars, value ≤ 50,000 chars, TTL 1–86,400 seconds (default 1 hour). Expired entries are cleaned up automatically every 5 minutes.

---

## Cross-Model Consensus

For critical outputs — security review, important decisions — run the query through multiple backends and score how much they agree.

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Is this regular expression safe from ReDoS: ^(a+)+$",
    "validate_with": 2
  }'
```

```json
{
  "response": "Yes, this pattern is vulnerable to ReDoS...",
  "validated": true,
  "consensus_score": 0.84,
  "backend_used": "ollama",
  "fallback_used": false
}
```

`consensus_score` is 0.0–1.0 (cosine similarity across responses). A score ≥ 0.7 means the models substantially agree. Below that, the gateway logs a discrepancy warning. The response returned is the longest (most detailed) answer from the set.

---

## API Reference

### `POST /api/ai/query`

Routes a query to a backend and returns the response.

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | The prompt. 1–100,000 characters. |
| `task_type` | string | `"auto"` | `coding`, `swift`, `reasoning`, `analysis`, `image`, `vision`, `creative`, `long_context`, `general`, `auto` |
| `preferred_backend` | string | null | Force a backend: `ollama`, `mlxcode`, `swarmui`, `comfyui` |
| `model` | string | null | Override the Ollama model name (e.g. `"deepseek-r1:8b"`) |
| `session_id` | string | null | Session identifier for context tracking and analytics |
| `context_keys` | string[] | `[]` | Keys from the context store to inject into this prompt |
| `validate_with` | int | null | 2 or 3: run through multiple backends and score consensus |
| `stream` | bool | `false` | Not yet implemented |
| `options` | object | `{}` | Backend-specific overrides: `temperature`, `max_tokens`, `system`, `negative_prompt`, `width`, `height`, `steps` |

**Response:**

| Field | Type | Description |
|---|---|---|
| `response` | string | The model's output |
| `backend_used` | string | Which backend handled the request |
| `model_used` | string | Which model within that backend |
| `task_type` | string | Resolved task type (useful when `"auto"` was used) |
| `session_id` | string | Session ID (auto-generated if not provided) |
| `tokens_per_second` | float | Generation speed (Ollama and MLXCode only) |
| `token_count` | int | Token count (Ollama and MLXCode only) |
| `validated` | bool | Whether consensus validation was run |
| `consensus_score` | float | Agreement score if `validated` is true |
| `fallback_used` | bool | Whether routing fell back to a secondary backend |
| `error` | string | Error message if the request partially failed |

---

### `GET /api/ai/status`

Full gateway status snapshot.

```json
{
  "status": "running",
  "version": "1.0.0",
  "port": 34750,
  "uptime_seconds": 3842,
  "backends": [
    {"name": "ollama", "available": true, "url": "http://localhost:11434", "latency_ms": 8.1},
    {"name": "mlxcode", "available": false, "url": "http://localhost:37422", "latency_ms": null},
    {"name": "swarmui", "available": false, "url": "http://localhost:7801", "latency_ms": null},
    {"name": "comfyui", "available": true, "url": "http://localhost:8188", "latency_ms": 5.2}
  ],
  "active_sessions": 3,
  "total_queries": 142
}
```

---

### `GET /api/ai/backends`

Quick backend availability list. Same backend array as above, without the gateway metadata.

---

### `POST /api/ai/validate`

Force consensus validation. Same request body as `/api/ai/query` but always runs multi-backend comparison regardless of `validate_with`.

**Response:**

```json
{
  "consensus": true,
  "score": 0.81,
  "responses": ["Response from backend 1...", "Response from backend 2..."],
  "backends_used": ["ollama", "mlxcode"],
  "recommended": "The longer, more detailed response..."
}
```

---

### `POST /api/context/write`

| Field | Type | Required | Description |
|---|---|---|---|
| `session_id` | string | yes | Session identifier. Max 128 chars. |
| `key` | string | yes | Context key. Max 256 chars. |
| `value` | string | yes | Context value. Max 50,000 chars. |
| `ttl_seconds` | int | no | Expiry in seconds. 1–86400. Default: 3600. |

---

### `GET /api/context/read`

Query params: `session_id`, `key`. Returns `{"session_id", "key", "value"}` or 404 if not found or expired.

---

### `GET /api/context/session`

Query param: `session_id`. Returns all non-expired entries: `{"session_id", "entries": {key: value, ...}, "count"}`.

---

### `DELETE /api/context/session`

Query param: `session_id`. Deletes all context entries and session record.

---

### `GET /api/analytics/recent`

Query param: `limit` (1–100, default 20). Returns the most recent queries from the log.

```json
{
  "queries": [
    {
      "id": 142,
      "session_id": "abc123",
      "task_type": "reasoning",
      "backend_used": "ollama",
      "model_used": "deepseek-r1:8b",
      "prompt_length": 87,
      "response_length": 412,
      "latency_ms": 4821.3,
      "fallback_used": 0,
      "validated": 0,
      "created_at": "2026-04-03T21:14:02+00:00"
    }
  ],
  "count": 1
}
```

---

### `GET /api/analytics/stats`

```json
{
  "active_sessions": 3,
  "total_queries": 142,
  "uptime_seconds": 3842
}
```

---

### `GET /health`

Simple liveness check. Returns `{"status": "ok", "uptime_seconds": N}`.

---

## Swift Integration

`AIService.swift` is a drop-in Swift client. Copy it into any Xcode project to call the gateway from your macOS or iOS app.

```swift
import Foundation
// (paste AIService.swift into your project — no SPM dependency needed)

// Basic query
let result = try await AIService.shared.query(
    "Write a Swift extension to validate email addresses",
    taskType: .swift
)
print(result.response)
// "Backend: mlxcode, 138.4 tok/s"
print("Backend: \(result.backendUsed), \(result.tokensPerSecond ?? 0) tok/s")

// Force a specific backend
let analysis = try await AIService.shared.query(
    "What are the security implications of this code?",
    taskType: .analysis,
    backend: "ollama",
    model: "deepseek-r1:8b"
)

// Write shared context, then use it
try await AIService.shared.writeContext(
    session: "myapp-session",
    key: "codebase_summary",
    value: "Swift 6, SwiftUI, async/await throughout, no third-party dependencies"
)

let advice = try await AIService.shared.query(
    "What testing strategy would work best?",
    session: "myapp-session",
    contextKeys: ["codebase_summary"]
)

// Check if gateway is up before using it
guard await AIService.shared.isAvailable() else {
    print("Gateway not running — start it with: cd Nova-NextGen && ./run.sh")
    return
}

// Full status
let status = try await AIService.shared.status()
let available = status.backends.filter { $0.available }.map { $0.name }
print("Available backends: \(available.joined(separator: ", "))")
```

**Error handling:**

```swift
do {
    let result = try await AIService.shared.query("...")
} catch AIServiceError.gatewayUnavailable {
    // Gateway not running — start it with launchctl start com.nova.gateway
} catch AIServiceError.backendError(let message) {
    // A backend returned an error
} catch AIServiceError.networkError(let underlying) {
    // Network issue
}
```

---

## Configuration

Edit `config.yaml` in the project root. Restart the gateway after changes:

```bash
launchctl stop com.nova.gateway && launchctl start com.nova.gateway
```

### Full config reference

```yaml
gateway:
  port: 34750
  host: "127.0.0.1"     # Change to "0.0.0.0" for LAN access (read SECURITY.md first)
  log_level: "INFO"      # DEBUG, INFO, WARNING, ERROR
  db_path: "~/.nova_gateway/context.db"

backends:
  ollama:
    url: "http://localhost:11434"
    enabled: true
    default_model: "deepseek-r1:8b"
    models:
      reasoning: "deepseek-r1:8b"
      coding: "qwen3-coder:30b"
      general: "qwen3-coder:30b"
      vision: "qwen3-vl:4b"
      creative: "qwen3-coder:30b"
      swift: "qwen3-coder:30b"
      analysis: "deepseek-r1:8b"
      long_context: "deepseek-v3.1:671b-cloud"

  mlxcode:
    url: "http://localhost:37422"
    enabled: true

  swarmui:
    url: "http://localhost:7801"
    enabled: true

  comfyui:
    url: "http://localhost:8188"
    enabled: true

routing:
  default_backend: "ollama"
  default_model: "qwen3-coder:30b"

context:
  ttl_seconds: 3600           # Default TTL for context entries
  cleanup_interval_seconds: 300

validation:
  enabled: true
  consensus_threshold: 0.7    # 0.0–1.0. Lower = easier to reach consensus.
  max_validators: 2
  timeout_seconds: 30
```

### Adding a new Ollama model

Install the model in Ollama:
```bash
ollama pull llama3.2:3b
```

Then update `config.yaml` to route a task type to it:
```yaml
backends:
  ollama:
    models:
      general: "llama3.2:3b"
```

Restart the gateway. No code changes needed.

---

## Managing the Service

```bash
# Check status
launchctl list | grep com.nova.gateway

# Stop
launchctl stop com.nova.gateway

# Start
launchctl start com.nova.gateway

# Disable autostart (survives reboot)
launchctl unload ~/Library/LaunchAgents/com.nova.gateway.plist

# Re-enable autostart
launchctl load ~/Library/LaunchAgents/com.nova.gateway.plist

# View live logs
tail -f ~/.nova_gateway/gateway.log

# View error log
tail -f ~/.nova_gateway/gateway.error.log

# Manual start with hot reload (development)
./run.sh --reload

# Manual start with debug logging
./run.sh --debug
```

---

## Troubleshooting

### Gateway won't start

Check the error log:
```bash
cat ~/.nova_gateway/gateway.error.log
```

Common causes:
- **Port already in use** — something else is on 34750. Change `port` in `config.yaml`.
- **Wrong Python version** — the venv must use Python 3.12. Run `bash install.sh` again.
- **Volume not mounted** — if the project lives on an external drive, it must be mounted before the LaunchAgent runs. The venv is stored at `~/.nova_gateway/venv` (on the boot drive) to avoid this.

### All backends show unavailable

```bash
# Check if Ollama is running
/usr/local/bin/ollama list

# Start Ollama
/usr/local/bin/ollama serve &

# Check MLXCode
curl http://localhost:37422/api/status
```

### Ollama queries time out

Large models (30B+) can take 30–60 seconds to load on first call. The gateway timeout is 300 seconds. Subsequent calls to the same model are faster once it's in memory.

### MLXCode shows as unavailable even though it's open

MLXCode's health check verifies that a model is loaded (`modelLoaded: true`). Open MLXCode and load a model first, then it will show as available.

### Context entries returning 404

Entries expire after their TTL (default 1 hour). Write again with a longer `ttl_seconds`, or set `ttl_seconds: null` for no expiry (not recommended for large values).

---

## Project Structure

```
Nova-NextGen/
├── nova_gateway/
│   ├── main.py              # FastAPI app — all routes and lifecycle
│   ├── router.py            # Task type detection and backend selection
│   ├── config.py            # config.yaml loader with typed accessors
│   ├── models.py            # Pydantic request/response models
│   ├── backends/
│   │   ├── base.py          # Abstract base class all backends implement
│   │   ├── ollama.py        # Ollama /api/generate integration
│   │   ├── mlxcode.py       # MLXCode /api/chat integration
│   │   ├── swarmui.py       # SwarmUI GenerateText2Image integration
│   │   └── comfyui.py       # ComfyUI /prompt workflow integration
│   ├── context/
│   │   └── store.py         # aiosqlite-backed session memory bus
│   └── validation/
│       └── consensus.py     # Cosine similarity cross-model scoring
├── AIService.swift          # Drop-in Swift client for Xcode projects
├── config.yaml              # All runtime configuration
├── requirements.txt         # Pinned Python dependencies
├── run.sh                   # Manual start / dev mode
├── install.sh               # One-shot setup + LaunchAgent registration
├── SECURITY.md              # Threat model and hardening guide
└── LICENSE                  # MIT
```

---

## Security

The gateway is designed as a **localhost-only service**:

- Binds to `127.0.0.1` by default — not reachable from other machines
- CORS restricted to `http://localhost` and `http://127.0.0.1` origins
- All SQL queries use parameterized statements — no injection risk
- Input validated by Pydantic on every request
- No credentials stored anywhere in the project
- No outbound network calls (all backends are local)

See [SECURITY.md](SECURITY.md) for the full threat model, a hardening guide for LAN deployment, and the vulnerability disclosure process.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.6 | HTTP framework |
| `uvicorn[standard]` | 0.34.0 | ASGI server |
| `httpx` | 0.28.1 | Async HTTP client for backend calls |
| `aiosqlite` | 0.20.0 | Async SQLite for context store |
| `pyyaml` | 6.0.2 | Config file parsing |
| `pydantic` | 2.10.4 | Request/response validation |
| `python-multipart` | 0.0.20 | Form data support |
| `aiofiles` | 24.1.0 | Async file operations |

All versions are pinned. Dependabot is configured to alert on vulnerability disclosures weekly.

---

## License

MIT License — Copyright © 2026 Jordan Koch.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND**, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
