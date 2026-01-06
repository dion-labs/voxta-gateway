# Development Guide

This guide is for developers (human or AI) who want to understand, modify, or extend the Voxta Gateway. It covers the architecture, design principles, and code conventions that keep this project maintainable.

## The Two Golden Rules

!!! danger "Rule 1: State-Mirror Only"
    The Gateway **observes** Voxta state and **broadcasts** it. It never **decides** or **acts** based on state.

    ```python
    # ✅ CORRECT
    # Voxta sent replyGenerating → Update state.ai_state → Broadcast ai_state_changed
    
    # ❌ WRONG
    # state.ai_state is THINKING for 10 seconds → Send timeout interrupt
    ```

    If you find yourself writing `if state.X then do Y`, stop. That logic belongs in a downstream app, not the gateway.

!!! danger "Rule 2: Consumer-First Features"
    Every line of code must trace back to a consumer need. No speculative features.

    ```python
    # ✅ CORRECT
    # Avatar-bridge needs sentence_ready events → Implement sentence buffer
    
    # ❌ WRONG
    # Voxta has a load_scenarios API → Expose it just in case
    ```

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                        main.py                               │
│                   (FastAPI endpoints)                        │
└───────────────────────────┬──────────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────────┐
│                       gateway.py                             │
│            (Orchestration + High-Level APIs)                 │
├──────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────────┐  ┌─────────────────┐   │
│  │   state.py  │  │ sentence_buffer │  │ websocket_mgr   │   │
│  │  (Models)   │  │    (Text→TTS)   │  │  (Broadcasts)   │   │
│  └─────────────┘  └─────────────────┘  └─────────────────┘   │
│                                                              │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │                   voxta_bridge.py                        │ │
│  │              (Voxta Client + Observers)                  │ │
│  └──────────────────────────┬──────────────────────────────┘ │
└─────────────────────────────┼────────────────────────────────┘
                              │
                       ┌──────▼──────┐
                       │   Voxta     │
                       │  (SignalR)  │
                       └─────────────┘
```

## Module Responsibilities

### `state.py` - Data Models

**Purpose:** Define the gateway's mirrored state.

```python
# What belongs here:
- GatewayState dataclass
- AIState enum
- CharacterInfo dataclass
- to_snapshot() method

# What does NOT belong here:
- Business logic
- State transitions (those are triggered by events)
- Anything that "decides"
```

### `voxta_bridge.py` - Voxta Observer

**Purpose:** Connect to Voxta, observe events, update state.

```python
# What belongs here:
- VoxtaClient connection management
- Event observers that UPDATE state
- Low-level Voxta operations (for Gateway to call)
- Event history recording

# What does NOT belong here:
- High-level semantic APIs
- Business logic decisions
- Direct WebSocket broadcasting
```

### `gateway.py` - Orchestration

**Purpose:** Tie components together, provide high-level APIs.

```python
# What belongs here:
- external_speaker_start/stop (translates to Voxta operations)
- send_dialogue (formats and sends)
- Event routing from bridge → websocket manager
- Sentence buffer integration

# What does NOT belong here:
- Direct Voxta protocol knowledge
- HTTP/WebSocket endpoint definitions
- App-specific logic
```

### `websocket_manager.py` - Client Registry

**Purpose:** Track connected clients, route events by subscription.

```python
# What belongs here:
- Client connection/disconnection
- Subscription management
- Selective event broadcasting
- Per-client message history

# What does NOT belong here:
- Event generation
- State management
- HTTP endpoints
```

### `sentence_buffer.py` - Text Processing

**Purpose:** Convert streaming reply chunks into complete sentences.

```python
# What belongs here:
- Text accumulation per message
- Sentence boundary detection
- Callback invocation when sentence is ready

