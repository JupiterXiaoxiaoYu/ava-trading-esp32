# DeviceKit Legacy Planning Folder

The implementation source of truth is now `ava-devicekit/`. This directory is
kept only for older planning artifacts that predate the clean framework split.
Do not add new runtime code here.

## Current Source Of Truth

| Area | Path |
|---|---|
| Backend framework | `ava-devicekit/backend/ava_devicekit/` |
| Ava Box manifest | `ava-devicekit/apps/ava_box/manifest.json` |
| Firmware runtime boundary | `ava-devicekit/firmware/` |
| Shared UI runtime | `ava-devicekit/shared_ui/` |
| Schemas | `ava-devicekit/schemas/` |
| Capability inventory | `ava-devicekit/docs/legacy-capability-inventory.md` |

## Migration Rule

Ava DeviceKit code must use DeviceKit-owned contracts: `DeviceSession`,
`DeviceMessage`, `ScreenPayload`, app manifests, provider interfaces, and app
skills. Older server, firmware, and shared trees may be used as behavior
references only; they are not public framework APIs.
