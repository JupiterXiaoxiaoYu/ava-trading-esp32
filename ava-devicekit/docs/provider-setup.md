# Provider Setup

Providers are configured in `RuntimeSettings` or `userland/runtime.example.json`.

| Provider | Framework Interface | Built-In Implementation | Required Secret |
|---|---|---|---|
| ASR | `ASRProvider.transcribe_pcm16` | Qwen realtime PCM16, OpenAI-compatible transcription, custom class | provider-specific env var |
| LLM | `LLMProvider.complete` | OpenAI-compatible chat completions, custom class | provider-specific env var |
| TTS | `TTSProvider.synthesize` | Mock, OpenAI-compatible `/audio/speech`, AliBL CosyVoice WebSocket, custom class | provider-specific env var |
| Chain data | `ChainAdapter` | AVE-backed Solana reference, mock, custom class | provider-specific env var |
| Market stream | `MarketStreamAdapter` | Mock, polling, AVE data WSS reference, custom class | provider-specific env var |
| Trade execution | App-level `TradeExecutionProvider` | Paper, AVE proxy wallet, AVE Solana transaction construction, custom class | provider-specific env var |

ASR audio format is explicit: the existing-firmware gateway buffers binary audio between `listen:start` and `listen:stop`, runs it through the configured `AudioDecoder`, calls ASR, and routes the transcript into the app. Qwen realtime and OpenAI-compatible ASR expect PCM16 after decoding. If firmware captures OPUS, set `audio.decoder_class` to `ava_devicekit.providers.asr.audio.OpusLibDecoder` with `opuslib` installed, or to another deployment-provided decoder that returns PCM16.


## Provider Selection In Runtime Config

Users choose providers in the config file. Built-in names cover common compatible APIs; `provider: custom` loads any Python class that implements the interface.

```json
{
  "providers": {
    "asr": {
      "provider": "openai-compatible",
      "base_url": "https://api.openai.com/v1",
      "model": "whisper-1",
      "api_key_env": "OPENAI_API_KEY",
      "language": "en"
    },
    "llm": {
      "provider": "openai-compatible",
      "base_url": "https://api.deepseek.com/v1",
      "model": "deepseek-chat",
      "api_key_env": "DEEPSEEK_API_KEY"
    },
    "tts": {
      "provider": "custom",
      "class": "my_app.providers.MyTTSProvider",
      "options": {
        "base_url": "https://tts.example.com",
        "api_key_env": "MY_TTS_KEY",
        "model": "my-tts-model",
        "voice": "ava"
      }
    }
  }
}
```

Provider aliases currently supported by the built-in registry:

| Type | Built-In `provider` Values | Custom Extension |
|---|---|---|
| ASR | `qwen`, `qwen_realtime`, `qwen3-asr-flash-realtime`, `openai-compatible`, `whisper`, `transcription` | `provider: custom` + `class` |
| LLM | `openai-compatible`, `openai`, `compatible` | `provider: custom` + `class` |
| TTS | `mock`, `openai-compatible`, `openai`, `compatible`, `alibl`, `alibl_stream`, `cosyvoice` | `provider: custom` + `class` |

See `userland/provider/provider.catalog.example.json` for copyable examples.

## Chain And Execution Providers

Chain data and execution are separate boundaries. A `ChainAdapter` returns screen-ready feed/search/detail payloads; a trade executor creates or submits an app-specific action only after the device confirmation flow.

```json
{
  "adapters": {
    "chain": {
      "provider": "custom",
      "class": "my_app.adapters.MyChainAdapter",
      "options": {
        "base_url": "https://data.example.com",
        "api_key_env": "MY_DATA_API_KEY"
      }
    }
  },
  "execution": {
    "mode": "custom",
    "class": "my_app.execution.MyTradeExecutor",
    "options": {
      "base_url": "https://trade.example.com",
      "api_key_env": "MY_TRADE_API_KEY"
    }
  }
}
```

Custom chain adapters implement `get_feed`, `search_tokens`, and `get_token_detail`. Custom execution providers implement `execute(summary, params)` and may optionally implement `send_signed_solana_tx(request_id, signed_tx)` if the app uses an external signing flow.

### AliBL / CosyVoice TTS

Ava Box uses the same Bailian CosyVoice WebSocket provider shape as the original server `AliBLTTS` block. Configure it in runtime JSON with `provider: alibl`, `format: opus`, and set `DASHSCOPE_API_KEY` in the deployment environment, or set `api_key_env` to a separate AliBL key such as `ALIBL_TTS_API_KEY`. The checked-in runtime defaults use the international DashScope endpoint with `model: cosyvoice-v3-flash` and `voice: longanyang`; deployments with a China-region Bailian key can switch back to `wss://dashscope.aliyuncs.com/api-ws/v1/inference/`, `cosyvoice-v2`, and `longcheng_v2`.
