# AVE Xiaozhi 产品总监级 Review（2026-04-07）

## 0. 评审结论（Executive Verdict）

**结论：当前分支已达到“工程实现可测 + QA 回归可跑”的阶段，但尚未达到“可面向真实资金用户上线”的标准。**

- **工程/QA 可用（已达标）**：核心屏幕状态机、按键链路、回退策略、交易提交/确认协议适配、主要回归测试均已成型并可重复执行。
- **真实用户可用（未达标）**：真实交易闭环证据不足（尤其是 live order event 样本与链上结果归因），交易历史可追溯能力仍缺。

---

## 1. 本轮证据与交叉检查范围

已逐项交叉检查以下目标文件：

- `docs/simulator-ui-guide.md`
- `docs/pending-tasks.md`
- `docs/ave-feature-map.md`
- `shared/ave_screens/ave_screen_manager.h`
- `shared/ave_screens/ave_screen_manager.c`
- `shared/ave_screens/screen_feed.c`
- `shared/ave_screens/screen_spotlight.c`
- `shared/ave_screens/screen_confirm.c`
- `shared/ave_screens/screen_limit_confirm.c`
- `shared/ave_screens/screen_result.c`
- `shared/ave_screens/screen_portfolio.c`
- `shared/ave_screens/screen_notify.c`
- `server/main/xiaozhi-server/test_ave_e2e.py`
- `server/main/xiaozhi-server/test_ave_api_matrix.py`
- `server/main/xiaozhi-server/test_p3_trade_flows.py`

并执行回归命令：

```bash
cd /home/jupiter/ave-xiaozhi/server/main/xiaozhi-server
pytest -q test_ave_api_matrix.py test_p3_trade_flows.py test_ave_e2e.py
# 结果：47 passed, 25 subtests passed in 0.73s
```

---

## 2. 分级问题清单（P0 / P1 / P2 / P3）

## P0（阻断上线）

1. **真实交易结果链路证据仍不足，尚不满足真实资金场景上线门槛**
   - `docs/pending-tasks.md:41` 明确写到本轮“no real order event sample was captured”。
   - `server/main/xiaozhi-server/test_ave_e2e.py:182-184` 为避免真实卖出，测试用 `balance_raw="0"`，意味着并未覆盖真实资产变动路径。
   - 风险：真实用户交易时，RESULT/NOTIFY 时序、状态归因、异常分支可能与实验环境不一致。

## P1（高优先级，影响可运营性）

1. **“E2E 已覆盖”的证据表达偏乐观，自动化可信度不足**
   - `docs/ave-feature-map.md:7` 把 `python3 test_ave_e2e.py` 作为基线。
   - `test_ave_e2e.py` 本质是脚本流程，不是 pytest 风格断言测试（见全文件结构，尤其 `run_tests` 过程在 `server/main/xiaozhi-server/test_ave_e2e.py:99-218`）。
   - 风险：CI 绿灯不等价于真实 E2E 绿灯。

2. **交易后可追溯能力仍未完全闭环（历史查询缺口仍在）**
   - `docs/ave-feature-map.md` 已对齐为：`getSwapOrder` 已接入 submit-only ACK reconciliation；`tx/history` 仍未接入。
   - 风险：已能覆盖一部分“提交后状态回查”，但用户侧完整历史追溯与客服解释链路仍不充分。

## P2（中优先级，影响体验完整度）

1. **模拟器与真机系统键对齐已提升，但仍需边界一致性验证**
   - `docs/simulator-ui-guide.md` 已对齐为 FN/PTT `F1` 按下/松开发送协议级 `listen start/stop`（`mode=manual`）。
   - 仍建议补充长按、抢焦点、重复按键等边界场景验证，避免“看似对齐但细节漂移”。

2. **实时流能力只覆盖 price/kline，交易观察维度有限**
   - `docs/ave-feature-map.md:79-80`：Data WSS 未集成 `tx/multi_tx/liq`。
   - 对“异常波动预警、鲸鱼/清算提示”等运营诉求支撑不足。

3. **主题覆盖仍有限**
   - `docs/ave-feature-map.md:46-49`：`rwa/l2` 未接入键控 source 循环。

