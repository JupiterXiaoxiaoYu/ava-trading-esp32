# AVE / xiaozhi 公网部署记录（tmux 方案）

## 当前状态
- 时间：2026-04-09
- 服务器：DigitalOcean Droplet
- SSH：`ssh -p 2222 -i ~/.ssh/id_ed25519_win root@167.99.29.70`
- 后端目录：`/root/ave-xiaozhi/xiaozhi-server`
- 运行方式：`tmux`
- 反向代理：`nginx`
- 当前已经跑起来
- 当前已经确认可从公网访问：`http://167.99.29.70/xiaozhi/ota/`

## 当前可用地址
- OTA：`http://167.99.29.70/xiaozhi/ota/`
- WebSocket：`ws://167.99.29.70/xiaozhi/v1/`
- 视觉接口：`http://167.99.29.70/mcp/vision/explain`

## 域名当前情况
- 域名：`jupdev.tech`
- 截至 2026-04-09，`jupdev.tech` 还没有 A 记录
- `www.jupdev.tech` 也还没有解析好
- 所以现在还不能直接申请 HTTPS 证书

## 域名要怎么配
在你的域名 DNS 管理面板里加这两条：

`A    @      167.99.29.70`
`A    www    167.99.29.70`

也可以把第二条换成：

`CNAME    www    jupdev.tech`

TTL 用默认值或者 `300`

## 服务器上已经做过的事
- 安装了 `python3-venv`
- 安装了 `ffmpeg`
- 安装了 `nginx`
- 安装了 `certbot`
- 把你的后端同步到了：`/root/ave-xiaozhi/xiaozhi-server`
- 创建了 Python 虚拟环境：`/root/ave-xiaozhi/xiaozhi-server/.venv`
- 已安装 `requirements.txt`
- 已启动 tmux 会话：`xiaozhi`
- 已配置 nginx 代理：
- `/xiaozhi/v1/` -> `127.0.0.1:8000`
- `/xiaozhi/ota/` -> `127.0.0.1:8003`
- `/mcp/vision/explain` -> `127.0.0.1:8003`
- 已打开服务器本机防火墙：`2222/tcp`、`80/tcp`、`443/tcp`

## tmux 常用命令
进入服务器：
`ssh -p 2222 -i ~/.ssh/id_ed25519_win root@167.99.29.70`

查看 tmux：
`tmux ls`

进入后端会话：
`tmux attach -t xiaozhi`

从 tmux 退出但不停止服务：
`Ctrl+b` 然后按 `d`

## 当前后端重启命令
进入服务器后执行：

`tmux kill-session -t xiaozhi 2>/dev/null || true`
`tmux new-session -d -s xiaozhi "cd /root/ave-xiaozhi/xiaozhi-server && . .venv/bin/activate && python app.py 2>&1 | tee -a /root/ave-xiaozhi/xiaozhi-server/runtime.log"`
`tmux capture-pane -pt xiaozhi | tail -n 40`

## 当前验证命令
本地验证公网 OTA：
`curl http://167.99.29.70/xiaozhi/ota/`

服务器本机验证：
`curl http://127.0.0.1/xiaozhi/ota/`

查看日志：
`tail -n 100 /root/ave-xiaozhi/xiaozhi-server/runtime.log`

## 板子现在怎么填
如果你现在就要先试公网，不等域名：

`http://167.99.29.70/xiaozhi/ota/`

设备拿到 OTA 后，会收到 websocket：

`ws://167.99.29.70/xiaozhi/v1/`

## 等 DNS 生效后要做的事
先确认：

`curl http://jupdev.tech/xiaozhi/ota/`

如果能通，再在服务器执行：

`certbot --nginx -d jupdev.tech -d www.jupdev.tech`

然后把后端配置切到域名：

`python3 - <<'PY'`
`from pathlib import Path`
`p = Path('/root/ave-xiaozhi/xiaozhi-server/data/.config.yaml')`
`text = p.read_text()`
`text = text.replace('ws://167.99.29.70/xiaozhi/v1/', 'wss://jupdev.tech/xiaozhi/v1/')`
`text = text.replace('http://167.99.29.70/mcp/vision/explain', 'https://jupdev.tech/mcp/vision/explain')`
`p.write_text(text)`
`print('done')`
`PY`

再重启后端：

`tmux kill-session -t xiaozhi`
`tmux new-session -d -s xiaozhi "cd /root/ave-xiaozhi/xiaozhi-server && . .venv/bin/activate && python app.py 2>&1 | tee -a /root/ave-xiaozhi/xiaozhi-server/runtime.log"`

## 域名生效后的最终地址
- OTA：`https://jupdev.tech/xiaozhi/ota/`
- WebSocket：`wss://jupdev.tech/xiaozhi/v1/`
- 视觉接口：`https://jupdev.tech/mcp/vision/explain`

## 这次问题的关键点
- 之前 DigitalOcean 控制台防火墙开了还不够
- 服务器里的 `ufw` 也开着，而且只放行了 `2222`
- 我已经补开了 `80` 和 `443`
- 所以后面公网 HTTP 访问已经恢复正常

## 2026-04-09 DNS 复查结论
- 我重新从公网核验后，`jupdev.tech` 还不能稳定解析
- 根因不是 A 记录本身，而是域名现在同时挂了两套权威 DNS
- DigitalOcean 这套返回的是：`167.99.29.70`
- 另一套 Orderbox 这组 `tech-domains.*.orderbox-dns.com` 返回的是空记录
- 公网递归 DNS 会随机命中其中一套，所以有的人能解析，有的人不能解析

## 必须改成这样
在域名注册商的 Nameserver 面板里，只保留这一套：

`ns1.digitalocean.com`
`ns2.digitalocean.com`
`ns3.digitalocean.com`

把下面这四个删掉：

`tech-domains.venus.orderbox-dns.com`
`tech-domains.mercury.orderbox-dns.com`
`tech-domains.earth.orderbox-dns.com`
`tech-domains.mars.orderbox-dns.com`

## 改完后的检查标准
当我再次检查时，必须满足：
- `jupdev.tech` -> `167.99.29.70`
- `www.jupdev.tech` -> `167.99.29.70` 或 CNAME 到 `jupdev.tech`
- 不能再看到 Orderbox 那四个 nameserver

只有到这一步，`certbot` 才能正常签发 HTTPS 证书。


## 2026-04-09 HTTPS 已完成
- 已成功签发 Let's Encrypt 证书
- 证书域名：`jupdev.tech`、`www.jupdev.tech`
- 证书到期：`2026-07-08`
- nginx 已自动切到 80 -> 443 跳转
- 后端 `data/.config.yaml` 已切到域名版 websocket / vision 地址
- `tmux` 会话 `xiaozhi` 已重启

## 当前最终可用地址
- OTA：`https://jupdev.tech/xiaozhi/ota/`
- WebSocket：`wss://jupdev.tech/xiaozhi/v1/`
- 视觉接口：`https://jupdev.tech/mcp/vision/explain`
- `https://www.jupdev.tech/xiaozhi/ota/` 也可访问，但设备建议统一使用主域名 `jupdev.tech`

## 已验证结果
- `http://jupdev.tech/xiaozhi/ota/` -> 自动 301 跳转到 HTTPS
- `https://jupdev.tech/xiaozhi/ota/` -> 返回 `wss://jupdev.tech/xiaozhi/v1/`
- `https://www.jupdev.tech/xiaozhi/ota/` -> 也返回 `wss://jupdev.tech/xiaozhi/v1/`

## 板子现在应该填写
`https://jupdev.tech/xiaozhi/ota/`
