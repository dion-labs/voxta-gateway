# API Reference

The Voxta Gateway exposes two interfaces:

1. **HTTP REST API** - For sending actions and querying state
2. **WebSocket API** - For receiving real-time events

## Base URL

```
HTTP:  http://localhost:8081
WS:    ws://localhost:8081/ws
```

## Quick Reference

### HTTP Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/state` | GET | Current state snapshot |
| `/dialogue` | POST | Send dialogue |
| `/context` | POST | Send context update |
| `/external_speaker_start` | POST | Signal external speaker started |
| `/external_speaker_stop` | POST | Signal external speaker stopped |
| `/tts_playback_start` | POST | Signal TTS started |
| `/tts_playback_complete` | POST | Signal TTS finished |
| `/debug/clients` | GET | List connected clients |
| `/debug/clients/{id}/history` | GET | Client message history |
| `/debug/voxta/history` | GET | Raw Voxta event history |

### WebSocket Events

| Event | Description | Typical Subscribers |
|-------|-------------|---------------------|
| `chat_started` | Chat became active | All clients |
| `chat_closed` | Chat was closed | All clients |
| `dialogue_received` | Message in chat | Chat overlays |
| `sentence_ready` | Complete sentence for TTS | Avatar bridges |
| `ai_state_changed` | AI state transition | Most clients |
| `external_speaker_started` | External speaker began | Avatar bridges |
| `external_speaker_stopped` | External speaker ended | Avatar bridges |
| `app_trigger` | Animation/expression command | Avatar bridges |
| `characters_updated` | Character list changed | Avatar bridges |

## Detailed Documentation

- [HTTP Endpoints](api/http.md) - Complete HTTP API reference
- [WebSocket Protocol](api/websocket.md) - Connection and messaging
- [Event Types](api/events.md) - All event payloads

