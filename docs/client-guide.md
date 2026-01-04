# Building Clients

This guide covers best practices for building robust downstream applications that communicate with the Voxta Gateway. Whether you're building a chat overlay, avatar bridge, or game integration, these patterns will help you create reliable, maintainable clients.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Your Application                     │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  │
│  │ State       │  │ Event       │  │ Action          │  │
│  │ Manager     │  │ Handlers    │  │ Dispatcher      │  │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘  │
│         │                │                  │           │
│         └────────────────┼──────────────────┘           │
│                          │                              │
│                   ┌──────▼──────┐                       │
│                   │  Gateway    │                       │
│                   │  Client     │                       │
│                   └──────┬──────┘                       │
└──────────────────────────┼──────────────────────────────┘
                           │
                    ┌──────▼──────┐
                    │   Gateway   │
                    │   Server    │
                    └─────────────┘
```

## Client Lifecycle

### 1. Connection Phase

```python
import asyncio
import websockets
import json
from enum import Enum

class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"  # Connected AND chat is active

class GatewayClient:
    def __init__(self, gateway_url: str, client_id: str):
        self.gateway_url = gateway_url
        self.client_id = client_id
        self.state = ClientState.DISCONNECTED
        self.chat_active = False
        self.websocket = None
        
    async def connect(self, events: list[str]):
        """Connect to gateway and subscribe to events."""
        self.state = ClientState.CONNECTING
        
        ws_url = self.gateway_url.replace("http", "ws") + "/ws"
        self.websocket = await websockets.connect(ws_url)
        
        # Subscribe to events
        await self.websocket.send(json.dumps({
            "type": "subscribe",
            "client_id": self.client_id,
            "events": events
        }))
        
        # Wait for snapshot
        response = await self.websocket.recv()
        snapshot = json.loads(response)
        
        if snapshot["type"] == "snapshot":
            self.chat_active = snapshot["state"]["chat_active"]
            self.state = ClientState.READY if self.chat_active else ClientState.CONNECTED
            
        return snapshot["state"]
```

### 2. Event Handling Phase

```python
async def listen(self):
    """Main event loop."""
    async for message in self.websocket:
        event = json.loads(message)
        await self._handle_event(event)

async def _handle_event(self, event: dict):
    """Route events to handlers."""
    event_type = event["type"]
    data = event.get("data", {})
    
    # Chat lifecycle
    if event_type == "chat_started":
        self.chat_active = True
        self.state = ClientState.READY
        await self.on_chat_started(data)
        
    elif event_type == "chat_closed":
        self.chat_active = False
        self.state = ClientState.CONNECTED
        await self.on_chat_closed()
    
    # Other events - only process if chat is active
    elif self.chat_active:
        if event_type == "dialogue_received":
            await self.on_dialogue(data)
        elif event_type == "ai_state_changed":
            await self.on_ai_state_changed(data)
        # ... more handlers
```

### 3. Action Phase

```python
async def send_dialogue(self, text: str, source: str = "user"):
    """Send dialogue to the gateway."""
    if not self.chat_active:
        raise RuntimeError("Cannot send dialogue: no active chat")
    
    async with httpx.AsyncClient() as client:
        await client.post(
            f"{self.gateway_url}/dialogue",
            json={"text": text, "source": source}
        )
```

## Best Practices

### ✅ DO: Check Chat Status Before Sending

```python
# Good - check before sending
if client.chat_active:
    await client.send_dialogue("Hello!")

# Also good - use state from snapshot on connect
state = await client.connect(["chat_started", "chat_closed"])
if state["chat_active"]:
    await client.send_dialogue("I just connected!")
```

### ❌ DON'T: Send Blindly

```python
# Bad - no check, will fail if no chat
await client.send_dialogue("Hello!")
```

### ✅ DO: Subscribe Only to Events You Need

```python
# Good - specific events reduce noise
events = ["chat_started", "chat_closed", "dialogue_received"]

# Acceptable for debugging
events = ["all"]

