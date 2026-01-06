# Migration Guide: Moving to Voxta Gateway

This guide provides a structured approach for migrating existing applications from direct `VoxtaClient` (SignalR) usage to the high-level semantic `GatewayClient` provided by the Voxta Gateway.

## Overview

The Voxta Gateway acts as a state-mirroring proxy. Instead of your application managing raw SignalR events, session pinning, and manual state tracking, the `GatewayClient` provides:

1.  **Simplified State**: Properties like `client.chat_active` and `client.ai_state`.
2.  **High-Level Actions**: `send_dialogue`, `external_speaker_start`, etc.
3.  **Automatic Reconnection**: Built-in retry logic for both HTTP and WebSocket.
4.  **Semantic Events**: Clean events like `chat_started`, `sentence_ready`, and `ai_state_changed`.

---

## Phase 1: Preparation

### 1. Isolated Migration (Worktrees)
Before modifying the application, create a dedicated git worktree. This prevents interference with the stable codebase while you iterate.

```bash
git worktree add migration-your-app -b migrate-your-app
```

### 2. Handling Unreleased Gateway Source
If the `voxta-gateway` is not yet published to PyPI, you must manually point your application to its source directory.

```python
import sys
from pathlib import Path

# Add local voxta-gateway to path
gateway_path = Path("/path/to/dion-labs-oss/voxta-gateway/main")
if gateway_path.exists():
    sys.path.append(str(gateway_path))
```

---

## Phase 2: Client Transition

### 1. Update Imports
Replace the old `VoxtaClient` imports with the `GatewayClient`.

**Before:**
```python
from voxta_client import VoxtaClient
```

**After:**
```python
from voxta_gateway.client import GatewayClient
```

### 2. Lifecycle Management
The `GatewayClient` runs its own event loop and handles reconnection. Start it as a background task.

```python
async def main():
    client = GatewayClient(gateway_url="http://localhost:8081", client_id="my-app")
    
    # Start in background
    gateway_task = asyncio.create_task(client.start())
    
    # ... your app logic ...
    
    await client.stop()
    gateway_task.cancel()
```

---

## Phase 3: Implementing Core Logic

### 1. Chat Lifecycle & Queuing
Directly sending messages to Voxta when no chat is active usually causes drops. Use the `chat_started` event to flush a local queue.

```python
class MyRelay:
    def __init__(self, client):
        self.client = client
        self.queue = []

    async def on_message(self, text):
        if self.client.chat_active:
            await self.client.send_dialogue(text=text, source="my-source")
        else:
            self.queue.append(text)

    async def flush_queue(self):
        while self.queue:
            text = self.queue.pop(0)
            await self.client.send_dialogue(text=text)

# Subscribe to lifecycle
client.on("chat_started", my_relay.flush_queue)
```

### 2. Health Monitoring
Implement a periodic health check to ensure the gateway is reachable and Voxta is connected to the gateway.

```python
async def health_loop(client):
    while True:
        try:
            health = await client.health_check()
            if not health["voxta_connected"]:
                logging.warning("Gateway up, but Voxta disconnected from it")
        except Exception:
            logging.error("Gateway unreachable")
        await asyncio.sleep(30)
```

---

## Phase 4: Observability (Best Practice)

For relays and background workers, it is highly recommended to add a simple **FastAPI Debug App**. This allows you to inspect the internal state (queue size, history, gateway status) without digging through logs.

```python
from fastapi import FastAPI
import uvicorn

app = FastAPI()

@app.get("/")
async def status():
    return {
        "gateway": client.is_connected,
        "chat": client.chat_active,
        "queue_size": len(my_relay.queue)
    }

# Start uvicorn as an additional background task
```

---

## Phase 5: Containerization

Update your `Dockerfile` to include the new gateway requirements:

1.  **Dependencies**: Add `httpx`, `fastapi`, and `uvicorn`.
2.  **Voxta Client**: Ensure `voxta-client >= 0.2.0` is used for compatibility.
3.  **Source Mounts**: If using the unreleased gateway, ensure the directory is mounted or copied into the container.

```dockerfile
RUN pip install httpx fastapi uvicorn "voxta-client>=0.2.0"
```

---

## Common Pitfalls

*   **Path Conflicts**: Ensure the directory containing `voxta_gateway/` is in `sys.path`, not the package folder itself.
*   **Blocking Handlers**: Never put blocking `sleep()` or heavy CPU work inside an `@client.on` handler. Use `asyncio.create_task()` if you need to run something long-lived.
*   **Immediate Reply**: By default, `send_dialogue` might not trigger a reply for certain sources. Explicitly set `immediate_reply=True` if you want the AI to talk back immediately after every message.


