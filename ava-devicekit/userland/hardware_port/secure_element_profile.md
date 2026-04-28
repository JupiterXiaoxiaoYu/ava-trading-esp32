# Optional Secure Element Profile

This profile is for hardware builders who want stronger device identity or optional signing support. It is not required for every DeviceKit board and it does not change the default custody model: ESP32 devices are physical interaction and confirmation surfaces unless an app explicitly implements signer behavior.

## Recommended Hardware Capabilities

| Capability | Purpose |
|---|---|
| Secure element or protected key store | Stores device identity keys or optional app-specific signing keys |
| Display | Shows transaction, proof, payment, or registration summary before approval |
| At least two physical controls | Confirm and cancel must be physically distinct enough to avoid accidental approval |
| LED / buzzer / haptic feedback | Indicates signing, network, error, and confirmation state |
| USB serial or debug transport | Manufacturing, diagnostics, and recovery |
| Secure boot / flash encryption when available | Reduces firmware tampering risk |

## Key Separation

| Key Type | Stored On Device? | Used For | Notes |
|---|---|---|---|
| Device identity key | Optional yes | Device registration, challenge-response, signed telemetry/proofs | Does not control user assets |
| User asset wallet key | Default no | Trading, payment, custody | Prefer external wallet or backend/proxy wallet unless building a signer app |
| App-specific signer key | Optional only in signer app | Message/transaction signatures after physical approval | Use secure element if available |

## Challenge-Response Registration

Recommended flow:

```text
Admin provisions device
  -> Device registers and receives challenge
  -> Secure element signs challenge
  -> Backend stores device_public_key and verification result
  -> Runtime messages can include device signatures for proofs/telemetry
```

Board ports can expose this through:

- `device_public_key` in `ava_board_config_t`
- `sign_challenge()` in `ava_board_io_t`
- `ava_board_send_challenge_response()` in the template

## Physical Confirmation Rules

1. Always show action type, recipient/program, amount/value, network, and risk before approval.
2. Confirm and cancel must both be available on hardware.
3. Signing requests must include a request id and a stable hash/summary.
4. Never sign opaque payloads without a user-readable summary.
5. App-level signer flows should use `ActionDraft` and `hardware_signer_approval`; trading/payment apps should not silently become signer apps.

## Profile Labels

Use these profile strings in `board.profile.json` or runtime config:

| Profile | Meaning |
|---|---|
| `none` | No protected key hardware |
| `nvs_device_key` | Device identity key in ESP32 NVS; acceptable for prototypes only |
| `secure_element_device_key` | Device identity key in secure element |
| `secure_element_signer` | App-specific signer key in secure element; requires explicit signer app UX |
