# Scratch Arcade 本地/热点/公网服务接入记录

日期：2026-04-08

更新：2026-04-09

## 结论

当前固件不是把聊天后端地址硬编码在程序里直接连接，而是走下面这条链路：

1. 设备启动后先请求 `OTA URL`
2. OTA 服务返回 `websocket.url` 或 `mqtt.endpoint`
3. 固件把这些地址保存到设备设置中
4. 设备再去连接真正的聊天服务

所以，设备能不能连上我们自己的服务，关键不在“bin 里有没有写死服务器”，而在：

- 设备能不能访问我们配置的 `OTA URL`
- OTA 返回给设备的 `websocket.url` / `mqtt.endpoint` 能不能被设备访问

另外，`nulllaborg/xiaozhi-esp32` 的 `Scratch-Arcade` 参考分支已经在这块同型号板子上实机验证为“完全正常”：

- 屏幕、背光、按键正常
- Wi-Fi、OTA、MQTT 链路正常
- PDM 麦克风和 I2S 喇叭正常
- 唤醒词、监听、聊天状态机正常

这说明当前 Scratch Arcade 板子的公开硬件定义已经足够支撑完整小智聊天固件，后续我们的重点不再是“猜硬件”，而是：

- 把参考固件中已经验证过的板级音频配置稳定移植到我们的 AVE 固件
- 把 OTA / websocket / mqtt 指到我们自己的服务
- 再确认服务端是否会下发 AVE `type=display` 页面数据

## 固件侧关键位置

- OTA 地址读取：`main/ota.cc:46`
- 配网页保存 OTA 地址：`managed_components/78__esp-wifi-connect/wifi_configuration_ap.cc:599`
- OTA 下发的 `mqtt` 配置写入设置：`main/ota.cc:146`
- OTA 下发的 `websocket` 配置写入设置：`main/ota.cc:167`
- WebSocket 读取并连接：`main/protocols/websocket_protocol.cc:84`
- MQTT 读取并连接：`main/protocols/mqtt_protocol.cc:65`

## 2026-04-09 参考固件实机验证结果

参考仓库：

- `https://github.com/nulllaborg/xiaozhi-esp32/tree/Scratch-Arcade`
- 本地路径：`/home/jupiter/ave-xiaozhi/xiaozhi-esp32-scratch-arcade-ref`
- 分支：`Scratch-Arcade`
- 提交：`adefb4ef1a711d229e25a7ca220bb78460927530`

本地已编译出参考固件整包：

- `merged-binary-ref-scratch-arcade.bin`
- 路径：`/home/jupiter/ave-xiaozhi/merged-binary-ref-scratch-arcade.bin`

该参考固件烧录后，串口日志确认以下链路全部正常：

- 识别板型：`SKU=scratch-arcade`
- LCD 初始化成功，背光打开
- 音频硬件初始化成功：`NoAudioCodec: Simplex channels created`
- 连上热点 `yumao`
- 获取 IP：`172.20.10.13`
- 成功访问 `api.tenclass.net:443`
- 成功连接 `mqtt.xiaozhi.me`
- 激活完成：`Application: Activation done`
- AFE / 唤醒词启动：
  - `AfeWakeWord: Model 0: wn9_nihaoxiaozhi_tts`
  - `AFE: Input PCM Config: total 1 channels(1 microphone, 0 playback), sample rate:16000`
- 设备状态机继续进入：
  - `idle -> connecting`
  - `connecting -> listening`

这份日志非常关键，因为它证明：

- 该板子的 PDM 麦克风接法是有效的
- 该板子的 I2S 喇叭接法是有效的
- 当前参考固件使用的是可工作的真实音频 codec，而不是占位实现

### 参考固件确认可工作的板级音频定义

来自参考分支 `main/boards/scratch-arcade/config.h`：

- 输入采样率：`16000`
- 输出采样率：`16000`
- 麦克风 `PDM CLK`：`GPIO_NUM_47`
- 麦克风 `PDM DATA`：`GPIO_NUM_48`
- 喇叭 `BCLK`：`GPIO_NUM_41`
- 喇叭 `LRCK`：`GPIO_NUM_42`
- 喇叭 `DOUT`：`GPIO_NUM_1`

参考分支在板级实现里使用：

- `NoAudioCodecSimplexPdm`

对应位置：

- `xiaozhi-esp32-scratch-arcade-ref/main/boards/scratch-arcade/config.h`
- `xiaozhi-esp32-scratch-arcade-ref/main/boards/scratch-arcade/scratch_arcade.cc`

## 对我们当前 AVE 固件的直接影响

我们原先的 `scratch-arcade-s3` 端口主要问题有两个：

1. 早期版本 flash 大小错误，用了 `16MB`，而板子实际是 `8MB flash + 8MB PSRAM`
2. 音频路径最初还是占位实现，没有接入参考固件已验证的 PDM / I2S 定义

目前这两个问题都已经明确：

