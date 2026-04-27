# Production Deploy

## Services

Run the HTTP gateway and WebSocket gateway behind a reverse proxy:

```bash
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 0.0.0.0 --port 8788 --config runtime.local.json
PYTHONPATH=backend python3 -m ava_devicekit.cli run-legacy-ws --host 0.0.0.0 --port 8787 --config runtime.local.json
```

Use long proxy read timeouts for hardware sessions and keep WebSocket ping enabled through `websocket_ping_interval` and `websocket_ping_timeout`.

## Runtime Safety

| Area | Rule |
|---|---|
| Secrets | Store only environment variable names in config files |
| Wallet signing | Keep user-key custody outside ESP32 unless a secure element/wallet design is added |
| AI actions | Use deterministic routing for known actions and require physical confirmation for high-risk actions |
| OTA | Serve firmware only from the configured `firmware_bin_dir` |
| Admin APIs | Expose sanitized runtime state only; never return secret values |
