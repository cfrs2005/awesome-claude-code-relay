# MQ — ModelQuality 检测引擎

给任何 **Anthropic 兼容**（`/v1/messages`）的中转站做标准化基础检测，输出可分享的中文验证报告。思路对标 VPS 圈的 NodeQuality：同一套探针、同一种报告格式，任何人都能复现。

## 自助测试（推荐）

用**你自己的 Key** 在本地跑，Key 不出你的机器：

```bash
curl -fsSL https://raw.githubusercontent.com/cfrs2005/awesome-claude-code-relay/main/mq/mq.py -o mq.py
python3 mq.py --base-url https://api.example.com --key sk-your-key
```

只依赖 Python 3.8+ 标准库，无第三方依赖。引擎只访问 `--base-url`（及可选的 `--official-base-url`）两个地址。

带官方对照（推荐，tokenizer 计数对照是目前最强的换壳证据）：

```bash
python3 mq.py --base-url https://api.example.com --key sk-xxx \
  --official-base-url https://api.anthropic.com --official-key sk-ant-xxx
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--model` | 被测模型 id，默认 `claude-haiku-4-5-20251001` |
| `--key-file` | 从文件读 Key（避免进入 shell history / CI 日志） |
| `--rounds` | 一致性采样轮数（默认 4，越多越准也越费额度） |
| `--json` / `--markdown` | 报告落盘路径 |
| `--self-test` | 离线自检，不发任何请求 |

## 检测项

| 检测项 | 等级 | 判定依据 |
|--------|------|----------|
| 基础 Messages | 核心 | 响应结构（content/usage/stop_reason/id）完整 |
| SSE 流式 | 核心 | 事件序列完整（message_start/…/message_stop），统计 TTFT、TPS |
| tokenizer 计数一致性 | 核心 | 相同请求 input_tokens 必须完全一致；与官方对照必须逐字节相等 |
| system 透传 | 核心 | system 指令生效 |
| tool_use | 重要 | 结构化 tool_use 块 + tool_result 回合闭环 |
| extended thinking | 信息 | thinking 块与 signature 字段**存在性**（≠密码学真实） |
| 身份旁证 | 启发式 | 自称身份、注入泄漏探测，仅作旁证 |
| 稳定性 | 重要 | N 次重复调用成功率、p50/p95 延迟 |

## 结论分级

- `basic_passed` 基础验证通过 —— 协议与行为特征正常
- `behavior_anomaly` 行为异常 —— 核心协议项失败
- `identity_suspect` 身份存疑 —— tokenizer 计数不一致 / 官方对照不符 / 身份旁证异常
- `evidence_insufficient` 证据不足 —— 连基础调用都无法完成

## 明确不能证明的事

- 不能证明服务商**不留存、不转卖**你的请求与代码
- 不能密码学验证 thinking signature 的真实性
- 身份旁证（问模型"你是谁"）可被上游指示伪造，只是辅助信号

**收录 ≠ 推荐，验证通过 ≠ 安全可信。**
