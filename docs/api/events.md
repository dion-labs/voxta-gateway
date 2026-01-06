# Events

All events follow this structure:

```json
{
  "type": "event_name",
  "data": { ... },
  "timestamp": 1704394200.0
}
```

## Chat Lifecycle Events

### chat_started

A chat session became active. Safe to start sending messages.

```json
{
  "type": "chat_started",
  "data": {
    "characters": [
      {"id": "char-uuid", "name": "Apex", "creator_notes": null, "text_gen_service": null}
    ]
  },
  "timestamp": 1704394200.0
}
```

**When to use:** Check this to know when you can start sending dialogue/context.

---

### chat_closed

The chat session was closed. Stop sending messages.

```json
{
  "type": "chat_closed",
  "data": {},
  "timestamp": 1704394500.0
}
```

**When to use:** Clear any queued messages, reset UI state.

---

## AI State Events

### ai_state_changed

The AI transitioned between states.

```json
{
  "type": "ai_state_changed",
  "data": {
    "old_state": "idle",
    "new_state": "thinking"
  },
  "timestamp": 1704394200.0
}
```

**States:**

| State | Description |
|-------|-------------|
| `idle` | Not doing anything, ready for input |
| `thinking` | Generating a reply |
| `speaking` | TTS is playing (Voxta or bridge-controlled) |

**When to use:** 
- Show "typing" indicator when `thinking`
- Know when to wait before interrupting
- Track conversation flow

---

## Dialogue Events

### dialogue_received

A message appeared in the chat (user, AI, or external source).

```json
{
  "type": "dialogue_received",
  "data": {
    "message_id": "msg-uuid",
    "text": "Hello, how can I help you?",
    "character_id": "char-uuid",
    "source": "ai",
    "author": null
  },
  "timestamp": 1704394200.0
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `message_id` | string? | Unique message ID |
| `text` | string | The message content |
| `character_id` | string? | Character who sent (for AI messages) |
| `source` | string | `ai`, `user`, `game`, `twitch` |
| `author` | string? | Author name (for external sources) |

**When to use:** Display messages in chat overlay.

---

### sentence_ready

A complete sentence is ready for TTS.

```json
{
  "type": "sentence_ready",
  "data": {
    "text": "Hello there!",
    "character_id": "char-uuid",
    "message_id": "msg-uuid"
  },
  "timestamp": 1704394200.0
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Complete sentence (ends with punctuation) |
| `character_id` | string | Character speaking |
| `message_id` | string | Which message this is part of |

**When to use:** 
- Queue sentence for TTS generation
- Trigger avatar lip-sync

**Note:** Multiple `sentence_ready` events may come from a single message as it streams.

---

## External Speaker Events

### external_speaker_started

An external speaker (game NPC, user microphone) started talking.

```json
{
  "type": "external_speaker_started",
  "data": {
    "source": "game",
    "reason": "npc_dialogue"
  },
  "timestamp": 1704394200.0
}
```

**When to use:**
- Stop queued TTS playback immediately
- Clear pending sentence queue
- Show visual indicator that someone else is speaking

---

### external_speaker_stopped

External speaker finished talking.

```json
{
  "type": "external_speaker_stopped",
  "data": {
    "source": "game"
  },
  "timestamp": 1704394210.0
}
```

**When to use:**
- Resume normal operation
- AI may start responding (if `trigger_response` was true)

---

## Character Events

### characters_updated

The character list changed (new chat, participant added/removed).

```json
{
  "type": "characters_updated",
  "data": {
    "characters": [
      {"id": "char-1", "name": "Apex", "creator_notes": null, "text_gen_service": null},
      {"id": "char-2", "name": "Luna", "creator_notes": null, "text_gen_service": null}
    ]
  },
  "timestamp": 1704394200.0
}
```

**When to use:**
- Preload avatar models
- Update character selection UI
- Adjust multi-character handling

---

## Action Events

### app_trigger

An action/trigger was invoked (expression, animation, etc.).

```json
{
  "type": "app_trigger",
  "data": {
    "name": "SetAvatar",
    "arguments": {
      "expression": "happy",
      "intensity": 0.8
    },
    "character_id": "char-uuid"
  },
  "timestamp": 1704394200.0
}
```

**Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Action name |
| `arguments` | object | Action parameters |
| `character_id` | string? | Which character triggered this |

**When to use:**
- Trigger avatar expressions/animations
- Execute custom actions defined in Voxta

---

## Connection Events

### voxta_connected

Gateway successfully connected to Voxta.

```json
{
  "type": "voxta_connected",
  "data": {},
  "timestamp": 1704394200.0
}
```

---

### voxta_disconnected

Gateway lost connection to Voxta.

```json
{
  "type": "voxta_disconnected",
  "data": {},
  "timestamp": 1704394200.0
}
```

**When to use:**
- Show connection status indicator
- Pause sending until reconnected

---

## Subscription Recommendations

### Chat Overlay
```json
["chat_started", "chat_closed", "dialogue_received"]
```

### Avatar Bridge
```json
["chat_started", "chat_closed", "sentence_ready", "ai_state_changed", 
 "external_speaker_started", "external_speaker_stopped", 
 "app_trigger", "characters_updated"]
```

### Game Dialogue Relay
```json
["chat_started", "chat_closed", "ai_state_changed"]
```

### Twitch Chat Relay
```json
["chat_started", "chat_closed"]
```

### Debug Client
```json
["all"]
```



