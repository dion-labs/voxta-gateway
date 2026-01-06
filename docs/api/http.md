# HTTP Endpoints

All endpoints accept and return JSON.

## Health & State

### GET /health

Check if the gateway is running and connected to Voxta.

**Response:**
```json
{
  "status": "ok",
  "voxta_connected": true
}
```

### GET /state

Get the current gateway state snapshot.

**Response:**
```json
{
  "connected": true,
  "chat_active": true,
  "ai_state": "idle",
  "current_speaker_id": null,
  "external_speaker_active": false,
  "external_speaker_source": null,
  "characters": [
    {
      "id": "char-uuid",
      "name": "Apex",
      "creator_notes": null,
      "text_gen_service": null
    }
  ]
}
```

**State Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `connected` | boolean | Is gateway connected to Voxta? |
| `chat_active` | boolean | Is there an active chat session? |
| `ai_state` | string | Current AI state: `idle`, `thinking`, `speaking` |
| `current_speaker_id` | string? | Character ID currently speaking |
| `external_speaker_active` | boolean | Is an external speaker (game, user) active? |
| `external_speaker_source` | string? | Source of external speaker if active |
| `characters` | array | Characters in the current chat |

---

## High-Level Actions

### POST /dialogue

Send dialogue that appears in chat and may trigger AI response.

**Request:**
```json
{
  "text": "Hello, how are you?",
  "source": "user",
  "author": null,
  "immediate_reply": true
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The dialogue text |
| `source` | string | No | Source: `user`, `game`, `twitch` (default: `user`) |
| `author` | string | No | Author name (for Twitch usernames, NPC names) |
| `immediate_reply` | boolean | No | Should AI respond immediately? (default: based on source) |

**Source Behavior:**

| Source | Default `immediate_reply` | Formatting |
|--------|---------------------------|------------|
| `user` | `true` | Sent as-is |
| `game` | `false` | `[GAME] {author}: {text}` or `[GAME] {text}` |
| `twitch` | `false` | `[TWITCH] {author}: {text}` or `[TWITCH] {text}` |

**Response:**
```json
{"status": "ok"}
```

---

### POST /context

Send context update (not shown in chat, but AI knows about it).

**Request:**
```json
{
  "key": "chessboard",
  "content": "FEN: rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3",
  "description": "White played e4"
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `key` | string | Yes | Unique identifier for this context type |
| `content` | string | Yes | The context data (FEN, game state, etc.) |
| `description` | string | No | Optional spoken summary for AI |

**Response:**
```json
{"status": "ok"}
```

---

### POST /external_speaker_start

Signal that an external speaker started talking. This interrupts the AI if it's speaking or thinking.

**Request:**
```json
{
  "source": "game",
  "reason": "npc_dialogue"
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | string | Yes | Who is speaking: `game`, `user` |
| `reason` | string | No | Optional reason for logging |

**Effect:**
- Interrupts AI if speaking/thinking
- Prevents AI from generating new responses
- Broadcasts `external_speaker_started` event

**Response:**
```json
{"status": "ok"}
```

---

### POST /external_speaker_stop

Signal that external speaker stopped talking.

**Request:**
```json
{
  "trigger_response": true
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trigger_response` | boolean | No | Should AI respond? (default: `true`) |

**Effect:**
- Releases the "busy" state
- If `trigger_response` is true, requests AI to respond
- Broadcasts `external_speaker_stopped` event

**Response:**
```json
{"status": "ok"}
```

---

### POST /tts_playback_start

Signal that external TTS playback started (avatar bridge playing audio).

**Request:**
```json
{
  "character_id": "char-uuid",
  "message_id": "msg-uuid"
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `character_id` | string | Yes | Which character is speaking |
| `message_id` | string | No | Which message is being spoken |

**Effect:**
- Updates AI state to `speaking`
- Notifies Voxta that speech is playing

**Response:**
```json
{"status": "ok"}
```

---

### POST /tts_playback_complete

Signal that external TTS playback finished.

**Request:**
```json
{
  "character_id": "char-uuid",
  "message_id": "msg-uuid"
}
```

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `character_id` | string | Yes | Which character finished speaking |
| `message_id` | string | No | Which message was spoken |

**Effect:**
- Updates AI state to `idle` (unless external speaker active)
- Notifies Voxta that speech finished

**Response:**
```json
{"status": "ok"}
```

---

## Debug Endpoints

### GET /debug/clients

List all connected WebSocket clients.

**Response:**
```json
{
  "avatar-bridge-001": {
    "client_id": "avatar-bridge-001",
    "subscribed_events": ["sentence_ready", "app_trigger"],
    "message_count": 42,
    "connected_at": 1704393600.0,
    "last_message_at": 1704394200.0
  },
  "chat-overlay-001": {
    "client_id": "chat-overlay-001",
    "subscribed_events": ["dialogue_received"],
    "message_count": 15,
    "connected_at": 1704393650.0,
    "last_message_at": 1704394180.0
  }
}
```

---

### GET /debug/clients/{client_id}/history

Get message history for a specific client.

**Response:**
```json
[
  {
    "type": "sentence_ready",
    "data": {"text": "Hello there!", "character_id": "char-uuid"},
    "timestamp": 1704394200.0
  },
  {
    "type": "ai_state_changed",
    "data": {"old_state": "thinking", "new_state": "speaking"},
    "timestamp": 1704394199.0
  }
]
```

---

### GET /debug/voxta/history

Get raw Voxta event history (incoming and outgoing).

**Response:**
```json
[
  {
    "direction": "IN",
    "type": "replyGenerating",
    "data": {"sessionId": "..."},
    "timestamp": 1704394198.0
  },
  {
    "direction": "OUT",
    "type": "speechPlaybackStart",
    "data": {"sessionId": "...", "messageId": "..."},
    "timestamp": 1704394200.0
  }
]
```