# What does NOT belong here:
- TTS generation (that's in downstream apps)
- Voxta protocol knowledge
```

### `main.py` - HTTP/WebSocket Layer

**Purpose:** FastAPI application, endpoints, middleware.

```python
# What belongs here:
- HTTP endpoint definitions
- WebSocket endpoint
- Request/Response models
- CORS, middleware, lifespan

# What does NOT belong here:
- Business logic
- Direct Voxta interaction
- State management
```

## Decision Flowchart: Where Does This Code Belong?

```
Is this feature requested by a consumer?
├── NO → Don't implement it
└── YES ↓

Does it require Voxta internal knowledge?
├── NO → Implement in the downstream app
└── YES ↓

Do multiple apps need this same calculation?
├── NO → Implement in the single app that needs it
└── YES → Implement in Gateway
```

## Adding a New Feature

### Step 1: Document the Need

Before writing code, answer:

1. **Which consumer needs this?** (avatar-bridge, chat-overlay, etc.)
2. **What problem does it solve?** (not "it would be nice")
3. **Can it be done in the downstream app instead?**

### Step 2: Choose the Right Layer

| Feature Type | Location |
|-------------|----------|
| New event from Voxta | `voxta_bridge.py` (observer) |
| New derived state | `state.py` (property) |
| New high-level action | `gateway.py` (method) |
| New HTTP endpoint | `main.py` (route) |
| New WebSocket event | Add to `events_to_broadcast` in `gateway.py` |

### Step 3: Implement

```python
# Example: Adding a new "user_typing" event

# 1. Add observer in voxta_bridge.py
async def _on_typing_start(self, data: dict):
    await self.event_emitter.emit("user_typing_started", {})

# 2. Add to event routing in gateway.py
events_to_broadcast = [
    # ... existing events ...
    "user_typing_started",
    "user_typing_stopped",
]

# 3. Document in docs/api/events.md
```

### Step 4: Test

```python
# tests/test_new_feature.py
@pytest.mark.asyncio
async def test_typing_event_broadcast():
    # Simulate Voxta event
    # Verify gateway broadcasts to subscribed clients
    pass
```

## Code Conventions

### Naming

```python
# Events: past tense, describing what happened
"chat_started"      # ✅ Good
"start_chat"        # ❌ Bad (sounds like a command)

# HTTP endpoints: semantic action from caller's perspective
POST /dialogue      # ✅ Good
POST /send_message  # ❌ Bad (too Voxta-specific)

# Methods: verb_noun
async def send_dialogue(...)       # ✅ Good
async def dialogue_sender(...)     # ❌ Bad
```

### Error Handling

```python
# Gateway should be resilient - log and continue
async def _on_some_event(self, data: dict):
    try:
        # process
    except Exception as e:
        self.logger.error(f"Error processing event: {e}")
        # Don't re-raise - keep gateway running
```

### Logging

```python
# Use appropriate levels
self.logger.debug("Processing chunk...")     # Verbose, dev only
self.logger.info("Chat started")             # Normal operations
self.logger.warning("Client disconnected")   # Noteworthy but not error
self.logger.error("Voxta connection failed") # Actual problems
```

## Common Mistakes to Avoid

### ❌ Adding "Convenience" Logic

```python
# DON'T DO THIS
@app.post("/start_chat_and_wait_for_ready")
async def start_chat_and_wait():
    await bridge.start_chat(...)
    while state.ai_state != AIState.IDLE:
        await asyncio.sleep(0.1)  # Business logic in gateway!
    return {"status": "ready"}
```

The downstream app should:
1. Call start_chat
2. Subscribe to state changes
3. Decide when to proceed

### ❌ Caching Derived Business State

```python
# DON'T DO THIS
class GatewayState:
    @property
    def can_send_message(self):
        return self.ai_state == AIState.IDLE and not self.external_speaker_active
```

Different apps have different rules about when to send messages. This is a business decision.

### ❌ Hardcoding App Behavior

```python
# DON'T DO THIS
async def send_dialogue(self, text: str, source: str):
    if source == "game":
        await self.external_speaker_start("game")  # App-specific flow!
    await self.bridge.send_message(...)
```

The gateway doesn't know app-specific flows. The game-relay should call `external_speaker_start` itself.

### ❌ Exposing Internal IDs

```python
# DON'T DO THIS
def to_snapshot(self):
    return {
        "chat_id": self.chat_id,      # Internal detail
        "session_id": self.session_id, # Internal detail
        ...
    }

# DO THIS
def to_snapshot(self):
    return {
        "chat_active": self.chat_id is not None,  # What clients need
        ...
    }
```

## Testing Guidelines

### Unit Tests

Test components in isolation:

```python
def test_sentence_buffer_emits_complete_sentences():
    sentences = []
    
    async def on_sentence(text, char_id, msg_id):
        sentences.append(text)
    
    buffer = SentenceBuffer(on_sentence)
    await buffer.process_chunk("msg-1", "char-1", "Hello! How are you? ")
    
    assert "Hello!" in sentences
    assert "How are you?" in sentences
```

### Integration Tests

Test with mock Voxta:

```python
async def test_chat_lifecycle_events():
    # Start gateway with mock voxta
    # Simulate chatStarted event
    # Verify clients receive chat_started
    # Simulate chatClosed event
    # Verify clients receive chat_closed
    pass
```

## Debugging Tips

### Check State First

```bash
curl http://localhost:8081/state | jq
```

### Check Client Subscriptions

```bash
curl http://localhost:8081/debug/clients | jq
```

### Check Event History

```bash
curl http://localhost:8081/debug/voxta/history | jq
```

### Use Debug UI

Open `http://localhost:8081` to see real-time traffic per client.

## Summary

The Gateway is a **translator** and **state broadcaster**. It should be:

- **Dumb:** No autonomous decisions
- **Thin:** Minimal processing, just translation
- **Transparent:** Debug UI shows all traffic
- **Stable:** Changes are rare after initial implementation

If you're adding lots of code to the Gateway, you're probably solving the wrong problem in the wrong place.



