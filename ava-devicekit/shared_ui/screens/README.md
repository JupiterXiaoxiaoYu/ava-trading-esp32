# Shared UI Screen Contracts

The shared UI runtime owns portable primitives. Product screens are app-level renderers that consume `ScreenPayload` data.

| Screen | Required Payload Fields | App Layer |
|---|---|---|
| `feed` | `tokens[]`, `source_label`, `mode`, `chain` | Token discovery, watchlist, search results |
| `spotlight` | `symbol`, `token_id`, `price`, `change_24h`, `chart[]`, `risk_level` | Token detail and selected-token context |
| `portfolio` | `items[]`, `total_value`, `pnl` | Portfolio and paper/real positions |
| `confirm` | `trade_id`, `action`, `symbol`, `amount_native`, `risk` | Physical confirmation for high-risk actions |
| `result` | `title`, `body`, `ok` | Completion or cancellation feedback |
| `notify` | `title`, `body`, `level` | Low-risk status and fallback messages |

Every interactive list screen must preserve cursor context by emitting `screen_context` with the selected row. Voice routing depends on this context.
