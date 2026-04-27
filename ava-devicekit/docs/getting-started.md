# Getting Started

## Install For Local Development

```bash
cd ava-devicekit
python3 -m pip install -e .[dev,websocket]
```

## Run The Reference App Offline

```bash
PYTHONPATH=backend python3 examples/demo_flow.py
PYTHONPATH=backend python3 -m ava_devicekit.cli run-http --host 127.0.0.1 --port 8788 --mock
```

Then send device messages to `POST /device/message` or inspect state at `GET /device/state`.

## Runtime Configuration

Copy `userland/runtime.example.json`, set public URLs, and configure providers through `providers.asr`, `providers.llm`, and `providers.tts`. Secrets are referenced by environment variable names only; they are not stored in the JSON file.

```bash
export AVE_API_KEY=...
export DASHSCOPE_API_KEY=...
export OPENAI_API_KEY=...
PYTHONPATH=backend python3 -m ava_devicekit.cli validate --config runtime.local.json
```

## Admin Endpoints

| Path | Purpose |
|---|---|
| `/admin/capabilities` | Machine-readable framework/userland capability map |
| `/admin/runtime` | Sanitized runtime settings without secret values |
| `/admin/apps` | Active app manifest list |
