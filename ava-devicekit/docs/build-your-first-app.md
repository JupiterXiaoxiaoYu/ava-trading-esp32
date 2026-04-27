# Build Your First Hardware App

Create a starter app:

```bash
cd ava-devicekit
PYTHONPATH=backend python3 -m ava_devicekit.cli init-app ../my-devicekit-app
```

The generated directory contains:

| File | You Own |
|---|---|
| `manifest.json` | App id, chain, screen list, adapter names, firmware targets |
| `app.py` | App routing, deterministic actions, app-specific skills |
| `runtime.example.json` | Deployment ports, URLs, ASR/LLM/TTS providers |

A hardware app receives `DeviceMessage` values and returns one of: `ScreenPayload`, `ActionDraft`, or `ActionResult`. Use deterministic routes for known actions and reserve LLM fallback for open-ended answers.

Keep these concerns separate:

| Concern | Put It In |
|---|---|
| Generic chain feed/search/detail | `ChainAdapter` |
| Product actions like trading/payment/watchlist | App skill package |
| Physical confirmation requirements | `ActionDraft` + app confirmation handler |
| Board buttons, joystick, touch, microphone | Board port |
| Screen rendering | App UI layer consuming screen payloads |
