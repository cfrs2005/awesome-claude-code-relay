# awesome-claude-code-relay

[![Providers](https://img.shields.io/badge/服务商-31-blue)](#-服务商目录)
[![MQ 引擎](https://img.shields.io/badge/MQ%20引擎-v0.2.0-purple)](mq/)
[![无 AFF](https://img.shields.io/badge/定位-无AFF中立目录-green)](#️-原则)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Claude Code / Claude API 中转站社区目录 + 自动化基础验证（MQ / ModelQuality）**
> 思路对标 VPS 圈的 NodeQuality：统一探针、统一报告格式、任何人可复现。

---

## ⚠️ 先读这个

**收录 ≠ 推荐。验证通过 ≠ 安全可信。**

- 本目录**不背书任何服务商**。没有星级、没有排名、没有返利（AFF）链接——本仓库 2026-11 起已清除全部推广参数，且自动拒绝新增。
- 我们**没有能力、也不承诺**验证：模型是否为真（只能给出证据强弱）、服务商是否**留存、转卖、滥用**你的请求、代码与 Key。任何中转站理论上都能完整看到你的明文请求。
- 请**慎重选择**：个人实验可用中转；公司项目、商业代码、含密钥的仓库 → 请使用官方 API。
- 收录条目来自社区自荐，历史上从未做过统一测试，`未验证` 是诚实的默认状态。

---

## 🌐 在线站点

**https://mq.80aj.com** —— 服务商目录 + 每份验证报告（完整探针结果与复现命令）。
目录状态由合并后的报告自动回写；报告由提交者在本机跑出，站点只存档与呈现。

引擎分发按 tag 固定（当前 `v0.2.0`），不跟随 `main`——报告里写的 `engine` 才算数。

## 🚀 发布与部署

| 环节 | 做法 |
|---|---|
| 改动校验 | `ci.yml`：91 个用例（含引擎端到端、门禁状态机、渲染快照、workflow 语法）+ ruff + README 漂移检查 |
| 发布 | 打 tag `v*` → `deploy.yml` 打包（Hub + 契约层 + 渲染器 + 引擎副本 + 字体 + 目录索引）→ 上传 → 重启 → 校验 healthz 版本一致，不一致自动回滚 |
| 回滚 | 部署脚本保留上一版，健康检查不过即自动回退；也可手动 `workflow_dispatch` 重跑 |

## 📋 服务商目录

按验证状态排序（同级按名称），**排序不代表任何推荐**。`API 端点` 由提交者填写，未经核实。

<!-- providers:start -->
| 验证状态 | 服务商 | 家族 | 类型 | 官网 | API 端点 |
|---|--------|:---:|:---:|------|------------------------------|
| ✅ 基础验证通过 | LINUX DO Hub | OpenAI ⚠️ 非 Claude | 公益 | [linux.do](https://linux.do) | `https://hub.linux.do` |
| – 未验证 | 86GameStore | OpenAI ⚠️ 非 Claude | 商业 | [86gamestore.com](https://86gamestore.com) | `https://api.86gamestore.com` |
| – 未验证 | 88code | Claude | 商业 | [www.88code.org](https://www.88code.org) | `—` |
| – 未验证 | AICodeMirror | Claude | 商业 | [www.aicodemirror.com](https://www.aicodemirror.com) | `—` |
| – 未验证 | AIMZ | Claude | 商业 | [mzlone.top](https://mzlone.top) | `—` |
| – 未验证 | AI快站 AIFast | Claude | 商业 | [www.aifast.hk](https://www.aifast.hk) | `—` |
| – 未验证 | Anyrouter | Claude | 公益 | [anyrouter.top](https://anyrouter.top) | `—` |
| – 未验证 | Code By AI | Claude | 商业 | [www.codebyai.net](https://www.codebyai.net) | `—` |
| – 未验证 | CodeCli | Claude | 商业 | [www.code-cli.cn](https://www.code-cli.cn) | `—` |
| – 未验证 | CodeI Lab | Claude | 商业 | [www.codeilab.com](https://www.codeilab.com) | `—` |
| – 未验证 | CoderPlan | Claude | 商业 | [coderplan.ai](https://coderplan.ai) | `—` |
| – 未验证 | Cubence | Claude | 商业 | [cubence.com](https://cubence.com) | `—` |
| – 未验证 | Duckcoding | Claude | 商业 | [duckcoding.com](https://duckcoding.com) | `https://jp.duckcoding.com` |
| – 未验证 | EasyChat | Claude | 商业 | [easychat.site](https://easychat.site) | `—` |
| – 未验证 | Elysiver | Claude | 商业 | [elysiver.h-e.top](https://elysiver.h-e.top) | `—` |
| – 未验证 | FoxCode | Claude | 商业 | [foxcode.rjj.cc](https://foxcode.rjj.cc) | `—` |
| – 未验证 | GalaxyCode | Claude | 商业 | [nf.video](https://nf.video) | `—` |
| – 未验证 | Ikuncode | Claude | 商业 | [www.ikuncode.cc](https://www.ikuncode.cc) | `—` |
| – 未验证 | JikeAI | Claude | 商业 | [magic666.top](https://magic666.top) | `—` |
| – 未验证 | MikuCode | Claude | 商业 | [mikucode.xyz](https://mikucode.xyz) | `—` |
| – 未验证 | PackyCode | Claude | 商业 | [www.packyapi.com](https://www.packyapi.com) | `—` |
| – 未验证 | Privnode | Claude | 商业 | [privnode.com](https://privnode.com) | `—` |
| – 未验证 | Runanytime | Claude | 商业 | [runanytime.hxi.me](https://runanytime.hxi.me) | `—` |
| – 未验证 | SSSAiCode | Claude | 商业 | [www.sssaicode.com](https://www.sssaicode.com) | `—` |
| – 未验证 | TeamoRouter | Claude | 商业 | [teamorouter.com](https://teamorouter.com) | `—` |
| – 未验证 | TeapotRouter | Claude | 商业 | [teapotrouter.com](https://teapotrouter.com) | `—` |
| – 未验证 | Twinkle Model | Claude | 商业 | [big-model.smart-agi.com](https://big-model.smart-agi.com) | `—` |
| – 未验证 | Uucode | Claude | 商业 | [www.uucode.org](https://www.uucode.org) | `—` |
| – 未验证 | Xyai | Claude | 商业 | [new.xychatai.com](https://new.xychatai.com) | `—` |
| – 未验证 | YesCode | Claude | 商业 | [co.yes.vg](https://co.yes.vg) | `—` |
| – 未验证 | 智谱 BigModel | Claude | 商业 | [bigmodel.cn/](https://bigmodel.cn/) | `https://open.bigmodel.cn/api/anthropic` |
<!-- providers:end -->

*验证状态说明见 [MQ 验证体系](#-mq-验证体系)。收录验证的做法见 [在你的 PR 里贴一份 MQ 报告](#-收录验证在你的-pr-里贴一份-mq-报告)。*

---

## 🔬 MQ 验证体系

[MQ 引擎](mq/)（`mq/mq.py`，纯标准库、单文件、可离线自检）对 Anthropic 兼容端点做标准化检测：

| 维度 | 检测内容 | 结论边界 |
|------|----------|----------|
| 模型目录 | `GET /v1/models`：声明模型是否存在、目录家族构成（claude / gpt / glm …） | 只反映「它声称提供什么」 |
| 目录变化 | 与上一次测试对比新增/消失的模型；**家族构成是否翻转** | 换上游最直接的信号 |
| 协议 | Messages 结构、SSE 事件序列、system 透传、tool_use 闭环 | 结构性通过/失败 |
| 模型指纹 | **tokenizer 计数一致性** + `count_tokens` 指纹（与官方对照需逐字节一致） | 目前最强的换壳证据，仍非数学证明 |
| 身份自述 | 问模型"你是谁"（启发式） | **零证据力**，只记录不参与判定 |
| 性能 | TTFT、TPS（SSE 帧间统计）、p50/p95 延迟 | 环境相关，仅供参考 |
| 稳定性 | 重复调用成功率与错误分类 | 快照，非长期质量 |

**结论分级**：`基础验证通过` / `端点不可达` / `鉴权被拒` / `声明模型不存在` / `协议不兼容` / `行为异常` / `身份存疑`。
「端点挂了」和「协议不对」不再共用一个标签——它们对用户意味着完全不同的处置。

**明确不能证明的事**：thinking signature 字段存在 ≠ 密码学真实；任何短时测试都无法证明服务商不盗用数据。

## 🧪 自助测试（推荐）

用你自己的 Key 在本地跑，Key 不离开你的机器，零信任要求：

```bash
curl -fsSL https://raw.githubusercontent.com/cfrs2005/awesome-claude-code-relay/v0.2.0/mq/mq.py -o mq.py
python3 mq.py --base-url https://api.example.com --key sk-your-key
```

详见 [mq/README.md](mq/README.md)。

## 🤝 提交与收录规则

1. **必须先 Watch（关注）本仓库**。未关注项目的提交者，PR 会被自动化检查拒绝。Watch 入口：页面右上角 → Watch → All Activity。
2. 只修改 `providers/<id>.json`（模板见 [providers/schema.json](providers/schema.json) 与任一现有条目）。此类 PR 在校验通过后**自动合并**；触碰 README/workflow/脚本的 PR 一律转人工审查。
3. **任何链接不得携带 aff / invite / ref / code 等推广参数**——自动检查一票否决。
4. `models_claimed` 等字段是服务商声称，未经核实；描述性字段请保持中性，不写"稳定""高速"等营销词。
5. 自动合并的确定性依据是 **Providers Check** 工作流（schema / 推广参数 / 重复 id / URL 安全 / Watch 检查）；Claude/GLM 的分诊评论仅供参考，无合并权限。

## 🔑 收录验证：在你的 PR 里贴一份 MQ 报告

本项目**不接收你的 Key**，也不在你背后跑测试。流程和 VPS 圈的 NodeQuality 一样：
你自己跑、自己贴，我们只核验这份报告和 PR 声明的是不是同一个端点。

1. 提 PR 后，Action 会在 PR 下发一条指引评论，里面已经填好你这个条目的 `api_base` 和 `models_claimed`
2. 在**你自己的机器**上跑一次（Key 不离开本机）：

   ```bash
   curl -fsSL https://raw.githubusercontent.com/cfrs2005/awesome-claude-code-relay/v0.2.0/mq/mq.py -o mq.py
   python3 mq.py --base-url <你条目的 api_base> --key sk-your-key \
     --model <你声明的模型> --json report.json --markdown report.md
   ```

3. 把 `report.md` **全文**贴到 PR 评论里。第一行有一段 GitHub 上不可见的机器可读块，整份复制、不要手改
4. 评论 `/mq-done` 触发检查

### 核验规则（全部确定性，没有人工主观判断）

| 检查项 | 通过条件 |
|---|---|
| 报告存在 | PR 正文或评论里有可解析的 MQ 报告块 |
| 端点一致 | 报告里的 host == 条目 `api_base` 的 host（防「测 A 卖 B」） |
| 报告时效 | 测试时间在 30 天内 |
| 结论合格 | `基础验证通过`；其余结论说明端点本身有问题，需修复后重测 |

四项全过 → **自动合并**。合并后 `verification` 字段由报告自动回写。

维护者认为需要人工判断时，可打 `mq-manual` 标签转人工合并。

> 引擎能力与结论边界见 [mq/README.md](mq/README.md)；报告格式与设计取舍见
> [docs/2026-11-04-mq-report-gate.md](docs/2026-11-04-mq-report-gate.md)。

## ⚙️ Claude Code 配置（通用）

```bash
export ANTHROPIC_BASE_URL="https://your-relay.example.com"   # 中转站给你的端点，不带 /v1/messages
export ANTHROPIC_API_KEY="sk-your-api-key"                   # 中转站签发的 Key
claude
```

连通性自测：

```bash
curl "$ANTHROPIC_BASE_URL/v1/messages" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":16,"messages":[{"role":"user","content":"hi"}]}'
```

排障：`401/403` → 检查两个变量与 Key；确认 BASE URL 没带 `/v1/messages` 后缀。

---

## 🛡️ 免责声明

本仓库是社区信息聚合与自动化验证平台，不销售任何服务、不收认证费、不做出任何形式的担保。所有检测为快照式证据，不构成安全性、合规性、模型真实性的保证。使用任何第三方中转意味着你接受其可以接触到你的全部请求明文。因使用本目录信息造成的任何损失，本项目不承担责任。

## 📌 相关资源

- 在线可用性监控（第三方独立面板）：https://www.80aj.com/llm-monitor/

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg/repos=cfrs2005/awesome-claude-code-relay&type=Date)](https://star-history.com/#cfrs2005/awesome-claude-code-relay&Date)

## License

[MIT](LICENSE)

---

**关键词**：Claude Code, Claude API, API 中转站, 模型指纹验证, ModelQuality, Anthropic 兼容 API, LLM relay verification