- flash 问题已经修正为 `8MB`
- 音频针脚和 codec 方案已经从参考固件中提取出来

我们当前工作树里已经同步了参考固件那套音频定义：

- `main/boards/scratch-arcade-s3/config.h`
- `main/boards/scratch-arcade-s3/scratch_arcade_s3_board.cc`

并且已生成一版带真实音频定义的 AVE 固件整包：

- `merged-binary-8mb-audio.bin`
- 路径：`/home/jupiter/ave-xiaozhi/merged-binary-8mb-audio.bin`

注意：

- 参考固件“聊天完全正常”并不等于“自带 AVE 页面”
- AVE 页面仍然依赖正确的后端服务下发 `type=display` 消息
- 所以“参考固件正常”证明的是硬件和标准小智链路没问题，不是 AVE 页面链路已经打通

## 服务端关键位置

- 本地简单 OTA 服务启动路由：`server/main/xiaozhi-server/core/http_server.py:45`
- OTA 下发 websocket 地址：`server/main/xiaozhi-server/core/api/ota_handler.py:292`
- OTA GET 页面展示当前下发的 websocket 地址：`server/main/xiaozhi-server/core/api/ota_handler.py:363`
- 简单部署时 websocket 配置项：`server/main/xiaozhi-server/data/.config.yaml:20`

## 如果设备和电脑都在同一局域网

最直接的方式是：

- 电脑运行 `xiaozhi-server`
- 设备与电脑接入同一网络
- 设备配置 OTA 地址，例如：

```text
http://192.168.1.25:8003/xiaozhi/ota/
```

- 服务端下发 websocket 地址，例如：

```text
ws://192.168.1.25:8000/xiaozhi/v1/
```

对应配置参考：

```yaml
server:
  ip: 0.0.0.0
  port: 8000
  http_port: 8003
  websocket: ws://192.168.1.25:8000/xiaozhi/v1/
```

注意：

- 不能写 `127.0.0.1`
- 不能写 `localhost`
- 必须写设备视角能访问到的电脑 IP

## 如果设备只能连手机热点

这时不一定必须上公网服务器，但会多一个限制：

- 如果手机热点允许热点内设备互相访问，那么仍然可以本地直连
- 如果手机热点做了客户端隔离，设备就无法访问电脑

可选方案如下。

### 方案 A：板子和电脑都连同一个手机热点

前提：

- 手机热点允许设备之间互相访问

做法：

- 电脑也连这个热点
- 服务端配置 websocket 为电脑在热点下的 IP
- 设备 OTA 地址也填电脑在热点下的 IP

例如：

```text
OTA: http://电脑热点IP:8003/xiaozhi/ota/
WS:  ws://电脑热点IP:8000/xiaozhi/v1/
```

### 方案 B：本地跑服务，但做内网穿透

适合：

- 热点不允许设备互访
- 但仍想在本机开发和调试

思路：

- 电脑本地继续运行服务
- 把本地 `8003` 暴露为公网 OTA 地址
- 把本地 `8000` 暴露为公网 WebSocket 地址

最终设备使用：

```text
OTA: https://你的公网地址/xiaozhi/ota/
WS:  wss://你的公网地址/xiaozhi/v1/
```

### 方案 C：直接部署到公网服务器

最稳妥，适合长期使用：

- 不受手机热点是否隔离影响
- 设备在任何网络下都能连
- 更接近后续正式环境

## 建议的排查顺序

1. 先验证当前 bin 能否正常启动、点亮屏幕、响应按键
2. 再验证设备是否能访问 OTA 地址
3. 再验证 OTA 返回的 websocket 地址是否正确
4. 最后再验证聊天链路是否真正建立

## 当前我们已经准备好的固件

已成功编译并生成单文件烧录包：

- `merged-binary.bin`：
  `/home/jupiter/.config/superpowers/worktrees/firmware/feat-scratch-arcade-s3-port/build-scratch-553-lvgl/merged-binary.bin`

它可以直接从 `0x0` 烧录。

## 当前版本的已知限制

当前 Scratch Arcade S3 版本主要先验证：

- 屏幕显示
- 按键
- AVE 界面渲染

截至 2026-04-09，这条说明已经更新：

- 参考固件已经确认 PDM 麦克风具体引脚映射
- 我们也已经按参考固件把真实音频定义移植到当前 AVE 工作树
- 剩余重点已经转为“AVE 页面链路”和“后端地址配置”，而不是继续猜音频硬件

## 下一步建议

先用当前 `merged-binary.bin` 实机验证以下事项：

1. 能否正常烧录和启动
2. 屏幕方向、背光、UI 是否正常
3. 按键映射是否正确
4. 在无麦克风条件下，能否至少进入 UI 和看到服务端推送的界面

确认这些基础项后，再继续处理：

- OTA 指向本地/热点/公网服务
- AVE `type=display` 页面下发与渲染
- 参考固件与 AVE 固件的串口差异比对
