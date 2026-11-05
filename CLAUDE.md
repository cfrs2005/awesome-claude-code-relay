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
| `mq/mq.py` | MQ 检测引擎：模型目录 / 端点可用性 / 协议兼容性 / 身份证据（含签名回验）/ 稳定性 |
| `scripts/check_mq_report.py` | 核验 PR 里贴的 MQ 报告（存在性、端点一致性、时效、结论） |
| `scripts/pr_guide.py` | 生成 PR 指引评论（告诉提交者怎么跑、怎么贴） |
| `scripts/check_providers.py` | PR 确定性校验（自动合并的依据之一） |
| `scripts/update_verification.py` | 合并后把报告结论回写到条目 `verification` 字段 |
| `scripts/build_readme.py` | 从 providers/*.json 生成 README 目录表 |
| `.github/workflows/providers-check.yml` | PR 校验 + Watch 检查 + MQ 报告门禁 + 自动合并 |
| `.github/workflows/mq-guide.yml` | PR 打开时发布「怎么跑 MQ、怎么贴报告」指引 |
| `.github/workflows/claudecode.yml` | GLM 驱动的 Claude Code（@claude 交互 + PR 分诊 + 报告解读） |
| `mq/hub/` | **可选**：报告托管与浏览服务，不参与合并门禁 |
| `docs/verification-design.md` | 验证流程、威胁模型（公开透明文档） |
| `docs/README.md` | docs 索引；新增文档按 `YYYY-MM-DD-<english-kebab>.md` 命名并登记 |

## 收录验证的形态（NQ 式，勿改回服务端代跑）

对照 VPS 圈的 NodeQuality：**测量在用户自己的机器上发生，平台只做核验和呈现。**

- 提交者本地跑 `mq/mq.py`，把报告全文贴进 PR。**我们不接收、不转发、不存储任何 Key。**
- 报告第一行是 `<!--MQ-REPORT:<base64>-->` 机器可读块，由引擎生成，用户整份复制。
  它是结构化输入，**不是防伪凭证**——报告仍是可读可改的 markdown，信任来自端点一致性与社区监督。
- 门禁只做四件确定性的事：报告存在、host 一致、未过期（30 天）、结论合格。
  不做人工主观评审，也不用大模型判定放行。
- 大模型（GLM）只负责**解读**报告写人话，永远不参与放行判定。

**不要**把流程改回「提交绑定码 → 上传临时 Key → 服务端跑测试」。那会重新引入
密钥托管风险和审核式产品形态，两件事都不是本项目要的。

报告由提交者在本地生成并贴进 PR。仓库侧只解析报告首行的 `<!--MQ-REPORT:...-->` 机器可读块，不代跑、不接收 Key。历史 PR 可能仍指向旧的 Hub 工作台地址 `https://mq.80aj.com/pr/<PR号>`（`mq/hub/` 保留为可选服务，不在关键路径上）。

> 运维细节不写入仓库。凭证只通过受控的运行环境和 CI Secret 提供，绝不进入代码、文档、评论或报告。

## PR 规则（AI 助手必须遵守的执行边界）

1. 提交者必须已 **Watch** 本仓库（由 providers-check 用 `repos/{repo}/subscribers` 端点核验）。未 Watch → 不合并。
2. 自动合并**仅限** `providers/*.json` 且全部确定性检查通过（含 MQ 报告核验）；含 README / workflow / 脚本变更的 PR 一律转维护者人工审查。
3. AI（@claude / GLM 分诊）的结论是**参考信息**，永远不能替代 `providers-check` 的确定性校验，AI 没有合并权限。
4. 绝不在 PR、Issue、评论、日志中索要或粘贴 API Key。**本仓库的流程根本不接收 Key** —— Key 只留在提交者自己的机器上；任何要求提交者交出 Key 的说法都是错的。
5. MQ 引擎只由提交者在本地运行；仓库侧只解析报告里的机器可读块，绝不执行 PR head 的代码。合并只发生在 providers-check 全绿之后。

CI 凭证只配置在受控的仓库 Secret 和运行环境中。公开文档不列出凭证名称、存储位置或运维路径。

## MQ 验证语义

结论按「用户下一步该做什么」分层，不允许把不同故障塞进同一个标签：

| 结论 | 含义 | Hub verified |
|------|------|:---:|
| `basic_passed` | 协议与行为特征正常（**不是**"安全"或"模型为真"的证明） | ✅ |
| `endpoint_unreachable` | 网络不通、超时、或上游 5xx | ❌ |
| `auth_rejected` | 401/403，Key 无效或无权限 | ❌ |
| `model_not_found` | 声明模型不在 `/v1/models` 中（PR 声明本身不成立） | ❌ |
| `protocol_incompatible` | Messages 路径 404 或响应不符合规范 | ❌ |
| `behavior_anomaly` | 核心协议项（流式 / system / tools）失败 | ❌ |
| `identity_suspect` | tokenizer 不一致、官方对照不符、或目录家族构成翻转 | ❌ |
| `evidence_insufficient` | 保留值，仅用于兼容历史报告 | ❌ |

另有三个状态位不属于结论：`unverified` 未验证、`pending` 验证中、`inconclusive` 旧值。

**模型自述（"你是谁"）零证据力**，只记录不参与判定。

可靠的身份证据按强度排序：
1. **签名回验**（唯一密码学级）：把中转返回的 thinking signature 回放给官方端点，官方接受即为真品。需 `--official-key`。
2. `count_tokens` 指纹与官方对照
3. 响应标识前缀（`msg_` / `toolu_` / `srvtoolu_`）
4. `/v1/models` 目录的家族构成及其跨批次变化

⛔ **不要把 signature 的长度检查说成「加密验证」**。长度只能排除占位串，这是启发式，不是证明。

## 本地开发

```bash
python3 mq/mq.py --self-test                 # 引擎离线自检
python3 scripts/build_readme.py              # 重新生成 README 目录表
python3 scripts/check_providers.py --base origin/main --head <sha>   # 本地跑 PR 校验
```

仓库语言：中文。License：MIT。
