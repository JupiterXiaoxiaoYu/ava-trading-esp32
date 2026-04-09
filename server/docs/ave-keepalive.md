# AVE 服务端长连接保活说明

适用场景：ESP32 掌机以屏幕和摇杆浏览为主，语音只是辅助。如果仍使用默认的 120 秒无语音超时，设备会在停留 `feed`、`spotlight`、钱包页时被服务端主动断开，表现为数据不再刷新、页面像卡住、需要重新唤醒或重连。

本仓已将默认配置改为：

- `close_connection_no_voice_time: 315360000`
- `enable_websocket_ping: true`

其中 `315360000` 秒约等于 10 年，用来表达“工程上等同于永不超时”。之所以不直接使用 `0`，是因为现有超时逻辑把数值视为秒数参与比较，`0` 会导致立即超时，而不是禁用超时。

涉及位置：

- `server/main/xiaozhi-server/config.yaml`
- `server/main/xiaozhi-server/core/connection.py`
- `server/main/xiaozhi-server/core/handle/receiveAudioHandle.py`
- `server/main/xiaozhi-server/core/handle/textHandler/pingMessageHandler.py`
- `server/main/manager-api/src/main/resources/db/changelog/202604101030.sql`

如果你的部署已经存在 `data/.config.yaml`，并且里面显式写了旧值，那么本仓默认值不会覆盖它。请同时检查：

```yaml
close_connection_no_voice_time: 315360000
enable_websocket_ping: true
```

如果你的部署启用了 `manager-api`，还需要让数据库里的 `sys_params` 同步到新默认值。为此本仓新增了一个 Liquibase 变更集 `202604101030.sql`，用于把已有的：

- `close_connection_no_voice_time`
- `enable_websocket_ping`

更新为新的默认值，并在参数缺失时补齐。
