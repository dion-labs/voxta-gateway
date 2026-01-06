# Voxta Gateway

**The single point of contact between your applications and Voxta.**

The Voxta Gateway is a state-mirroring middleware that sits between the Voxta conversational AI platform and your downstream applications. It provides high-level semantic APIs that hide Voxta's internal complexity, making it easy to build chat overlays, avatar bridges, game integrations, and more.

## Why Use the Gateway?

### Before Gateway
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Avatar Bridge│     │ Chat Overlay │     │ Game Relay   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                     ┌──────▼───────┐
                     │    Voxta     │  ← Each app needs to understand
                     │   (SignalR)  │    low-level Voxta protocol
                     └──────────────┘
```

### With Gateway
```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Avatar Bridge│     │ Chat Overlay │     │ Game Relay   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            │
                    ┌───────▼────────┐
                    │ Voxta Gateway  │  ← High-level APIs
                    │ (HTTP + WS)    │    State snapshots
                    └───────┬────────┘    Event filtering
                            │
                     ┌──────▼───────┐
                     │    Voxta     │
                     └──────────────┘
```

## Key Features

| Feature | Description |
|---------|-------------|
| **State Snapshots** | Apps receive full state on connect - no startup order dependency |
| **High-Level APIs** | Semantic actions like `external_speaker_start` instead of raw `interrupt()` |
| **Event Subscriptions** | Apps only receive events they care about |
| **Sentence Buffering** | Streaming text is processed into complete sentences for TTS |
| **Debug UI** | Per-client traffic visualization at `http://localhost:8081` |

## Quick Example

=== "Using GatewayClient"

    ```python
    import asyncio
    from voxta_gateway import GatewayClient

    async def main():
        client = GatewayClient(
            gateway_url="http://localhost:8081",
            client_id="my-app",
            events=["chat_started", "dialogue_received", "ai_state_changed"]
        )
        
        @client.on("dialogue_received")
        async def on_dialogue(data):
            print(f"[{data.get('source')}] {data.get('text')}")
        
        @client.on("chat_started")
        async def on_chat_started(data):
            print("Chat started! Ready to send messages.")
            await client.send_dialogue("Hello from my app!")
        
        await client.start()

    asyncio.run(main())
    ```

=== "HTTP Only"

    ```python
    import httpx

    # Check if ready to send messages
    state = httpx.get("http://localhost:8081/state").json()
    if state["chat_active"]:
        # Send dialogue
        httpx.post("http://localhost:8081/dialogue", json={
            "text": "Hello from my app!",
            "source": "user"
        })
    ```

## Next Steps

- [Getting Started](getting-started.md) - Install and run the gateway
- [Building Clients](client-guide.md) - Best practices for downstream apps
- [Migration Guide](migration-guide.md) - Moving existing apps to the Gateway
- [API Reference](api.md) - Complete endpoint documentation
- [Development Guide](development-guide.md) - Contributing and architecture