## P3（低优先级，治理与可维护性）

1. **需要持续维持单一 release gate 文档**
   - 当前已将本轮发现的 docs 口径冲突修正，但发布判断仍应长期固定到单一 gate 文档，避免后续再次漂移。
   - 风险：若后续继续在多份文档中分别记录上线判断，团队仍可能再次出现口径分叉。

---

## 3. 哪些已经达到工程/QA 可用

以下能力已达到“工程可联调 + QA 可回归”标准：

1. **屏幕状态机与按键路由完整可用**
   - 全局 `Y -> portfolio`、NOTIFY 吞键、多屏分发明确：`shared/ave_screens/ave_screen_manager.c:214-240`。
   - FEED/SPOTLIGHT/CONFIRM/LIMIT_CONFIRM/RESULT/PORTFOLIO 各页面键逻辑明确并有本地 fallback。

2. **回退与防抢屏机制具备工程稳定性**
   - live 推送不抢屏（feed/spotlight guard）：`shared/ave_screens/ave_screen_manager.c:150-179`。
   - back fallback 优先 portfolio 语义清晰：`shared/ave_screens/ave_screen_manager.c:251-264`。

3. **交易确认流程具备防误触和超时兜底**
   - CONFIRM 500ms 防误触、15s watchdog：`shared/ave_screens/screen_confirm.c:302-316`。
   - LIMIT_CONFIRM 同类 watchdog：`shared/ave_screens/screen_limit_confirm.c:287-290`。

4. **回归覆盖深度已超过“基本可测”**
   - API 矩阵覆盖 payload 标准化、成功/失败样例、status 异常、WSS 事件映射：`server/main/xiaozhi-server/test_ave_api_matrix.py:640-1083`。
   - P3 交易流覆盖 pending 保护、deferred result flush、portfolio 回退：`server/main/xiaozhi-server/test_p3_trade_flows.py:157-260, 405-518`。

---

## 4. 哪些还没达到真实用户可用

1. **真实成交链路证据不足（尤其 live order 事件样本）**
   - 已在 pending 文档自认仍缺样本：`docs/pending-tasks.md:41`。

2. **用户交易后追溯能力仍有缺口**
   - `getSwapOrder` 已接入，但历史查询端点 `tx/history` 仍未接入（见 `docs/ave-feature-map.md`）。

3. **E2E 证据偏“脚本演示”而非“可审计自动化”**
   - `test_ave_e2e.py` 依赖人工环境与服务端状态，且存在“避免真实卖出”的保护分支（`server/main/xiaozhi-server/test_ave_e2e.py:182-184`）。

---

## 5. 基于 AVE API 能力的优先动作清单（建议执行顺序）

1. **统一发布口径（立即）**
   - 以单一文档作为 release gate（建议 pending-tasks 或新增 release-readiness），强制同步 P0 状态与测试计数。

2. **强化“提交成功 ≠ 成交成功”的可追踪闭环（本周）**
   - 在现有 `botswap` + `getSwapOrder` 基础上，补足 live 样本归档与回放验证，确保 submit-only ACK 的终态归因在真实流量下可审计。

3. **补齐交易历史可见性（本周）**
   - 接入 `GET /v1/thirdParty/tx/history`（若文档可用）或等效能力，提供用户可见的“最近成交/失败原因”视图与客服排障依据。

4. **建立可审计的真实环境 smoke（高优）**
   - 增加“只读/最小金额/沙箱资产”策略，采集真实 order event 样本，沉淀固定回放夹具，避免一直依赖 `balance_raw=0`。

5. **增强行情事件维度（中优）**
   - 视 API 计划与成本，增量接入 `tx/multi_tx/liq`，先用于告警级 NOTIFY，不强制首版 UI 重构。

6. **模拟器能力补齐（中优）**
   - 为 FN 语音/系统键设计模拟映射，降低“真机才可测”的联调阻力。

---

## 6. 总体建议（产品视角）

- **可以继续内测与 QA 回归，不建议直接面向真实资产用户公开上线。**
- 若必须灰度，建议先限定人群/金额/功能（禁用高风险路径），并把“交易最终状态可能延迟”以 UI 文案明确告知。
