# Adapter Development

Adapters connect DeviceKit apps to external data or event sources without coupling framework core to one vendor.

| Adapter Type | Interface | Runtime Selection | Responsibility |
|---|---|---|---|
| Chain data | `backend/ava_devicekit/adapters/base.py::ChainAdapter` | `adapters.chain` | Feed, token search, and token detail payloads |
| Market stream | `backend/ava_devicekit/streams/base.py::MarketStreamAdapter` | app/deployment code | Price, kline, or event updates that can be applied to an active session |

## Chain Adapter Contract

A chain adapter implements only basic data reads:

| Method | Returns |
|---|---|
| `get_feed(topic, platform, context)` | `ScreenPayload("feed", ...)` or another app-supported list screen |
| `search_tokens(keyword, context)` | Search result feed payload |
| `get_token_detail(token_id, interval, context)` | Detail/spotlight payload |

Trading, watchlist, portfolio, and voice routing stay in the app layer. This keeps the same DeviceKit runtime usable with AVE APIs, another Solana API, another chain, or a non-trading hardware app.

## Runtime Config

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
  }
}
```

Use `chain_adapter_template.py` as the starting point.
