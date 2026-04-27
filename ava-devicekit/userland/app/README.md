# New Hardware App Template

A hardware app is product logic built on DeviceKit. It should not modify core
session, transport, OTA, or firmware runtime contracts.

## Files To Create

| File | Purpose |
|---|---|
| `manifest.json` | Declarative app identity, screens, actions, adapters, models, safety policy |
| `my_app.py` | App class implementing `boot()` and `handle()` |
| `my_app_skills/` | Product-specific skills such as payment, alerts, trading, sensors, approvals |
| `screens/` | Optional app-specific screen builders or UI payload helpers |

## Minimal App Responsibilities

1. Load a manifest.
2. Keep `AppContext` current.
3. Convert `DeviceMessage` into `ScreenPayload`, `ActionDraft`, or `ActionResult`.
4. Use adapters/providers for chain/model/data behavior.
5. Keep product logic out of framework core.

Use `manifest.template.json` as the starting point.
