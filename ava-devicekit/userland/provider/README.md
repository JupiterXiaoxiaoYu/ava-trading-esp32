# Provider Development

Providers are deployment-owned integrations for AI or media services. Configure built-in providers through `RuntimeSettings` or add new implementations behind the same interfaces.

| Provider | Interface | Built-In Reference | Framework Or App |
|---|---|---|---|
| ASR | `providers/asr/base.py::ASRProvider` | `providers/asr/qwen_realtime.py` | Framework |
| LLM | `providers/llm/base.py::LLMProvider` | `providers/llm/openai_compatible.py` | Framework |
| TTS | `providers/tts/base.py::TTSProvider` | `providers/tts/mock.py`, `providers/tts/openai_compatible.py` | Framework |
| Market stream | `streams/base.py::MarketStreamAdapter` | `streams/mock.py`, `streams/polling.py`, `streams/ave_data_wss.py` | Framework contract; AVE WSS is Ava Box/reference |
| Trade execution | `apps/ava_box_skills/execution.py::TradeExecutionProvider` | Paper, AVE Solana transaction construction | Ava Box app |

Rules:

- Keep secrets in env vars or deployment config.
- Do not hardcode one vendor into app logic.
- Deterministic app routing should run before LLM fallback.
- TTS providers should return both text and audio metadata.
- ASR providers should state their expected audio format; Qwen realtime expects PCM16.
- Real trade providers should keep credentials server-side. Ava Box defaults to proxy/custodial wallet execution for real orders; ESP32 remains the confirmation surface.

Use `provider.catalog.example.json` for selectable ASR/LLM/TTS config examples, including custom Python provider classes.
