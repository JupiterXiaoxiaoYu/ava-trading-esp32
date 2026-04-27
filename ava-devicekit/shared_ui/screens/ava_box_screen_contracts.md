# Ava Box Screen Contracts

Ava Box may implement LVGL screens under its app UI layer using the shared payload contracts. DeviceKit core should not hard-code token trading UI.

| Ava Box Screen | Input Payload | Output Context |
|---|---|---|
| Feed | `tokens[]` from `ChainAdapter.get_feed()` or watchlist/search skills | `screen=feed`, `cursor`, `selected`, `visible_rows` |
| Spotlight | `get_token_detail()` payload | `screen=spotlight`, selected token identity and pair data |
| Portfolio | `AvaBoxSkillService.get_portfolio()` | selected position or empty state |
| Orders | `AvaBoxSkillService.get_orders()` | selected order |
| Confirm | `ActionDraft.screen` | `request_id` for confirm/cancel |
| Result | `ActionResult.screen` | no required selection |
