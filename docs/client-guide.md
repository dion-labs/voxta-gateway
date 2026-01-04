# Building Clients

This guide covers how to use the `GatewayClient` to build downstream applications that communicate with the Voxta Gateway.

## Using the GatewayClient

The `voxta-gateway` package includes a ready-to-use client that handles all the complexity of connecting, reconnecting, and processing events.

### Installation

```bash
pip install voxta-gateway
```

### Quick Start

```python
import asyncio
from voxta_gateway import GatewayClient

async def main():
    # Create client
    client = GatewayClient(
        gateway_url="http://localhost:8081",
        client_id="my-app",
        events=["chat_started", "chat_closed", "dialogue_received"]
    )
    
    # Register event handlers
    @client.on("dialogue_received")
    async def on_dialogue(data):
        print(f"[{data.get('source', '?')}] {data.get('text', '')}")
    
    @client.on("chat_started")
    async def on_chat_started(data):
        print(f"Chat started with: {[c['name'] for c in data.get('characters', [])]}")
    
    # Run with automatic reconnection
    await client.start()

asyncio.run(main())
```

## Client API Reference

### Constructor

```python
GatewayClient(
    gateway_url: str = "http://localhost:8081",
    client_id: str = "gateway-client",
    events: list[str] = None,  # Default: essential events
    reconnect_delay: float = 5.0,
    logger: logging.Logger = None,
)
```

### Lifecycle Methods

| Method | Description |
|--------|-------------|
| `await client.start()` | Run with automatic reconnection (blocks) |
| `await client.stop()` | Stop the client |
| `await client.connect_once()` | Connect without auto-reconnect (returns bool) |
| `await client.wait_for_chat(timeout=30)` | Wait until chat is active |
| `await client.wait_for_idle(timeout=30)` | Wait until AI is idle |

### State Properties

| Property | Type | Description |
|----------|------|-------------|
| `client.is_connected` | bool | Connected to gateway? |
| `client.is_ready` | bool | Connected AND chat active? |
| `client.chat_active` | bool | Is there an active chat? |
| `client.ai_state` | str | Current AI state (idle/thinking/speaking) |
| `client.characters` | list | Characters in current chat |
| `client.state` | GatewayState | Full state object |

### Action Methods

All action methods return `bool` (True if successful).

```python
# Send dialogue
await client.send_dialogue(
    text="Hello!",
    source="user",           # "user", "game", "twitch"
    author="PlayerName",     # Optional
    immediate_reply=True     # Optional
)

# Send context (not shown in chat)
await client.send_context(
    key="chessboard",
    content="FEN: rnbqkbnr/...",
    description="White played e4"  # Optional spoken summary
)

# External speaker management
await client.external_speaker_start(source="game", reason="npc_dialogue")
await client.external_speaker_stop(trigger_response=True)

# TTS coordination
await client.tts_playback_start(character_id="char-uuid", message_id="msg-uuid")
await client.tts_playback_complete(character_id="char-uuid", message_id="msg-uuid")

# Utilities
state = await client.get_state()  # Fetch current state
health = await client.health_check()  # Check gateway health
```

### Event Registration

```python
# Using decorator
@client.on("dialogue_received")
async def handler(data):
    pass

# Using method call
client.on("dialogue_received", my_handler)

# Remove handler
client.off("dialogue_received", my_handler)
```

## Example Applications

### Chat Overlay

Display messages in an OBS overlay:

```python
import asyncio
from voxta_gateway import GatewayClient

async def main():
    client = GatewayClient(
        client_id="chat-overlay",
        events=["chat_started", "chat_closed", "dialogue_received"]
    )
    
    messages = []
    
    @client.on("dialogue_received")
    async def on_dialogue(data):
        messages.append({
            "text": data["text"],
            "source": data.get("source", "unknown"),
            "author": data.get("author"),
        })
        # Update your UI here
        print(f"[{data.get('source')}] {data.get('text')}")
    
    @client.on("chat_closed")
    async def on_chat_closed(data):
        messages.clear()
        print("Chat closed, clearing messages")
    
    await client.start()

asyncio.run(main())
```

### Game Dialogue Relay

OCR game subtitles and relay to AI:

```python
import asyncio
from voxta_gateway import GatewayClient

async def main():
    client = GatewayClient(
        client_id="game-relay",
        events=["chat_started", "chat_closed", "ai_state_changed"]
    )
    
    @client.on("connected")
    async def on_connected(state):
        print(f"Connected! Chat active: {state.get('chat_active')}")
    
    # Start client in background
    asyncio.create_task(client.start())
    
    # Wait for connection
    await asyncio.sleep(2)
    
    # Simulate game dialogue detection
    while True:
        if client.chat_active:
            # When NPC starts talking
            await client.external_speaker_start(source="game", reason="npc_dialogue")
            
            # Send captured dialogue
            await client.send_dialogue(
                text="I used to be an adventurer like you...",
                source="game",
                author="Guard",
                immediate_reply=False
            )
            
            # When NPC stops talking
            await client.external_speaker_stop(trigger_response=True)
        
        await asyncio.sleep(5)

asyncio.run(main())
```