# Bad - subscribing to everything in production
# (wastes bandwidth and processing)
```

### ✅ DO: Handle Reconnection Gracefully

```python
async def run_with_reconnect(self):
    """Run client with automatic reconnection."""
    while True:
        try:
            await self.connect(self.events)
            await self.listen()
        except websockets.ConnectionClosed:
            self.state = ClientState.DISCONNECTED
            self.chat_active = False
            await asyncio.sleep(5)  # Backoff before reconnect
        except Exception as e:
            logging.error(f"Client error: {e}")
            await asyncio.sleep(5)
```

### ✅ DO: Use State Snapshots, Not Assumptions

```python
# Good - use the snapshot
state = await client.connect(events)
if state["ai_state"] == "speaking":
    # AI is currently speaking, maybe wait
    pass

# Bad - assume initial state
# (you don't know what happened before you connected)
```

## Event Subscription Patterns

### Chat Overlay (Read-Only)

Only needs to display messages:

```python
events = [
    "chat_started",      # Know when to start showing messages
    "chat_closed",       # Know when to clear/hide
    "dialogue_received", # The actual messages
]
```

### Avatar Bridge (TTS Integration)

Needs sentences for TTS and state for lip-sync timing:

```python
events = [
    "chat_started",
    "chat_closed",
    "sentence_ready",           # Complete sentences for TTS
    "ai_state_changed",         # Know when AI is speaking
    "external_speaker_started", # Stop TTS when external speaker
    "external_speaker_stopped",
    "app_trigger",              # Expression/animation commands
    "characters_updated",       # Preload avatar models
]
```

### Game Dialogue Relay (Bidirectional)

Sends game dialogue, needs to know AI state:

```python
events = [
    "chat_started",
    "chat_closed", 
    "ai_state_changed",  # Know when to interrupt/wait
]
```

### Twitch Chat Relay (Fire-and-Forget)

Minimal events, mostly sending:

```python
events = [
    "chat_started",
    "chat_closed",
]
# Mostly uses HTTP POST /dialogue
```

## Complete Client Example

Here's a production-ready client template:

```python
import asyncio
import json
import logging
from enum import Enum
from typing import Callable, Optional

import httpx
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ClientState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    READY = "ready"


