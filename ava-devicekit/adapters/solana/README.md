# Solana Adapter

The Solana adapter is the first `ChainAdapter` implementation for Ava DeviceKit.

It owns Solana-specific behavior that was previously mixed into Ava Box server tools:

| Capability | Behavior |
|---|---|
| Feed | Solana trending/rank feeds plus Pump.fun hot/new platform feeds |
| Search | Solana token search |
| Spotlight | Token detail, risk flags, kline-derived chart payload |
| Portfolio | Local paper portfolio placeholder for framework demos |
| Watchlist | Local JSON-backed watchlist state |
| Action drafts | Market buy/sell, limit buy, cancel draft payloads requiring device confirmation |

The adapter does not import or depend on legacy assistant runtime modules. Deployments inject API keys and wallet/signing behavior outside the core framework.
