# Solana AI DePIN Device

Reference app template for an ESP32 device that uses Ava DeviceKit as a Solana AI DePIN framework.

It demonstrates:

| Area | Template behavior |
|---|---|
| Device identity | DeviceKit control plane provisions and registers devices before runtime use. |
| Solana boundary | The app emits Solana action/proof drafts; signing/execution stays in backend or external wallet layers. |
| Physical confirmation | `device.register` and `proof.submit` require a hardware confirmation step. |
| AI context | Screen payloads expose device/project/status context so the model router can reason about the current page. |
| Hardware portability | The manifest declares input/output capabilities without requiring a specific button or joystick layout. |

Use it as a starting point for sensor devices, physical approval terminals, payment devices, or app-specific proof hardware.
