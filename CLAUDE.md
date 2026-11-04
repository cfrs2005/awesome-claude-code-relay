# CLAUDE.md

本仓库是 Claude Code / Claude API 中转站的**中立社区目录 + 自动化基础验证平台（MQ / ModelQuality）**。

## 定位（给在此仓库工作的 AI 助手）

- **无 AFF**：任何链接（website / api_base / notes）不得包含 aff、invite、ref、ic、code 等推广或返利参数。历史版本曾带推广参数，2026-11 已全部清除；发现新增推广参数必须在审查中标为一票否决。
- **收录 ≠ 推荐，验证通过 ≠ 安全**：禁止星级、排名、"稳定好用"式推荐话术。`models_claimed` 是服务商声称，不是事实。
- 目录数据是结构化的：`providers/<id>.json`（schema：`providers/schema.json`）。README 的目录表由 `scripts/build_readme.py` 生成，**不要手改标记区内的表格**。

## 关键文件

| 路径 | 作用 |
|------|------|
| `providers/*.json` | 服务商条目（每个服务商一个文件，id 与文件名一致；**一个 PR 只能新增一个**） |
| `providers/schema.json` | 条目 JSON Schema（自动校验依据） |
| `mq/mq.py` | MQ 检测引擎：协议 / tokenizer 计数一致性 / TTFT/TPS / 稳定性 / 身份旁证 |
| `mq/hub/app.py` | MQ Hub 服务（ntt197, mq.80aj.com）：OAuth 登录、临时 Key 内存暂存、运行引擎、回贴报告 |
| `scripts/check_providers.py` | PR 确定性校验（自动合并的依据之一） |
| `scripts/register_hub.py` | 从 PR 提取待测 URL 注册到 Hub（register-verify 调用） |
| `scripts/hub_gate.py` | Hub 验证门禁判定（providers-check 调用） |
| `scripts/build_readme.py` | 从 providers/*.json 生成 README 目录表 |
| `.github/workflows/providers-check.yml` | PR 校验 + Watch 检查 + Hub 门禁 + 自动合并 |
| `.github/workflows/register-verify.yml` | PR 变更注册到 Hub + 发布验证指引 |
| `.github/workflows/claudecode.yml` | GLM 驱动的 Claude Code（@claude 交互 + PR 自动分诊） |
| `docs/verification-design.md` | Hub 架构、威胁模型、部署说明 |

## PR 规则（AI 助手必须遵守的执行边界）

1. 提交者必须已 **Watch** 本仓库（由 providers-check 用 `repos/{repo}/subscribers` 端点核验）。未 Watch → 不合并。
2. 自动合并**仅限** `providers/*.json` 且全部确定性检查通过；含 README / workflow / 脚本变更的 PR 一律转维护者人工审查。
3. AI（@claude / GLM 分诊）的结论是**参考信息**，永远不能替代 `providers-check` 的确定性校验，AI 没有合并权限。
4. 绝不在 PR、Issue、评论、日志中索要或粘贴 API Key。官方验证的 Key 一律走一次性 HTTPS 入口（见 docs/verification-design.md）。
5. 检测引擎只以 **main 分支部署副本**运行（服务器 /opt/mq-hub/engine/mq.py），绝不执行 PR head 的代码（防 pwn request）；Hub 不执行合并，合并只发生在 providers-check 全绿之后。

## 必需 Secrets

| Secret | 用途 |
|--------|------|
| `ANTHROPIC_BASE_URL` | GLM 的 Anthropic 兼容端点（如 `https://open.bigmodel.cn/api/anthropic`） |
| `GLM_API_KEY` | GLM API Key，经 `ANTHROPIC_AUTH_TOKEN` 供 Claude Code 使用 |
| `MQ_HUB_URL` | MQ Hub 地址（`https://mq.80aj.com`），注册与门禁用 |
| `MQ_HUB_TOKEN` | Action ↔ Hub 共享密钥（服务器 /opt/mq-hub/env 中 HUB_TOKEN） |
| `MQ_BOT_TOKEN`（可选） | PAT，用于 fork PR 的评论/自动合并（fork PR 的默认 token 只读） |

## MQ 验证语义

- `basic_passed` 基础验证通过：协议与行为特征正常（**不是**"安全"或"模型为真"的证明）
- `behavior_anomaly` 行为异常：核心协议项失败
- `identity_suspect` 身份存疑：tokenizer 计数不一致 / 与官方对照不符 / 身份旁证异常
- `inconclusive` 证据不足、`unverified` 未验证、`pending` 验证中

## 本地开发

```bash
python3 mq/mq.py --self-test                 # 引擎离线自检
python3 scripts/build_readme.py              # 重新生成 README 目录表
python3 scripts/check_providers.py --base origin/main --head <sha>   # 本地跑 PR 校验
```

仓库语言：中文。License：MIT。
