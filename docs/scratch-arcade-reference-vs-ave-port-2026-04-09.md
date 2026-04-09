# Scratch Arcade 参考固件 vs AVE 固件对比

日期：2026-04-09

## 目的

这份文档用于回答两个问题：

1. 为什么参考固件在同一块 Scratch Arcade 板子上“完全正常”
2. 我们当前 AVE 固件距离“硬件正常 + AVE 页面正常”还差什么

## 参考对象

### 参考正常版

- 仓库：`https://github.com/nulllaborg/xiaozhi-esp32/tree/Scratch-Arcade`
- 本地路径：`/home/jupiter/ave-xiaozhi/xiaozhi-esp32-scratch-arcade-ref`
- 分支：`Scratch-Arcade`
- 提交：`adefb4ef1a711d229e25a7ca220bb78460927530`
- 板型：`scratch-arcade`

### 当前 AVE 版

- 工作树：`/home/jupiter/.config/superpowers/worktrees/firmware/feat-scratch-arcade-s3-port`
- 板型：`scratch-arcade-s3`

## 已确认的事实

### 1. 参考固件实机工作正常

参考固件已经编译并烧录验证成功：

- 固件包：`/home/jupiter/ave-xiaozhi/merged-binary-ref-scratch-arcade.bin`
- 串口日志显示：
  - LCD 初始化成功
  - `NoAudioCodec: Simplex channels created`
  - Wi-Fi 连接成功
  - `MQTT: Connected to endpoint`
  - `Application: Activation done`
  - `AfeWakeWord` 启动成功
  - 状态机继续进入 `idle -> connecting -> listening`

这说明这块板子的“屏幕 + 按键 + PDM 麦克风 + I2S 喇叭”在参考固件里都是跑通的。

### 2. AVE 版的核心差异不在“硬件公开资料不足”

参考固件已经把这块板子的关键引脚坐实，因此后续不应继续把问题归因于“硬件信息不完整”。真正要解决的是：

- 我们的 AVE 固件是否完整沿用了参考固件已验证的板级能力
- AVE 页面链路是否真正收到了服务端 `type=display`

## 板级配置对比

### 一致的部分

当前 AVE 版已经同步了参考固件里最关键的音频和显示引脚：

- 麦克风 `PDM CLK`：`GPIO_NUM_47`
- 麦克风 `PDM DATA`：`GPIO_NUM_48`
- 喇叭 `BCLK`：`GPIO_NUM_41`
- 喇叭 `LRCK`：`GPIO_NUM_42`
- 喇叭 `DOUT`：`GPIO_NUM_1`
- 屏幕 `SCK/MOSI/CS/DC/RST/BL`：`12/11/10/45/46/21`
- 屏幕方向参数：`swap_xy=true`、`mirror_y=true`、`invert_color=true`
- `spi_mode = 0`

对应文件：

- 参考版：`xiaozhi-esp32-scratch-arcade-ref/main/boards/scratch-arcade/config.h`
- AVE 版：`main/boards/scratch-arcade-s3/config.h:6`

### 不同的部分

参考版的按钮模型是“小智标准聊天机”：

- `GPIO0`：启动/聊天键
- `GPIO5`：音量加
- `GPIO9`：音量减

当前 AVE 版的按钮模型是“Arcade 手柄”：

- D-pad：`16/15/14/13`
- `FN`：`0`
- `A/B/X/Y`：`39/5/9/4`

这不是错误，而是产品交互目标不同。参考版的目标是“小智聊天”，AVE 版的目标是“Arcade UI + AVE 导航”。

## 板级实现对比

### 参考版做了什么

参考版板级实现文件：`xiaozhi-esp32-scratch-arcade-ref/main/boards/scratch-arcade/scratch_arcade.cc`

它的特点：

- 使用 `NoAudioCodecSimplexPdm`
- 直接走标准小智聊天键逻辑
- 启动键会进入 `ToggleChatState()`
- 音量键直接控制输出音量
- 没有 AVE 键盘事件桥接

