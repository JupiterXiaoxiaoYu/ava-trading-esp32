# Provider Setup

Providers are configured in `RuntimeSettings` or `userland/runtime.example.json`.

| Provider | Framework Interface | Built-In Implementation | Required Secret |
|---|---|---|---|
| ASR | `ASRProvider.transcribe_pcm16` | Qwen realtime PCM16 session | `DASHSCOPE_API_KEY` |
| LLM | `LLMProvider.complete` | OpenAI-compatible chat completions | `OPENAI_API_KEY` or compatible key |
| TTS | `TTSProvider.synthesize` | OpenAI-compatible `/audio/speech` plus mock | `OPENAI_API_KEY` or compatible key |
| Market stream | `MarketStreamAdapter` | Mock, polling, AVE data WSS reference | `AVE_API_KEY` for AVE WSS |
| Trade execution | App-level execution provider | Paper, AVE Solana transaction construction | `AVE_API_KEY` for real provider |

ASR audio format is explicit: Qwen realtime provider accepts PCM16. If firmware captures OPUS, the board port or deployment transport must provide an `AudioDecoder` that returns PCM16 before passing chunks into the provider session.
