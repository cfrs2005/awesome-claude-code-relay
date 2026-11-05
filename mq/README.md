# MQ — ModelQuality 检测引擎

给任何 **Anthropic 兼容**（`/v1/messages`）的中转站做标准化检测，输出可分享的中文验证报告。思路对标 VPS 圈的 NodeQuality：同一套探针、同一种报告格式，任何人都能复现。

## 自助测试（推荐）

用**你自己的 Key** 在本地跑，Key 不出你的机器：

```bash
curl -fsSL https://raw.githubusercontent.com/cfrs2005/awesome-claude-code-relay/v0.2.0/mq/mq.py -o mq.py
python3 mq.py --base-url https://api.example.com --key sk-your-key
```

只依赖 Python 3.9+ 标准库，无第三方依赖。引擎只访问 `--base-url`（及可选的 `--official-base-url`）两个地址。

带官方对照（推荐，tokenizer 计数对照是目前最强的换壳证据）：

```bash
python3 mq.py --base-url https://api.example.com --key sk-xxx \
  --official-base-url https://api.anthropic.com --official-key sk-ant-xxx
```

先花小钱看看端点什么情况：

```bash
python3 mq.py --base-url https://api.example.com --key sk-xxx --mode quick
```

同一个端点 **第二次及以后** 的测试，建议带上上次的 `report.json`，会额外比对模型目录变化：

```bash
python3 mq.py --base-url https://api.example.com --key sk-xxx \
  --previous-report ./last-report.json
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--model` | 被测模型 id，默认 `claude-haiku-4-5-20251001` |
| `--key-file` | 从文件读 Key（避免进入 shell history / CI 日志） |
| `--previous-report` | 上次的 `report.json`，用于检测模型目录 / 上游变化 |
| `--mode` | `quick`（约 8 次请求，粗测）/ `standard`（默认）/ `full`（含重复稳定性采样） |
| `--expect-family` | 期望的模型家族，默认 `claude`。目录里一个都没有时直接判不合格 |
| `--rounds` | 一致性采样轮数（默认 4，越多越准也越费额度） |
| `--json` / `--markdown` | 报告落盘路径 |
| `--self-test` | 离线自检，不发任何请求 |

## 检测项

报告分五组，顺序即阅读优先级：模型目录 → 端点可用性 → 协议兼容性 → 身份证据 → 稳定性与性能。

| 检测项 | 分组 | 判定依据 |
|--------|------|----------|
| 模型目录 `GET /v1/models` | 目录 | 声明模型是否存在；目录家族构成（claude / gpt / glm …） |
| 与上次目录对比 | 目录 | 模型集合增删；**家族构成是否翻转**（换上游的直接信号） |
| 基础 Messages | 可用性 | 响应结构（content/usage/stop_reason/id）完整；HTTP 状态分级 |
| SSE 流式 | 协议 | 事件序列完整（message_start/…/message_stop），统计 TTFT、TPS |
| system 透传 | 协议 | system 指令生效 |
| tool_use 闭环 | 协议 | 结构化 tool_use 块 + tool_result 回合闭环 |
| extended thinking | 协议 | 有 thinking 块 + signature 存在且长度 ≥ 50；缺块或缺签名判 FAIL |
| **签名回验** ⭐ | 身份 | 把中转返回的 signature 回放给**官方端点**，官方接受与否。唯一密码学级证据，需官方 Key |
| 响应标识规范 | 身份 | `id` 前缀 `msg_`、`type` / `role` / `response.model`、`toolu_` / `srvtoolu_` 前缀 |
| tokenizer 指纹 `count_tokens` | 身份 | 固定文本的 token 计数，确定性 + 与官方可比 |
| tokenizer 计数一致性 | 身份 | 相同请求 input_tokens 必须完全一致；与官方对照必须逐字节相等 |
| usage 自洽性 | 身份 | 长短 prompt 的 input 增量落在 [45,140]；output 不超 max_tokens |
| 模型自述 | 身份 | 仅记录它自己怎么说，**不参与通过判定** |
| 稳定性 | 稳定性 | N 次重复调用成功率、p50/p95 延迟 |

检测项的设计取舍（哪些照搬成熟实现、哪些是我们多的）见
[docs/2026-11-04-mq-detectors-vs-veridrop.md](../docs/2026-11-04-mq-detectors-vs-veridrop.md)。

## 结论分级

结论按「用户下一步该做什么」分层，不再把不同故障塞进同一个标签。

| 结论 | 含义 | 能否通过门禁 |
|------|------|:---:|
| `basic_passed` | 协议与行为特征均通过 | ✅ |
| `endpoint_unreachable` | 网络不通、超时、或上游 5xx | ❌ |
| `auth_rejected` | 401/403，Key 无效或无权限 | ❌ |
| `model_not_found` | 声明模型不在 `/v1/models` 中 | ❌ |
| `protocol_incompatible` | Messages 路径返回 404 或响应不符合规范 | ❌ |
| `behavior_anomaly` | 核心协议项（流式 / system / tools）失败 | ❌ |
| `identity_suspect` | tokenizer 不一致、官方对照不符、或目录家族翻转 | ❌ |
| `evidence_insufficient` | 保留值，仅兼容历史报告 | ❌ |

只有 `basic_passed` 会让 Hub 判为 `verified=true`。

## 明确的证据边界

- **模型自述零证据力**：问模型"你是谁"，它会照着 system prompt 回答，中转站可以随手指示它自称 Claude。该探针只做记录，不参与判定。
- **签名长度检查不是加密验证**：长度只能排除占位串。真伪要靠「签名回验」把 signature 回放给官方端点。
- **不能证明不留存、不转卖**请求与代码。
- **签名回验只覆盖返回了 thinking 的模型**：不支持 thinking 的模型没有同等强度的验证手段。
- 目录家族检查只能证明「它声称提供什么」，配合 tokenizer 才能构成一致证据链。

**收录 ≠ 推荐，验证通过 ≠ 安全可信。**