class GatewayClient:
    """Production-ready Gateway client with reconnection support."""
    
    def __init__(
        self,
        gateway_url: str = "http://localhost:8081",
        client_id: str = "my-client",
        events: list[str] = None,
    ):
        self.gateway_url = gateway_url
        self.client_id = client_id
        self.events = events or ["chat_started", "chat_closed"]
        
        self.state = ClientState.DISCONNECTED
        self.chat_active = False
        self.characters = []
        self.ai_state = "idle"
        
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False
    
    def on(self, event_type: str, handler: Callable):
        """Register an event handler."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
    
    async def start(self):
        """Start the client with automatic reconnection."""
        self._running = True
        while self._running:
            try:
                await self._connect()
                await self._listen()
            except websockets.ConnectionClosed:
                logger.warning("Connection closed, reconnecting in 5s...")
            except Exception as e:
                logger.error(f"Error: {e}, reconnecting in 5s...")
            
            self.state = ClientState.DISCONNECTED
            self.chat_active = False
            
            if self._running:
                await asyncio.sleep(5)
    
    async def stop(self):
        """Stop the client."""
        self._running = False
        if self._websocket:
            await self._websocket.close()
    
    async def _connect(self):
        """Connect to the gateway."""
        self.state = ClientState.CONNECTING
        logger.info(f"Connecting to {self.gateway_url}...")
        
        ws_url = self.gateway_url.replace("http", "ws") + "/ws"
        self._websocket = await websockets.connect(ws_url)
        
        # Subscribe
        await self._websocket.send(json.dumps({
            "type": "subscribe",
            "client_id": self.client_id,
            "events": self.events
        }))
        
        # Get snapshot
        response = await self._websocket.recv()
        snapshot = json.loads(response)
        
        if snapshot["type"] == "snapshot":
            self._update_state(snapshot["state"])
        
        logger.info(f"Connected! Chat active: {self.chat_active}")
    
    async def _listen(self):
        """Listen for events."""
        async for message in self._websocket:
            event = json.loads(message)
            await self._dispatch(event)
    
    async def _dispatch(self, event: dict):
        """Dispatch event to handlers."""
        event_type = event["type"]
        data = event.get("data", {})
        
        # Update internal state
        if event_type == "chat_started":
            self.chat_active = True
            self.characters = data.get("characters", [])
            self.state = ClientState.READY
        elif event_type == "chat_closed":
            self.chat_active = False
            self.characters = []
            self.state = ClientState.CONNECTED
        elif event_type == "ai_state_changed":
            self.ai_state = data.get("new_state", "idle")
        elif event_type == "characters_updated":
            self.characters = data.get("characters", [])
        
        # Call registered handlers
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(data)
                    else:
                        handler(data)
                except Exception as e:
                    logger.error(f"Handler error: {e}")
    
    def _update_state(self, state: dict):
        """Update internal state from snapshot."""
        self.chat_active = state.get("chat_active", False)
        self.characters = state.get("characters", [])
        self.ai_state = state.get("ai_state", "idle")
        self.state = ClientState.READY if self.chat_active else ClientState.CONNECTED
    
    # ─────────────────────────────────────────────────────────
    # Actions (HTTP)
    # ─────────────────────────────────────────────────────────
    
    async def send_dialogue(self, text: str, source: str = "user", author: str = None):
        """Send dialogue to the gateway."""
        if not self.chat_active:
            logger.warning("Cannot send dialogue: no active chat")
            return
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.gateway_url}/dialogue",
                json={"text": text, "source": source, "author": author}
            )
    
    async def send_context(self, key: str, content: str, description: str = None):
        """Send context update."""
        if not self.chat_active:
            logger.warning("Cannot send context: no active chat")
            return
        
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.gateway_url}/context",
                json={"key": key, "content": content, "description": description}
            )
    
    async def external_speaker_start(self, source: str, reason: str = None):
        """Signal external speaker started."""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.gateway_url}/external_speaker_start",
                json={"source": source, "reason": reason}
            )
    
    async def external_speaker_stop(self, trigger_response: bool = True):
        """Signal external speaker stopped."""
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.gateway_url}/external_speaker_stop",
                json={"trigger_response": trigger_response}
            )


# ─────────────────────────────────────────────────────────
# Usage Example
# ─────────────────────────────────────────────────────────

async def main():
    client = GatewayClient(
        gateway_url="http://localhost:8081",
        client_id="example-client",
        events=["chat_started", "chat_closed", "dialogue_received", "ai_state_changed"]
    )
    
    @client.on("chat_started")
    async def on_chat_started(data):
        print(f"Chat started with characters: {data.get('characters', [])}")
    
    @client.on("dialogue_received")
    async def on_dialogue(data):
        print(f"[{data.get('source', '?')}] {data.get('text', '')}")
    
    @client.on("ai_state_changed")
    def on_state_change(data):
        print(f"AI state: {data.get('old_state')} -> {data.get('new_state')}")
    
    await client.start()


if __name__ == "__main__":
    asyncio.run(main())
```

## Anti-Patterns to Avoid

### ❌ Polling State Instead of Using Events

```python
# Bad - polling wastes resources
while True:
    state = requests.get(f"{gateway}/state").json()
    if state["ai_state"] == "idle":
        do_something()
    await asyncio.sleep(0.1)  # 10 requests per second!

# Good - subscribe to events
@client.on("ai_state_changed")
async def on_state_change(data):
    if data["new_state"] == "idle":
        await do_something()
```

### ❌ Ignoring Chat Lifecycle

```python
# Bad - sends even when no chat
async def send_periodically():
    while True:
        await client.send_dialogue("Update!")  # Might fail
        await asyncio.sleep(60)

# Good - respect chat lifecycle
async def send_periodically():
    while True:
        if client.chat_active:
            await client.send_dialogue("Update!")
        await asyncio.sleep(60)
```

### ❌ Not Handling Reconnection

```python
# Bad - crashes on disconnect
async def main():
    await client.connect()
    await client.listen()  # If this fails, program exits

# Good - automatic reconnection (see template above)
async def main():
    await client.start()  # Handles reconnection internally
```

## Next Steps

- [API Reference](api.md) - Complete endpoint and event documentation
- [Development Guide](development-guide.md) - Contributing to the gateway itself

