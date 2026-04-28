# DePIN Reward Device Reference App

Pattern inspired by Solana DePIN reward examples: a hardware device owns a device identity key, signs telemetry or proof batches, an oracle verifies eligibility, and the device/user physically confirms reward claim drafts.

The ESP32 identity key is for device proof only. User asset custody stays in an external wallet, backend custody service, or app-specific signer boundary.
