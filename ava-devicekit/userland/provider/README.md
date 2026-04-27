# Provider Development

Providers are deployment-owned integrations for AI or media services.

| Provider | Interface | Existing Reference |
|---|---|---|
| ASR | `providers/asr/base.py::ASRProvider` | `providers/asr/qwen_realtime.py` |
| LLM | `providers/llm/base.py::LLMProvider` | `providers/llm/openai_compatible.py` |
| TTS | `providers/tts/base.py::TTSProvider` | `providers/tts/mock.py` |

Rules:

- Keep secrets in env vars or deployment config.
- Do not hardcode one vendor into app logic.
- Deterministic app routing should run before LLM fallback.
- TTS providers should return both text and audio metadata.
