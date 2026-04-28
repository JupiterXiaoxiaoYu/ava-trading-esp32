# AVE-Backed Solana Adapter

The built-in Solana adapter is the first `ChainAdapter` implementation for Ava DeviceKit. It is AVE-backed by default, but it sits behind the generic `ChainAdapter` interface so deployments can replace it with another Solana data API or another chain adapter.

It owns Solana-specific behavior that was previously mixed into Ava Box server tools:

| Capability | Behavior |
|---|---|
| Feed | Solana trending/rank feeds plus Pump.fun hot/new platform feeds |
| Search | Solana token search |
| Spotlight | Token detail, risk flags, kline-derived chart payload |

The adapter does not import or depend on legacy assistant runtime modules. Trading, watchlist, portfolio, and skill behavior belong to the Ava Box app layer, not this basic chain adapter.

To use another data API, configure a custom adapter class in runtime JSON:

```json
{
  "adapters": {
    "chain": {
      "provider": "custom",
      "class": "my_app.adapters.MyChainAdapter",
      "options": {
        "base_url": "https://data.example.com"
      }
    }
  }
}
```
