# Getting Started

This guide will get you up and running with the Voxta Gateway in under 5 minutes.

## Prerequisites

- Python 3.10 or higher
- Voxta server running (default: `http://localhost:5384`)

## Installation

### From PyPI (Recommended)

```bash
pip install voxta-gateway
```

### From Source

```bash
git clone https://github.com/dion-labs/voxta-gateway.git
cd voxta-gateway/main
pip install -e ".[dev]"
```

## Running the Gateway

### Basic Usage

```bash
# Using default settings (Voxta at localhost:5384, Gateway on port 8081)
voxta-gateway
```

### With Custom Configuration

```bash
# Specify Voxta URL and port
VOXTA_URL=http://192.168.1.100:5384 GATEWAY_PORT=8081 voxta-gateway
```

### Using Uvicorn Directly

```bash
VOXTA_URL=http://localhost:5384 uvicorn voxta_gateway.main:app --host 0.0.0.0 --port 8081
```

## Verify It's Working

### 1. Check Health Endpoint

```bash
curl http://localhost:8081/health
```

Expected response:
```json
{"status": "ok", "voxta_connected": true}
```

### 2. Check State

```bash
curl http://localhost:8081/state
```

Expected response:
```json
{
  "connected": true,
  "chat_active": false,
  "ai_state": "idle",
  "external_speaker_active": false,
  "external_speaker_source": null,
  "characters": []
}
```

### 3. Open Debug UI

Navigate to [http://localhost:8081](http://localhost:8081) in your browser to see the real-time debug interface.

## Your First Client

Here's a minimal Python client that listens for events:

```python
import asyncio
import websockets
import json

async def main():
    uri = "ws://localhost:8081/ws"
    
    async with websockets.connect(uri) as websocket:
        # Step 1: Subscribe to events
        await websocket.send(json.dumps({
            "type": "subscribe",
            "client_id": "my-first-client",
            "events": ["chat_started", "chat_closed", "dialogue_received"]
        }))
        
        # Step 2: Receive initial state snapshot
        response = await websocket.recv()
        snapshot = json.loads(response)
        print(f"Connected! Chat active: {snapshot['state']['chat_active']}")
        
        # Step 3: Listen for events
        print("Listening for events... (start a chat in Voxta)")
        async for message in websocket:
            event = json.loads(message)
            print(f"[{event['type']}] {event.get('data', {})}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it:
```bash
pip install websockets
python my_client.py
```

## Configuration Reference

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `VOXTA_URL` | `http://localhost:5384` | Voxta server URL |
| `GATEWAY_PORT` | `8081` | Port for the Gateway HTTP/WS server |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Troubleshooting

### "voxta_connected": false

The gateway couldn't connect to Voxta. Check that:

1. Voxta is running
2. The `VOXTA_URL` is correct
3. No firewall is blocking the connection

### WebSocket connection rejected

Make sure you send a subscription message as the first message:

```json
{"type": "subscribe", "client_id": "your-app", "events": ["all"]}
```

### No events received

1. Check that a chat is active in Voxta
2. Verify you're subscribed to the right events
3. Check the Debug UI at `http://localhost:8081` to see what events are flowing

## Next Steps

- [Building Clients](client-guide.md) - Learn best practices for robust clients
- [API Reference](api.md) - Explore all available endpoints and events

