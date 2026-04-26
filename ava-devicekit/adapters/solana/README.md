# Solana Adapter

The Solana adapter is the first `ChainAdapter` implementation for Ava DeviceKit.

It owns Solana-specific behavior that was previously mixed into Ava Box server tools:

| Capability | Behavior |
|---|---|
| Feed | Solana trending/rank feeds plus Pump.fun hot/new platform feeds |
| Search | Solana token search |
| Spotlight | Token detail, risk flags, kline-derived chart payload |

The adapter does not import or depend on legacy assistant runtime modules. Trading, watchlist, portfolio, and skill behavior belong to the Ava Box app layer, not this basic chain adapter.
