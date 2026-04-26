# Legacy Runtime Extraction Plan

Ava DeviceKit is moving Ava Box capabilities into our own framework. The clean implementation now starts in `ava-devicekit/`; the old server/firmware/shared trees are references until the required behavior is replaced.

## Target Boundary

| Capability | New owner |
|---|---|
| Hardware app manifest | `ava-devicekit/apps/ava_box/manifest.json` |
| App/session types | `ava-devicekit/backend/ava_devicekit/core/` |
| Chain/helper adapter interface | `ava-devicekit/backend/ava_devicekit/adapters/base.py` |
| Solana implementation | `ava-devicekit/backend/ava_devicekit/adapters/solana.py` |
| Reference app routing | `ava-devicekit/backend/ava_devicekit/apps/ava_box.py` |
| Device session gateway | `ava-devicekit/backend/ava_devicekit/gateway/` |
| Screen/action schemas | `ava-devicekit/schemas/` |

## Extraction Rule

Do not import legacy runtime modules from `ava-devicekit/`. In particular, the clean framework must not depend on legacy connection classes, tool registration, or provider lifecycle code.

| Legacy concept | Replacement |
|---|---|
| `ConnectionHandler` | `DeviceSession` + `AppContext` |
| tool registration callbacks | `AvaBoxApp.handle(DeviceMessage)` |
| monolithic tool file | `ChainAdapter` + app routing + screen builders |
| direct screen push tasks | `ScreenPayload` returned by app/session |
| provider-specific model config | `ModelRouter` and deployment-injected providers |

## Migration Order

| Step | Outcome |
|---|---|
| 1 | Keep clean backend package compiling independently |
| 2 | Port Solana feed/search/detail/watchlist/draft behavior into `SolanaAdapter` |
| 3 | Route simulator/mock device through `DeviceSession` |
| 4 | Move LVGL screen code behind clean `ScreenPayload` contracts |
| 5 | Replace firmware transport glue with DeviceKit `DeviceMessage` protocol |
| 6 | Retire legacy server paths once online service is running on the clean gateway |
