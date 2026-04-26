# Firmware Runtime Target

This directory is the target home for Ava DeviceKit's firmware-facing runtime.

The clean framework should expose only these concepts to ESP32 ports:

| Concept | Purpose |
|---|---|
| Device transport | send/receive JSON messages |
| Key mapper | joystick/buttons/FN into `DeviceMessage` actions |
| Audio hooks | microphone input and speaker output routed by deployment |
| Screen runtime | render `ScreenPayload` messages |
| OTA/settings | deployment-managed device lifecycle |

The current production firmware still lives in the repo-level `firmware/` directory while this clean boundary is implemented.
