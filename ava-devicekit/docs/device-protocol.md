# Device Protocol

DeviceKit uses JSON text frames plus optional binary audio frames. The protocol is hardware-agnostic: board ports convert GPIO, joystick, touch, microphone, and display events into these frames.

## Device To Server Frames

| Frame | Required Fields | Purpose |
|---|---|---|
| `hello` | `type`, optional `device_id`, `app_id`, `audio_params` | Opens a session and receives the boot display payload. |
| `ping` | `type` | Keeps connection state fresh; server returns `pong`. |
| `ack` / `message_ack` | `type`, `message_id` | Confirms that an outbound payload was applied by firmware/UI. |
| `key_action` | `type`, `action` | Sends a direct app action such as `portfolio`, `buy`, or `back`. |
| `input_event` | `type`, `source`, `kind`, optional `semantic_action`, `context` | Sends hardware-agnostic input from buttons, joystick, touch, encoder, etc. |
| `screen_context` | `type`, `context` or selection fields | Updates server-side context with current page, cursor, selected row, and visible rows. |
| `listen` | `type`, `state` | Starts/stops/updates voice capture. Binary audio frames are sent between start and stop. |
| `listen_detect` | `type`, `text`, optional `context` | Sends already-detected transcript/wake phrase into app routing. |
| `confirm` | `type`, optional `request_id` | Confirms the pending high-risk action draft. |
| `cancel` / `abort` | `type`, optional `request_id` | Cancels the pending action draft. |
| `signed_tx` | `type`, transaction payload | Optional external-wallet/signer return path. |
| `goodbye` | `type` | Gracefully closes the session. |
| `device_identity` | `type`, `device_id`, optional `device_public_key`, `challenge`, `signature` | Sends device identity or challenge-response material during registration or attestation flows. |
| `device_telemetry` | `type`, `device_id`, `readings`, optional `transport`, `signature` | Sends sensor/proof readings for DePIN, oracle, reward, and data-anchor apps. |

## Server To Device Frames

| Frame | Required Fields | Purpose |
|---|---|---|
| `hello` | `type`, `session_id`, `audio_params`, `devicekit` | Session metadata and negotiated audio parameters. |
| `display` | `type`, `screen`, `data`, optional `context`, `message_id`, `ack_required` | Render a screen payload. |
| `tts` | `type`, `state`, optional `text`, `audio`, `content_type` | TTS lifecycle and optional base64 audio chunks. |
| `stt` | `type`, `state`, `text` | Partial or final transcript echo. |
| `pong` | `type`, `session_id` | Ping response. |
| `ack` | `type`, `message_id`, `ok` | Server acknowledgement of a device ACK frame. |
| `device_command` | `type`, `command`, `payload`, optional `message_id`, `ack_required` | Server command for device runtime behavior, such as `ota_check`. |
| `system` | `type`, `command`, `message` | Protocol/system error. |

## ACK Rule

If a server frame has `message_id` and `ack_required: true`, the device should ACK after the payload has been applied:

```json
{"type":"ack","message_id":"msg_123"}
```

For `display`, ACK after the screen parser/render path succeeds. For `device_command`, ACK after the command is accepted by firmware. Existing Ava Box firmware is still compatible because the server can auto-ack after send, but new board ports should implement explicit ACK.

## OTA Trigger Command

The server can ask an online device to perform its normal OTA check:

```json
{
  "type": "device_command",
  "command": "ota_check",
  "payload": {"reason": "admin_request"},
  "message_id": "msg_...",
  "ack_required": true
}
```

The device should call its existing OTA check routine. Firmware download still happens through `POST /ava/ota/` and `GET /ava/ota/download/{filename}`.

## Context Snapshot Rule

Whenever voice or AI-driven actions depend on what the user is looking at, attach context:

```json
{
  "type": "input_event",
  "source": "button_a",
  "kind": "press",
  "semantic_action": "buy",
  "context": {
    "screen": "spotlight",
    "cursor": 0,
    "selected": {"token_id": "...", "symbol": "SOL", "chain": "solana"},
    "visible_rows": []
  }
}
```

This is the generic mechanism that lets apps and models know the current page, cursor, selected object, and visible data.

## Identity, Telemetry, And Transport Contracts

DeviceKit keeps machine-readable contracts for the Solana AI DePIN patterns added to the framework:

| Contract | Schema | Runtime Use |
|---|---|---|
| Device identity | `schemas/device_identity.schema.json` | Per-device token auth, optional public-key identity, challenge-response hooks, and secure-element profiles. |
| Device telemetry | `schemas/device_telemetry.schema.json` | Signed sensor readings, oracle proofs, reward claims, and HTTP fallback ingestion. |
| Transport profile | `schemas/transport_profile.schema.json` | Board-port heartbeat, reconnect interval, HTTP fallback, ACK, OTA check, and context snapshot capabilities. |
| Developer service | `schemas/developer_service.schema.json` | Server-side API services such as Solana RPC, Solana Pay, oracle, reward distributor, data anchor, gasless transaction, and device ingest. |

Board ports should declare their transport profile in `board.profile.json`. Apps that submit readings should send `device_telemetry` frames with scalar `readings` and include a `signature` when the selected security profile requires signed device data.

## Security Boundary

Devices should never receive backend API keys, wallet secrets, or provider credentials. They receive display payloads, audio, action drafts, and commands. Backend services are configured through server-side env vars and service registry entries.
