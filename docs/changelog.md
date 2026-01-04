# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-01-04

### Added

- Initial release of Voxta Gateway
- **Core Features:**
  - State mirroring from Voxta
  - High-level semantic APIs (`/dialogue`, `/context`, `/external_speaker_start`, etc.)
  - WebSocket with selective event subscriptions
  - Sentence buffering for TTS
  - Debug UI with per-client traffic visualization

- **HTTP Endpoints:**
  - `GET /health` - Health check
  - `GET /state` - State snapshot
  - `POST /dialogue` - Send dialogue
  - `POST /context` - Send context
  - `POST /external_speaker_start` - Start external speaker
  - `POST /external_speaker_stop` - Stop external speaker
  - `POST /tts_playback_start` - TTS started
  - `POST /tts_playback_complete` - TTS finished
  - `GET /debug/clients` - List connected clients
  - `GET /debug/clients/{id}/history` - Client history
  - `GET /debug/voxta/history` - Voxta event history

- **WebSocket Events:**
  - `chat_started` / `chat_closed` - Chat lifecycle
  - `dialogue_received` - Messages in chat
  - `sentence_ready` - Complete sentences for TTS
  - `ai_state_changed` - AI state transitions
  - `external_speaker_started` / `external_speaker_stopped` - External speaker
  - `app_trigger` - Actions/animations
  - `characters_updated` - Character list changes
  - `voxta_connected` / `voxta_disconnected` - Connection status

- **Documentation:**
  - Getting Started guide
  - Client building guide with best practices
  - Development guide for contributors
  - Complete API reference

### Architecture

- State-Mirror model: Gateway observes, never decides
- Consumer-First features: Only implement what's needed
- High-level semantic APIs hiding Voxta internals

