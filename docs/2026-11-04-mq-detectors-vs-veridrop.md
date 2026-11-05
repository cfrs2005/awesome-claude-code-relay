# MQ 检测项对照 Veridrop 的取舍

日期：2026-11-04
参考实现：`canarybyte/veridrop`（开源，MIT）
范围：`mq/mq.py`

## 为什么对照

MQ 原来的探针是凭直觉写的：问模型"你是谁"、让它算一道乘法、让它查巴黎天气。这些题**不是官方规范要求的，也不是 Claude Code 真实会发的请求**，测出来的结果别人无法复现，也无法与任何基准比较。

Veridrop 是这个领域已有的成熟实现，值得先看它怎么做，再决定自己补什么、不补什么。

## 从 Veridrop 学到的四件事

### 一、检测项要按「伪造难度」加权，不是按直觉排序

它的权重表：

| 检测项 | 权重 | 理由 |
|---|---:|---|
| thinking_signature | 25 | 服务端签名，最难伪造 |
| behavioral_signature | 15 | 行为指纹，中等 |
| structured_output | 12 | 需要真实能力 |
| consistency / knowledge / token_usage | 各 10 | |
| pdf | 8 | |
| identity | **5** | 问"你是谁"，最容易被 system prompt 操纵 |

「问模型你是谁」权重只有 5 —— 这一点和 MQ 原来的做法正好相反：我们把它当成一个正经检测项写在报告里。现在已降级为纯记录项。

### 二、critical 硬否决，不允许被总分淹没

一个 25% 权重的检测项失败，可能被六个 100% 的廉价检查拉回及格线。Veridrop 的做法是：只要出现 critical 级 issue，verdict 上限锁在 `marginal`，即使总分 ≥ 70 也不给绿。

MQ 的 `verdict()` 用的是同一种思路但更硬：按「端点通不通 → 声明模型在不在 → 协议对不对 → 身份证据」的顺序短路，前一层不过就不看后面。不需要引入分数。

### 三、把「测试没做成」和「测出来很差」分开

Veridrop 的 `fatal_run_error()` 专门识别两类错误并拒绝出分：

```
credit balance is too low / insufficient_quota / billing
model_not_found / model not available / 无可用渠道
```

理由很直接：报一个 35 分，和说「这个账号跑不了这个测试」，是两回事。前一种是误导。

MQ v0.2.0 的结论分层已经在做同样的事：`endpoint_unreachable` / `auth_rejected` / `model_not_found` 都不进入协议评分。两边独立收敛到了同一个设计。

### 四、几个极便宜且决定性的检查

| 检查 | 为什么值得做 |
|---|---|
| **消息标识前缀** | 官方只保证 `msg_` / `toolu_` / `srvtoolu_` 前缀。中转如果返回 UUID 或 `tool_1`，说明不是官方原生实现。一次请求就能查，成本≈0 |
| **长短 prompt 的 input_tokens 增量** | 80 个简单英文词在 Anthropic tokenizer 下有稳定增量区间。偏离区间说明分词器不同或 usage 被改写 |
| **stream 与 non-stream 的 usage 一致** | 两条独立代码路径，虚报时容易对不上 |
| **output_tokens 不超 max_tokens** | 最简单粗暴的虚报识别 |
| **长上下文 needle-in-haystack** | 三层（32k / 100k / 200k）埋针，抓「宣传 1M 实际 200k」。这是高端欺诈唯一能测出来的手段 |

## 一个需要说清楚的地方

Veridrop 的 README 把 `thinking_signature` 称为「加密级真伪验证」，说 signature 是「Anthropic 服务端用密钥签名的加密产物，中转站理论上无法伪造」。

**但它的判定代码只检查签名存在与长度：**

```python
if not thinking_block_seen:      score = 0.0
elif not signature_received:     score = 30.0
elif len(signature_value) < 50:  score = 70.0
else:                            score = 100.0
```

`SIGNATURE_MIN_LEN = 50`，注释写的是「empirically > 100 chars, we settle for >= 50 as a generous lower bound」。**没有做任何服务端校验。**

这不是说它写错了 —— 「伪造成本高」是成立的，长度检查确实能排除占位串和完全不返回的情况。但「加密级」这个词描述的是伪造难度，不是验证强度。用户读到「唯一年内可加密验证、不可绕过的真伪指标」，容易以为有个数学证明在后面。

## MQ 补了什么

### 照搬的两项

- **`probe_message_id`**：`id` 前缀 `msg_`、`type == "message"`、`role == "assistant"`、`response.model` 含 `claude`、`tool_use.id` 前缀 `toolu_`、`server_tool_use.id` 前缀 `srvtoolu_`。任一不符 → FAIL，进 `identity_suspect`。
- **`probe_token_usage`**：短 prompt（`Reply with exactly: ok`）与长 prompt（追加 80 个 ` apple`）的 `input_tokens` 增量应落在 `[45, 140]`；`output_tokens` 不得超过 `max_tokens + 4`。

### 升级的一项

`probe_thinking` 从「INFO：signature 字段存在」改成三级判定：

| 情况 | 级别 |
|---|---|
| 端点拒绝 thinking 参数（模型不支持） | INFO，不算缺陷 |
| 返回 200 但没有 thinking 块 | **FAIL**，能力被剥离或后端不是声明模型 |
| 有 thinking 块但没有 signature 字段 | **FAIL**，不是官方端点直接产出 |
| signature 存在但 < 50 字符 | WARN，疑似占位串 |
| signature 存在且 ≥ 50 字符 | PASS（长度合格，真伪待回验） |

### 多出来的一项：真正的签名回验

这是 Veridrop 没做的，也是唯一能给出密码学强度结论的手段。

**做法**：把中转返回的 assistant content（含 `thinking` 块和 `signature`）原样回放给**官方端点**，追加一轮用户消息，让官方继续对话。

Anthropic 服务端会校验 signature 是否由自己的私钥签发：

- 官方 **200** → 签名是真品。后端确实是所声明的 Anthropic 模型。**这是数学级的证据，不是启发式。**
- 官方 **400 且错误提到 signature** → 签名是伪造或改写过的。
- 其他状态码 → 无法判定，记 INFO，**绝不当作通过**。

需要 `--official-key`。没有官方 Key 时该项显示 INFO 并说明原因，不扣分也不加分。

## 没做的

**长上下文 needle-in-haystack。** 价值很高（能抓「宣传 1M 实际 200k」），但成本随档位从 $0.05 涨到 $8，且必须由用户的 Key 支付。做成默认项会让 PR 验证变得昂贵。留作后续可选项 `--long-context`，不进默认路径。

**加权总分。** Veridrop 有 0-100 分和 `passed/marginal/failed` 三档。MQ 保留七级结论枚举，因为它对「下一步该做什么」的表达更精确，而且 PR 门禁只需要一个布尔值。分数适合排行榜，不适合门禁。

## 证据边界（仍然成立）

- 长度检查、前缀检查、token 增量检查都是**启发式**。它们能排除大量明显的换壳手法，但不能证明模型为真。
- 只有 `签名回验` 一项具备密码学强度，且它只覆盖「返回了 thinking 的模型」。
- 不支持 thinking 的模型，以及 OpenAI / Gemini 协议，都没有同等强度的验证手段 —— 这一点 Veridrop 也承认。
