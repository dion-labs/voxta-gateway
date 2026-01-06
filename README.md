# Voxta Gateway

[![Build](https://github.com/dion-labs/voxta-gateway/actions/workflows/ci.yml/badge.svg)](https://github.com/dion-labs/voxta-gateway/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/dion-labs/voxta-gateway/branch/main/graph/badge.svg)](https://codecov.io/gh/dion-labs/voxta-gateway)
[![PyPI version](https://img.shields.io/pypi/v/voxta-gateway.svg)](https://pypi.org/project/voxta-gateway/)
[![Python versions](https://img.shields.io/pypi/pyversions/voxta-gateway.svg)](https://pypi.org/project/voxta-gateway/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A state-mirroring gateway for the Voxta conversational AI platform, providing high-level semantic APIs for downstream applications.

## Overview

The Voxta Gateway is the single point of contact between the AI Streaming OS ecosystem and Voxta. It acts as a **State-Mirror** that observes Voxta state and broadcasts it to downstream applications, while providing **Consumer-First** APIs that only expose functionality actively used by registered consumers.

### Key Features

- **Startup Order Independence**: Apps can start in any order and receive state snapshots on connection
- **High-Level Semantic APIs**: No downstream app needs to understand Voxta internals
- **Selective Event Streaming**: Each app only receives events it subscribed to
- **Per-Client Observability**: Debug UI shows traffic breakdown per connected app
- **Sentence Buffering**: Processes reply chunks into complete sentences for TTS

## Installation

```bash
pip install voxta-gateway
```

Or install from source:

```bash
git clone https://github.com/dion-labs/voxta-gateway.git
cd voxta-gateway/main
pip install -e ".[dev]"
```

## Quick Start

```bash
# Start the gateway
VOXTA_URL=http://localhost:5384 uvicorn voxta_gateway.main:app --host 0.0.0.0 --port 8081
```

Or use the CLI:

```bash
voxta-gateway
```

## API Overview

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check and Voxta connection status |
| `/state` | GET | Current gateway state snapshot |
| `/dialogue` | POST | Send dialogue (user, game, twitch) |
| `/context` | POST | Send context update (not shown in chat) |
| `/external_speaker_start` | POST | Signal external speaker started |
| `/external_speaker_stop` | POST | Signal external speaker stopped |
| `/tts_playback_start` | POST | Signal TTS playback started |
| `/tts_playback_complete` | POST | Signal TTS playback completed |

### WebSocket

Connect to `/ws` and send a subscription message:

```json
{
    "type": "subscribe",
    "client_id": "my-app",
    "events": ["dialogue_received", "ai_state_changed"]
}
```

Available events:
- `chat_started` - A chat session became active (safe to send messages)
- `chat_closed` - The chat session was closed (stop sending messages)
- `dialogue_received` - User message, AI message, or game dialogue
- `sentence_ready` - Complete sentence ready for TTS
- `ai_state_changed` - AI state transition (idle/thinking/speaking)
- `external_speaker_started` - External speaker began talking
- `external_speaker_stopped` - External speaker finished talking
- `app_trigger` - Expression/animation commands
- `characters_updated` - Character list changed

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VOXTA_URL` | `http://localhost:5384` | Voxta server URL |
| `GATEWAY_PORT` | `8081` | Gateway HTTP port |
| `LOG_LEVEL` | `INFO` | Logging level |

## Architecture

```
┌─────────────────┐       ┌──────────────────┐       ┌───────────────────┐
│     Voxta       │ ────> │  Voxta-Gateway   │ ────> │  Downstream Apps  │
│    (Brain)      │       │  (State Mirror)  │       │ (Decision Makers) │
└─────────────────┘       └──────────────────┘       └───────────────────┘
                                │
                                v
                         [Mirrored State]
                         - session_id
                         - chat_id
                         - characters[]
                         - ai_state
                         - external_speaker_active
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linter
ruff check .

# Format code
ruff format .
```

## License

MIT License - see [LICENSE](LICENSE) for details.

