# Nova-NextGen AI Gateway

> A local AI intent router for macOS — automatically routes queries to the right model across seven backends: TinyChat, MLXCode, MLX Chat, OpenWebUI, Ollama, SwarmUI, and ComfyUI. One endpoint. Zero manual model selection.

![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![Version](https://img.shields.io/badge/Version-2.0.0-orange)
![Platform](https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-000000?logo=apple&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

---

## What It Is

Nova-NextGen is a local AI gateway that sits in front of your entire AI stack and makes routing decisions for you. You send one request, describe what you need, and the gateway picks the right backend — based on the task, what's currently available, and each engine's unique strengths.

It also integrates cleanly with **OpenRouter/DeepSeek V3** for cloud conversations, while keeping all compute work local.

```
Your App / Nova / curl
          │
          ▼
  Nova-NextGen :34750
  (Intent Router)
          │
          ├─ quick / classify ──────────► TinyChat   :8000  (qwen3:4b — fastest)
          │
          ├─ coding / swift ───────────► MLXCode    :37422 (Apple Neural Engine)
          │                                  │
          │                                  └─ fallback ──► MLX Chat :5000
          │
          ├─ general / creative / summarize ► MLX Chat  :5000 (Apple ANE fast)
          │                                      │
          │                                      └─ fallback ──► Ollama :11434
          │
          ├─ document / research ──────► OpenWebUI  :3000  (RAG-capable)
          │                                  │
          │                                  └─ fallback ──► Ollama :11434
          │
          ├─ reasoning / analysis ─────► Ollama     :11434 (deepseek-r1:8b)
          │
          ├─ vision ───────────────────► Ollama     :11434 (qwen3-vl:4b)
          │
          ├─ image ────────────────────► SwarmUI    :7801
          │                                  │
          │                                  └─ fallback ──► ComfyUI :8188
          │
          └─ long_context ─────────────► Ollama     :11434 (deepseek-v3.1-cloud)
```

---

## Why Seven Backends?

Each engine has a distinct strength. Routing to the right one matters:

| Backend | Port | Strength | Best Task Types |
|---|---|---|---|
| **TinyChat** | 8000 | Fastest round-trip, minimal overhead | `quick`, `classify`, `format` |
| **MLXCode** | 37422 | Apple Neural Engine, Swift/coding specialist | `coding`, `swift`, `debug` |
| **MLX Chat** | 5000 | Apple Neural Engine, fast general inference | `general`, `creative`, `summarize` |
| **OpenWebUI** | 3000 | RAG, document grounding, conversation history | `document`, `research` |
| **Ollama** | 11434 | Best reasoning model (deepseek-r1), vision (qwen3-vl), largest model variety | `reasoning`, `analysis`, `vision`, `long_context` |
| **SwarmUI** | 7801 | Full-featured image generation UI | `image` |
| **ComfyUI** | 8188 | Node-based image workflows | `image` (fallback) |

**OpenRouter/DeepSeek V3** is used by Nova for conversations — it's not a local backend but integrates through `nova_intent_router.py` (see [Nova Integration](#nova-integration)).

---

## Requirements

- macOS (Apple Silicon recommended, Intel works)
- Python 3.12 — not 3.13/3.14 (pydantic-core Rust bindings require ≤ 3.13)
- At least one local backend running

Install Python 3.12 if needed:
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

`install.sh`:
1. Creates a Python 3.12 venv at `~/.nova_gateway/venv`
2. Installs all dependencies
3. Generates and loads a LaunchAgent (`com.nova.gateway.plist`)

The gateway starts immediately and auto-starts on login.

```bash
curl http://localhost:34750/health
# → {"status":"ok","uptime_seconds":3,"version":"2.0.0"}

curl http://localhost:34750/api/ai/backends
# → lists all 7 backends with available/unavailable and latency
```

---

## Quick Start

### Auto-routing — just ask

```bash
curl -X POST http://localhost:34750/api/ai/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Write a Swift function that debounces a Combine publisher"}'
```

```json
{
  "response": "import Combine\n\nextension Publisher {\n    func debounce...",
  "backend_used": "mlxcode",
  "model_used": "mlx-local",
  "task_type": "swift",
  "tokens_per_second": 142.3,
  "fallback_used": false
}
```

The gateway detected `"swift"` → `"Combine"` → routed to MLXCode on the Apple Neural Engine automatically.

### Explicit task type

```bash
# Fast classification (TinyChat)
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "Is this error recoverable: SIGKILL", "task_type": "quick"}'

# Document-grounded query (OpenWebUI RAG)
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "What does section 4.2 say?", "task_type": "document"}'

# Deep reasoning (Ollama deepseek-r1)
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "Analyze the security implications of this auth flow", "task_type": "reasoning"}'

# General text (MLX Chat — Apple Silicon fast)
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "Summarize these release notes", "task_type": "summarize"}'

# Image generation (SwarmUI)
curl -X POST http://localhost:34750/api/ai/query \
  -d '{"query": "A fox sitting in snow at dusk, cinematic lighting", "task_type": "image"}'
```

---

## Task Types

### Routing table

| `task_type` | Primary Backend | Model | Fallback |
|---|---|---|---|
| `quick` | TinyChat | qwen3:4b | Ollama |
| `coding` | MLXCode | mlx-local | MLX Chat → Ollama |
| `swift` | MLXCode | mlx-local | Ollama qwen3-coder:30b |
| `general` | MLX Chat | Qwen2.5-7B (MLX) | Ollama qwen3-coder:30b |
| `creative` | MLX Chat | Qwen2.5-7B (MLX) | Ollama qwen3-coder:30b |
| `summarize` | MLX Chat | Qwen2.5-7B (MLX) | Ollama qwen3-coder:30b |
| `document` | OpenWebUI | qwen3:30b | Ollama |
| `research` | OpenWebUI | qwen3:30b | Ollama deepseek-r1:8b |
| `reasoning` | Ollama | deepseek-r1:8b | — |
| `analysis` | Ollama | deepseek-r1:8b | — |
| `vision` | Ollama | qwen3-vl:4b | — |
| `image` | SwarmUI | — | ComfyUI |
| `long_context` | Ollama | deepseek-v3.1:671b-cloud | — |
| `auto` | *(keyword detection)* | | |

### Keyword auto-detection

When `task_type` is `"auto"` (the default), the gateway scans your prompt:

| Keywords | → task_type |
|---|---|
| `"yes or no"`, `"classify"`, `"tag this"`, `"one word answer"` | `quick` |
| `"swift"`, `"swiftui"`, `"xcode"`, `"uikit"`, `"appkit"` | `swift` |
| `"write code"`, `"debug"`, `"function"`, `"algorithm"`, `".py"`, `".rs"` | `coding` |
| `"in this document"`, `"based on the file"`, `"this pdf"` | `document` |
| `"research"`, `"find information about"`, `"background on"` | `research` |
| `"why does"`, `"explain why"`, `"step by step"`, `"tradeoffs"` | `reasoning` |
| `"analyze"`, `"root cause"`, `"patterns"`, `"diagnosis"` | `analysis` |
| `"generate image"`, `"draw me"`, `"paint"`, `"render a"` | `image` |
| `"what is in this image"`, `"describe this photo"` | `vision` |
| `"summarize"`, `"tldr"`, `"key points"`, `"main takeaways"` | `summarize` |
| `"write a story"`, `"poem"`, `"brainstorm"`, `"creative writing"` | `creative` |
| `"full document"`, `"entire transcript"`, `"complete codebase"` | `long_context` |
| *(no match)* | `general` |

---

## API Reference

### `POST /api/ai/query`

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Prompt, 1–100,000 chars |
| `task_type` | string | `"auto"` | `quick`, `coding`, `swift`, `general`, `creative`, `summarize`, `document`, `research`, `reasoning`, `analysis`, `vision`, `image`, `long_context`, `auto` |
| `preferred_backend` | string | null | Force: `tinychat`, `mlxcode`, `mlxchat`, `openwebui`, `ollama`, `swarmui`, `comfyui` |
| `model` | string | null | Override model name (backend-specific) |
| `session_id` | string | null | Session for context tracking |
| `context_keys` | string[] | `[]` | Keys to inject from shared context bus |
| `validate_with` | int | null | 2–3: run consensus validation across backends |
| `stream` | bool | `false` | Streaming (Ollama only) |
| `options` | object | `{}` | Backend options: `temperature`, `max_tokens`, `system`, `negative_prompt`, `width`, `height`, `steps` |

**Response:**

| Field | Type | Description |
|---|---|---|
| `response` | string | Model output |
| `backend_used` | string | Backend that handled the request |
| `model_used` | string | Specific model within that backend |
| `task_type` | string | Resolved task type (useful when `"auto"`) |
| `session_id` | string | Session ID |
| `tokens_per_second` | float | Generation speed (TinyChat, MLXChat, MLXCode, Ollama) |
| `token_count` | int | Output token count |
| `validated` | bool | Whether consensus validation ran |
| `consensus_score` | float | Agreement score (0.0–1.0) if validated |
| `fallback_used` | bool | Whether routing fell back to a secondary backend |

---

### `GET /api/ai/status`

Full gateway snapshot: uptime, version, all backend health + latency, session count, total queries.

```json
{
  "status": "running",
  "version": "2.0.0",
  "port": 34750,
  "uptime_seconds": 3842,
  "backends": [
    {"name": "tinychat",  "available": true,  "url": "http://localhost:8000",  "latency_ms": 2.1},
    {"name": "mlxcode",   "available": true,  "url": "http://localhost:37422", "latency_ms": 4.8},
    {"name": "mlxchat",   "available": true,  "url": "http://localhost:5000",  "latency_ms": 3.2},
    {"name": "openwebui", "available": true,  "url": "http://localhost:3000",  "latency_ms": 8.4},
    {"name": "ollama",    "available": true,  "url": "http://localhost:11434", "latency_ms": 9.1},
    {"name": "swarmui",   "available": false, "url": "http://localhost:7801",  "latency_ms": null},
    {"name": "comfyui",   "available": true,  "url": "http://localhost:8188",  "latency_ms": 5.3}
  ],
  "active_sessions": 2,
  "total_queries": 341
}
```

---

### `GET /api/ai/backends`

Same backend array as above, without gateway metadata.

---

### `POST /api/ai/validate`

Force cross-model consensus. Same request body as `/api/ai/query`. Always runs through multiple backends.

```json
{
  "consensus": true,
  "score": 0.83,
  "responses": ["Response from backend 1...", "Response from backend 2..."],
  "backends_used": ["ollama", "mlxchat"],
  "recommended": "The longer, more complete response..."
}
```

---

### Context Bus

The context bus stores key-value pairs per session in SQLite. Inject stored context automatically into any query.

**Write:**
```bash
curl -X POST http://localhost:34750/api/context/write \
  -H "Content-Type: application/json" \
  -d '{"session_id": "s1", "key": "project_goal", "value": "Build a HomeKit dashboard", "ttl_seconds": 3600}'
```

**Read:**
```bash
curl "http://localhost:34750/api/context/read?session_id=s1&key=project_goal"
```

**Read all:**
```bash
curl "http://localhost:34750/api/context/session?session_id=s1"
```

**Clear:**
```bash
curl -X DELETE "http://localhost:34750/api/context/session?session_id=s1"
```

**Inject into a query:**
```bash
curl -X POST http://localhost:34750/api/ai/query \
  -d '{
    "query": "What Swift frameworks should I use?",
    "session_id": "s1",
    "context_keys": ["project_goal"]
  }'
```
The gateway prepends `[Context: project_goal] Build a HomeKit dashboard` to the prompt automatically.

**Limits:** key ≤ 256 chars, value ≤ 50,000 chars, TTL 1–86,400s. Expired entries cleaned every 5 min.

---

### Analytics

```bash
# Last 20 queries with backend, model, latency, fallback flag
curl "http://localhost:34750/api/analytics/recent?limit=20"

# Aggregate totals
curl http://localhost:34750/api/analytics/stats
```

---

## Nova Integration

Nova-NextGen integrates with [Nova (OpenClaw)](https://openclaw.ai) via `nova_intent_router.py` — a Python script that sits between Nova's agent loop and the gateway.

**The two-tier model:**
- **Cloud (OpenRouter DeepSeek V3)** — Nova's conversations with Jordan, herd emails, Slack replies, dream journal. This is Nova's *voice*.
- **Local (Nova-NextGen)** — all compute work: code, summaries, analysis, images.

```python
# In any Nova script:
import sys
sys.path.insert(0, str(Path.home() / ".openclaw/scripts"))
from nova_intent_router import route

# Route to TinyChat for fast classification
result = route(intent="classify", prompt="Is this log line an error? [2026-04-03 ERR] timeout")

# Route to OpenWebUI for document query
result = route(intent="document_query", prompt="What does section 3.2 say?")

# Route to Ollama for deep reasoning
result = route(intent="security_analysis", prompt="Review this auth code for vulnerabilities...")

# Route to MLX Chat for summaries (Apple Silicon fast)
result = route(intent="summarize_text", prompt="Summarize: ...")

if result["success"]:
    print(result["response"])
    print(f"via {result['backend']} ({result.get('source')})")
```

**Full intent list:**
```bash
python3 ~/.openclaw/scripts/nova_intent_router.py --list-intents
```

| Intent | Backend | Task Type |
|---|---|---|
| `conversation` | Cloud DeepSeek V3 | — |
| `email_reply` | Cloud DeepSeek V3 | — |
| `slack_reply` | Cloud DeepSeek V3 | — |
| `dream_journal` | Cloud DeepSeek V3 | — |
| `herd_outreach` | Cloud DeepSeek V3 | — |
| `architecture` | Cloud DeepSeek V3 | — |
| `classify` | TinyChat | quick |
| `tag_content` | TinyChat | quick |
| `yes_no` | TinyChat | quick |
| `quick_lookup` | TinyChat | quick |
| `format_output` | TinyChat | quick |
| `code_review` | MLXCode | coding |
| `code_generation` | MLXCode | coding |
| `debug` | MLXCode | coding |
| `swift_code` | MLXCode | swift |
| `swift_review` | MLXCode | swift |
| `text_summary` | MLX Chat | general |
| `news_summary` | MLX Chat | general |
| `github_digest` | MLX Chat | general |
| `log_analysis` | MLX Chat | general |
| `summarize_text` | MLX Chat | summarize |
| `summarize_email_thread` | MLX Chat | summarize |
| `document_query` | OpenWebUI | document |
| `rag_lookup` | OpenWebUI | document |
| `research_topic` | OpenWebUI | research |
| `memory_consolidation` | Ollama | reasoning |
| `deep_analysis` | Ollama | reasoning |
| `security_analysis` | Ollama | reasoning |
| `vision_analysis` | Ollama | vision |
| `image_generation` | SwarmUI | image |
| `long_document` | Ollama | long_context |

---

## Swift Integration

Drop `AIService.swift` into any Xcode project:

```swift
// Query with auto-routing
let result = try await AIService.shared.query(
    "Write a Swift extension to validate email addresses",
    taskType: .swift
)
print(result.response)
print("Backend: \(result.backendUsed), \(result.tokensPerSecond ?? 0) tok/s")

// Quick classification (TinyChat — fastest)
let answer = try await AIService.shared.query(
    "Is this a valid IPv4 address: 192.168.1.999",
    taskType: .quick
)

// Document-grounded query (OpenWebUI)
let doc = try await AIService.shared.query(
    "What does section 4.2 specify?",
    taskType: .document
)

// Shared context
try await AIService.shared.writeContext(session: "s1", key: "goal", value: "Build HomeKit dashboard")
let advice = try await AIService.shared.query(
    "Which Swift frameworks should I use?",
    session: "s1",
    contextKeys: ["goal"]
)

// Check gateway is up
guard await AIService.shared.isAvailable() else { return }
```

---

## Configuration

`config.yaml` controls all backends, routing rules, and tuning parameters.

```yaml
gateway:
  port: 34750
  host: "127.0.0.1"   # Change to 0.0.0.0 for LAN (read SECURITY.md first)
  log_level: "INFO"

backends:
  tinychat:
    url: "http://localhost:8000"
    default_model: "qwen3:4b"

  mlxcode:
    url: "http://localhost:37422"

  mlxchat:
    url: "http://localhost:5000"
    default_model: "mlx-community/Qwen2.5-7B-Instruct-4bit"

  openwebui:
    url: "http://localhost:3000"
    default_model: "qwen3:30b"

  ollama:
    url: "http://localhost:11434"
    models:
      reasoning:    "deepseek-r1:8b"
      vision:       "qwen3-vl:4b"
      long_context: "deepseek-v3.1:671b-cloud"
      coding:       "qwen3-coder:30b"

routing:
  default_backend: "ollama"
  rules:
    - task_type: "quick"
      preferred: "tinychat"
      fallback: "ollama"

    - task_type: "coding"
      preferred: "mlxcode"
      fallback: "mlxchat"
      fallback2: "ollama"

    - task_type: "document"
      preferred: "openwebui"
      fallback: "ollama"

    - task_type: "reasoning"
      preferred: "ollama"
      model: "deepseek-r1:8b"

validation:
  consensus_threshold: 0.7   # 0.0–1.0
```

Restart after changes: `launchctl stop com.nova.gateway && launchctl start com.nova.gateway`

---

## Service Management

```bash
# Status
launchctl list | grep com.nova.gateway

# Stop / start
launchctl stop com.nova.gateway
launchctl start com.nova.gateway

# Disable autostart
launchctl unload ~/Library/LaunchAgents/com.nova.gateway.plist

# Re-enable autostart
launchctl load ~/Library/LaunchAgents/com.nova.gateway.plist

# Live logs
tail -f ~/.nova_gateway/gateway.log
tail -f ~/.nova_gateway/gateway.error.log

# Manual start (dev, hot reload)
./run.sh --reload --debug
```

---

## Project Structure

```
Nova-NextGen/
├── nova_gateway/
│   ├── main.py              # FastAPI app — startup, all routes
│   ├── router.py            # Intent detection + backend selection + fallback
│   ├── config.py            # config.yaml loader
│   ├── models.py            # Pydantic request/response models
│   ├── backends/
│   │   ├── base.py          # Abstract base (httpx async, health_check)
│   │   ├── tinychat.py      # TinyChat — OpenAI-compat, qwen3:4b, fastest
│   │   ├── mlxcode.py       # MLXCode — Apple ANE, Swift/coding
│   │   ├── mlxchat.py       # MLX Chat — Apple ANE, fast general
│   │   ├── openwebui.py     # OpenWebUI — RAG, document processing
│   │   ├── ollama.py        # Ollama — reasoning, vision, long context
│   │   ├── swarmui.py       # SwarmUI — image generation
│   │   └── comfyui.py       # ComfyUI — image workflows (fallback)
│   ├── context/
│   │   └── store.py         # aiosqlite session memory bus
│   └── validation/
│       └── consensus.py     # Cosine-similarity cross-model scoring
├── AIService.swift          # Drop-in Swift client for Xcode projects
├── config.yaml              # All runtime configuration
├── requirements.txt         # Pinned Python dependencies
├── run.sh                   # Manual start / dev mode
├── install.sh               # One-shot setup + LaunchAgent registration
├── SECURITY.md              # Threat model, hardening guide
└── LICENSE                  # MIT
```

---

## Troubleshooting

**Gateway won't start:**
```bash
cat ~/.nova_gateway/gateway.error.log
```
Common causes: port 34750 in use (change in `config.yaml`), wrong Python version (must be 3.12).

**Backend shows unavailable:**
- TinyChat: check Docker container is running — `docker ps | grep tinychat`
- MLXCode: app must be open with a model loaded (`/api/status` returns `modelLoaded: true`)
- MLX Chat: check port 5000 is serving — `curl http://localhost:5000/health`
- OpenWebUI: check Docker container — `docker ps | grep openwebui`
- Ollama: start with `/usr/local/bin/ollama serve`

**Ollama queries are slow on first call:**
Large models (30B+) take 30–60 seconds to load from disk. Subsequent calls are fast once the model is resident. The gateway timeout is 300s.

**OpenWebUI RAG not returning document results:**
RAG in OpenWebUI requires documents to be uploaded and indexed through the OpenWebUI web interface first. The gateway sends the query but document retrieval is managed by OpenWebUI itself.

---

## Security

- Binds to `127.0.0.1` by default — not reachable from other machines
- CORS restricted to `http://localhost` and `http://127.0.0.1`
- All SQL uses parameterized queries — no injection risk
- Input validated by Pydantic on every request
- No credentials stored in this project

See [SECURITY.md](SECURITY.md) for the full threat model and hardening guide for LAN deployment.

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | 0.115.6 | HTTP framework |
| `uvicorn[standard]` | 0.34.0 | ASGI server |
| `httpx` | 0.28.1 | Async HTTP client |
| `aiosqlite` | 0.20.0 | Async SQLite context store |
| `pyyaml` | 6.0.2 | Config parsing |
| `pydantic` | 2.10.4 | Request/response validation |
| `python-multipart` | 0.0.20 | Form data |
| `aiofiles` | 24.1.0 | Async file operations |

---

## License

MIT License — Copyright © 2026 Jordan Koch. See [LICENSE](LICENSE).
