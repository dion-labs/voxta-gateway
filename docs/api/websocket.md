# WebSocket Protocol

The WebSocket API provides real-time event streaming with selective subscriptions.

## Connection

Connect to `ws://localhost:8081/ws`

## Protocol Flow

```
Client                                    Gateway
  │                                          │
  │──────── Connect to /ws ─────────────────>│
  │                                          │
  │<──────── Connection Accepted ────────────│
  │                                          │
  │──────── Subscribe Message ──────────────>│
  │  {                                       │
  │    "type": "subscribe",                  │
  │    "client_id": "my-app",                │
  │    "events": ["chat_started", ...]       │
  │  }                                       │
  │                                          │
  │<──────── State Snapshot ─────────────────│
  │  {                                       │
  │    "type": "snapshot",                   │
  │    "state": { ... }                      │
  │  }                                       │
  │                                          │
  │<──────── Events (ongoing) ───────────────│
  │  {                                       │
  │    "type": "chat_started",               │
  │    "data": { ... },                      │
  │    "timestamp": 1704394200.0             │
  │  }                                       │
  │                                          │
```

## Messages

### Subscribe (Client → Server)

**Must be the first message** sent after connection.

```json
{
  "type": "subscribe",
  "client_id": "my-unique-client-id",
  "events": ["chat_started", "chat_closed", "dialogue_received"]
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Must be `"subscribe"` |
| `client_id` | string | No | Unique ID for this client (auto-generated if omitted) |
| `events` | array | No | Events to subscribe to (default: `["all"]`) |

**Special `events` values:**

- `["all"]` - Receive all events (useful for debugging)
- `[]` - Receive no events (HTTP-only client)

---

### Snapshot (Server → Client)

Sent immediately after successful subscription.

```json
{
  "type": "snapshot",
  "state": {
    "connected": true,
    "chat_active": true,
    "ai_state": "idle",
    "current_speaker_id": null,
    "external_speaker_active": false,
    "external_speaker_source": null,
    "characters": [
      {"id": "char-uuid", "name": "Apex"}
    ]
  }
}
```

This allows clients to know the current state immediately, regardless of when they connected.

---

### Event (Server → Client)

Events are sent when subscribed events occur.

```json
{
  "type": "event_type",
  "data": { ... },
  "timestamp": 1704394200.0
}
```

See [Events](events.md) for all event types and their payloads.

---

### Ping/Pong (Client ↔ Server)

Optional heartbeat mechanism.

**Client sends:**
```json
{"type": "ping"}
```

**Server responds:**
```json
{"type": "pong"}
```

---

### Update Subscription (Client → Server)

Update event subscriptions without reconnecting.

```json
{
  "type": "subscribe",
  "events": ["chat_started", "chat_closed", "sentence_ready"]
}
```

Note: Send a new subscribe message (without `client_id`) to update subscriptions.

---

## Example Client

### Python (websockets)

```python
import asyncio
import websockets
import json

async def main():
    async with websockets.connect("ws://localhost:8081/ws") as ws:
        # Subscribe
        await ws.send(json.dumps({
            "type": "subscribe",
            "client_id": "python-example",
            "events": ["chat_started", "dialogue_received"]
        }))
        
        # Get snapshot
        snapshot = json.loads(await ws.recv())
        print(f"Initial state: {snapshot['state']}")
        
        # Listen for events
        async for message in ws:
            event = json.loads(message)
            print(f"Event: {event['type']} - {event.get('data', {})}")

asyncio.run(main())
```

### JavaScript

```javascript
const ws = new WebSocket("ws://localhost:8081/ws");

ws.onopen = () => {
    ws.send(JSON.stringify({
        type: "subscribe",
        client_id: "js-example",
        events: ["chat_started", "dialogue_received"]
    }));
};

ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    
    if (msg.type === "snapshot") {
        console.log("Initial state:", msg.state);
    } else {
        console.log("Event:", msg.type, msg.data);
    }
};
```

## Connection Lifecycle

### Reconnection

If the connection drops, clients should:

1. Wait with backoff (e.g., 5 seconds)
2. Reconnect and re-subscribe
3. Use the new snapshot to sync state

```python
async def run_with_reconnect():
    while True:
        try:
            async with websockets.connect("ws://localhost:8081/ws") as ws:
                await subscribe(ws)
                await listen(ws)
        except websockets.ConnectionClosed:
            print("Disconnected, reconnecting in 5s...")
            await asyncio.sleep(5)
```

### Duplicate Client IDs

If a client connects with the same `client_id` as an existing connection, the old connection is closed. This allows clients to reconnect cleanly.

## Error Handling

### Invalid First Message

If the first message is not a valid subscribe message:

```
WebSocket closed with code 4000: "First message must be subscribe"
```

### Subscription Timeout

If no subscribe message is received within 10 seconds:

```
WebSocket closed with code 4000: "Subscription timeout"
```



