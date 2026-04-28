# New Hardware App Template

A hardware app is product logic built on DeviceKit. It should not modify core session, transport, OTA, or firmware runtime contracts.

## Files To Create

| File | Purpose |
|---|---|
| `manifest.json` | Declarative app identity, screens, actions, adapters, models, safety policy |
| `app.py` | App class implementing `boot()` and `handle()` |
| `my_app_skills/` | Product-specific skills such as payment, alerts, trading, sensors, approvals |
| `screens/` | Optional app-specific screen builders or UI payload helpers |

## Built-In Reference Templates

Use the CLI to create a starter app from any template:

```bash
PYTHONPATH=ava-devicekit/backend python3 -m ava_devicekit.cli init-app ./my-app --type depin_reward_device
```

| Type | App ID | Purpose |
|---|---|---|
| `starter` | configurable | Minimal app skeleton |
| `payment` / `payment_terminal` | `payment_terminal` | Solana Pay / PayFi hardware approval terminal |
| `alert` / `token_alert` | `token_alert` | Token or market alert device |
| `sensor` / `sensor_registry` | `sensor_registry` | Basic sensor registration flow |
| `depin` / `solana_ai_depin_device` | `solana_ai_depin_device` | Generic Solana AI DePIN reference app |
| `depin_reward_device` / `depin-reward` | `depin_reward_device` | Device identity, oracle verification, reward claim flow |
| `sensor_oracle_device` / `sensor-oracle` | `sensor_oracle_device` | WSS/HTTP telemetry, oracle, data-anchor flow |
| `onchain_event_listener` / `event-listener` | `onchain_event_listener` | Solana account/program/memo event -> display/TTS/actuator flow |
| `hardware_signer_approval` / `signer` | `hardware_signer_approval` | Optional physical approval signer pattern |

## Minimal App Responsibilities

1. Load a manifest.
2. Keep `AppContext` current.
3. Convert `DeviceMessage` into `ScreenPayload`, `ActionDraft`, or `ActionResult`.
4. Use adapters/providers/services for chain/model/data behavior.
5. Keep product logic out of framework core.
6. Use `ActionDraft` and physical confirmation for payments, trades, signatures, reward claims, and physical actuation.
7. Include page context and selected/cursor data in voice and input actions.

Use `manifest.template.json` as the minimal starting point, or a reference app under `examples/apps/` for a product-shaped template.