### Avatar Bridge (TTS Integration)

Process sentences and coordinate TTS:

```python
import asyncio
from voxta_gateway import GatewayClient

async def main():
    client = GatewayClient(
        client_id="avatar-bridge",
        events=[
            "chat_started", "chat_closed",
            "sentence_ready",
            "ai_state_changed",
            "external_speaker_started", "external_speaker_stopped",
            "app_trigger",
            "characters_updated"
        ]
    )
    
    tts_queue = asyncio.Queue()
    
    @client.on("sentence_ready")
    async def on_sentence(data):
        # Queue sentence for TTS
        await tts_queue.put({
            "text": data["text"],
            "character_id": data["character_id"],
            "message_id": data["message_id"]
        })
    
    @client.on("external_speaker_started")
    async def on_external_speaker(data):
        # Clear TTS queue when external speaker interrupts
        while not tts_queue.empty():
            tts_queue.get_nowait()
        print(f"External speaker ({data['source']}) started, cleared queue")
    
    @client.on("app_trigger")
    async def on_trigger(data):
        # Handle expressions/animations
        print(f"Trigger: {data['name']} with args {data.get('arguments', {})}")
    
    # TTS processing loop
    async def tts_loop():
        while True:
            item = await tts_queue.get()
            
            # Signal playback start
            await client.tts_playback_start(
                character_id=item["character_id"],
                message_id=item["message_id"]
            )
            
            # Generate and play TTS (your TTS code here)
            print(f"Speaking: {item['text']}")
            await asyncio.sleep(len(item["text"]) * 0.05)  # Simulate TTS
            
            # Signal playback complete
            await client.tts_playback_complete(
                character_id=item["character_id"],
                message_id=item["message_id"]
            )
    
    # Run both
    await asyncio.gather(
        client.start(),
        tts_loop()
    )

asyncio.run(main())
```

### Twitch Chat Relay

Forward Twitch messages to AI:

```python
import asyncio
from voxta_gateway import GatewayClient

async def main():
    client = GatewayClient(
        client_id="twitch-relay",
        events=["chat_started", "chat_closed"]
    )
    
    # Connect without blocking
    connected = await client.connect_once()
    if not connected:
        print("Failed to connect to gateway")
        return
    
    # Simulate Twitch messages
    async def process_twitch_message(username: str, message: str):
        if client.chat_active:
            await client.send_dialogue(
                text=message,
                source="twitch",
                author=username,
                immediate_reply=False  # Don't spam AI with every message
            )
    
    # Your Twitch integration here
    await process_twitch_message("viewer123", "Hello streamer!")
    await process_twitch_message("chatter456", "Great stream!")
    
    await client.stop()

asyncio.run(main())
```

## Event Subscription Recommendations

| Application | Recommended Events |
|-------------|-------------------|
| Chat Overlay | `chat_started`, `chat_closed`, `dialogue_received` |
| Avatar Bridge | `chat_started`, `chat_closed`, `sentence_ready`, `ai_state_changed`, `external_speaker_started`, `external_speaker_stopped`, `app_trigger`, `characters_updated` |
| Game Relay | `chat_started`, `chat_closed`, `ai_state_changed` |
| Twitch Relay | `chat_started`, `chat_closed` |
| Debug Tool | `all` |

## Best Practices

### ✅ DO: Check Chat Status Before Sending

```python
if client.chat_active:
    await client.send_dialogue("Hello!")
else:
    print("Waiting for chat...")
```

Or use the helper:

```python
if await client.wait_for_chat(timeout=30):
    await client.send_dialogue("Hello!")
```

### ✅ DO: Handle Connection Events

```python
@client.on("connected")
async def on_connected(state):
    if state["chat_active"]:
        print("Ready to go!")

@client.on("disconnected")
async def on_disconnected(data):
    print("Lost connection, will reconnect...")
```

### ✅ DO: Use Appropriate Events

Subscribe only to events you need - less noise, better performance:

```python
# Good - specific events
client = GatewayClient(events=["dialogue_received", "chat_started"])

# Avoid in production
client = GatewayClient(events=["all"])
```

### ❌ DON'T: Block Event Handlers

```python
# Bad - blocks all event processing
@client.on("dialogue_received")
async def on_dialogue(data):
    await slow_operation()  # Don't do this!

# Good - process in background
@client.on("dialogue_received")
async def on_dialogue(data):
    asyncio.create_task(slow_operation(data))
```

### ❌ DON'T: Ignore Chat Lifecycle

```python
# Bad - sends even when no chat
await client.send_dialogue("Hello!")  # Raises RuntimeError

# Good - respects lifecycle
if client.chat_active:
    await client.send_dialogue("Hello!")
```

## Next Steps

- [API Reference](api.md) - Complete endpoint and event documentation
- [Development Guide](development-guide.md) - Contributing to the gateway
