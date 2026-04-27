# UI Screen Development

DeviceKit sends screen payloads. Your device or simulator renders them.

## Required Screen Hooks

Implement `ava_dk_screen_vtable_t` for each screen your app declares:

| Hook | Purpose |
|---|---|
| `show(json_data, user)` | Render the screen data. |
| `key(key, user)` | Handle current-screen key behavior. |
| `selection_context_json(out, out_n, user)` | Return current cursor/selection context for voice and actions. |
| `cancel_timers(user)` | Stop screen timers when navigating away. |

Framework core does not prescribe layout, fonts, colors, or animation. Those are
app/device UI decisions.