### AVE 版做了什么

AVE 版板级实现文件：`main/boards/scratch-arcade-s3/scratch_arcade_s3_board.cc:16`

它的特点：

- 现在也已经使用 `NoAudioCodecSimplexPdm`
- `FN` 按键改成 AVE 的按住听说逻辑：`ave_hw_listen_button`
- D-pad 和 `A/B/X/Y` 改成 AVE 导航键：`ave_hw_key_press`
- 不再保留参考版的音量加减产品行为

所以，两版最大的板级差异不是“硬件初始化”，而是“输入交互语义”。

## 应用层对比

### 参考版应用层

参考版 `main/application.cc` 是标准小智运行时：

- `display->SetupUI()`
- 聊天消息、情绪、状态都走标准 `Display` 接口
- 不处理 `type=display` 这种 AVE 扩展消息

### AVE 版应用层

AVE 版 `main/application.cc` 比参考版多了两条关键能力：

1. 在显示初始化后调用：
   - `ave_hw_init(lv_display_get_default())`

2. 在协议消息入口中处理：
   - `type=display`
   - 然后把 JSON 转给 `ave_hw_handle_display_json(...)`

对应差异位置：

- `main/application.cc:64`
- `main/application.cc:583`

这意味着：

- 参考版能正常聊天，但不会自动显示 AVE 页面
- AVE 版只有在服务端下发 `type=display` 时，才会进入 AVE 页面链路

## 为什么参考版“完全正常”

从串口看，参考版的完整链路是：

1. 板级初始化成功
2. `NoAudioCodecSimplexPdm` 创建成功
3. 联网成功
4. OTA 返回正常
5. MQTT 成功连接
6. 激活完成
7. 唤醒词模型加载成功
8. AFE 音频处理链启动
9. 状态机进入 `listening`

这说明它的成功条件是：

- 板级硬件定义正确
- 连接的是标准小智后端
- 产品交互路径是标准小智聊天路径

## 为什么 AVE 版不能只靠“参考版正常”自动成功

因为 AVE 版比参考版额外多了一层依赖：

- 不是只要连上标准后端就够
- 还必须连接到能下发 AVE `type=display` 的后端

也就是说：

- 参考版验证的是“硬件链路”和“标准小智聊天链路”
- AVE 版还要额外验证“AVE 页面数据链路”

## 当前状态

### 已经解决的事情

- flash 大小已经修正为 `8MB`
- LCD `spi_mode` 已切到可工作的 `0`
- AVE 版已经同步参考版的真实音频配置
- AVE 版不再使用 `DummyAudioCodec`
- AVE 版已生成带真实音频定义的固件：
  - ` /home/jupiter/ave-xiaozhi/merged-binary-8mb-audio.bin`

### 仍待验证的事情

- 这版 AVE 固件烧录后，是否也能出现：
  - `NoAudioCodec: Simplex channels created`
  - `AfeWakeWord` 初始化成功
  - `idle -> connecting -> listening`
- 连接到我们的后端后，是否能收到 `type=display`
- 收到 `type=display` 后，屏幕是否真的切到 AVE 页面

## 建议的下一步顺序

1. 先烧录 `merged-binary-8mb-audio.bin`
2. 抓 AVE 版串口，对比参考版是否也能完成：
   - 音频 codec 初始化
   - 唤醒词初始化
   - `connecting -> listening`
3. 如果 AVE 版聊天链路正常，再验证后端是否会下发 `type=display`
4. 如果服务端已下发 `type=display` 但仍无页面，再回到显示桥接和渲染链路排查

## 一句话结论

参考固件已经证明这块 Scratch Arcade 板子的硬件链路是通的；我们当前 AVE 版剩下的核心问题，不是“这块板子能不能跑小智”，而是“在同样板级能力下，AVE 页面链路是否完整打通”。
