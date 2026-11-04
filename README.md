# awesome-claude-code-relay

[![Providers](https://img.shields.io/badge/服务商-24-blue)](#-服务商目录)
[![MQ 引擎](https://img.shields.io/badge/MQ%20引擎-v0.1.0-purple)](mq/)
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

## 📋 服务商目录

按验证状态排序（同级按名称），**排序不代表任何推荐**。`API 端点` 由提交者填写，未经核实。

<!-- providers:start -->
| 验证状态 | 服务商 | 类型 | 官网 | API 端点（Anthropic 兼容） |
|---|--------|:---:|------|------------------------------|
| – 未验证 | 86GameStore | 商业 | [86gamestore.com](https://86gamestore.com) | `https://api.86gamestore.com` |
| – 未验证 | 88code | 商业 | [www.88code.org](https://www.88code.org) | `—` |
| – 未验证 | AICodeMirror | 商业 | [www.aicodemirror.com](https://www.aicodemirror.com) | `—` |
| – 未验证 | AIMZ | 商业 | [mzlone.top](https://mzlone.top) | `—` |
| – 未验证 | Anyrouter | 公益 | [anyrouter.top](https://anyrouter.top) | `—` |
| – 未验证 | CodeCli | 商业 | [www.code-cli.cn](https://www.code-cli.cn) | `—` |
| – 未验证 | Cubence | 商业 | [cubence.com](https://cubence.com) | `—` |
| – 未验证 | Duckcoding | 商业 | [duckcoding.com](https://duckcoding.com) | `https://jp.duckcoding.com` |
| – 未验证 | EasyChat | 商业 | [easychat.site](https://easychat.site) | `—` |
| – 未验证 | Elysiver | 商业 | [elysiver.h-e.top](https://elysiver.h-e.top) | `—` |
| – 未验证 | FoxCode | 商业 | [foxcode.rjj.cc](https://foxcode.rjj.cc) | `—` |
| – 未验证 | GalaxyCode | 商业 | [nf.video](https://nf.video) | `—` |
| – 未验证 | Ikuncode | 商业 | [www.ikuncode.cc](https://www.ikuncode.cc) | `—` |
| – 未验证 | JikeAI | 商业 | [magic666.top](https://magic666.top) | `—` |
| – 未验证 | MikuCode | 商业 | [mikucode.xyz](https://mikucode.xyz) | `—` |
| – 未验证 | PackyCode | 商业 | [www.packyapi.com](https://www.packyapi.com) | `—` |
| – 未验证 | Privnode | 商业 | [privnode.com](https://privnode.com) | `—` |
| – 未验证 | Runanytime | 商业 | [runanytime.hxi.me](https://runanytime.hxi.me) | `—` |
| – 未验证 | SSSAiCode | 商业 | [www.sssaicode.com](https://www.sssaicode.com) | `—` |
| – 未验证 | TeapotRouter | 商业 | [teapotrouter.com](https://teapotrouter.com) | `—` |
| – 未验证 | Twinkle Model | 商业 | [big-model.smart-agi.com](https://big-model.smart-agi.com) | `—` |
| – 未验证 | Uucode | 商业 | [www.uucode.org](https://www.uucode.org) | `—` |
| – 未验证 | Xyai | 商业 | [new.xychatai.com](https://new.xychatai.com) | `—` |
| – 未验证 | YesCode | 商业 | [co.yes.vg](https://co.yes.vg) | `—` |
| – 未验证 | 智谱 BigModel | 商业 | [bigmodel.cn/](https://bigmodel.cn/) | `https://open.bigmodel.cn/api/anthropic` |
<!-- providers:end -->

*验证状态说明见 [MQ 验证体系](#-mq-验证体系)。申请验证的入口见 [官方验证（临时 Key）](#官方验证临时-key)。*

---

## 🔬 MQ 验证体系

[MQ 引擎](mq/)（`mq/mq.py`，纯标准库、单文件、可离线自检）对 Anthropic 兼容端点做标准化检测：

| 维度 | 检测内容 | 结论边界 |
|------|----------|----------|
| 协议 | Messages 结构、SSE 事件序列、system 透传、tool_use 闭环 | 结构性通过/失败 |
| 模型指纹 | **tokenizer 计数一致性**（同请求 input_tokens 必须恒定；与官方端点对照需逐字节一致） | 目前最强的换壳证据，仍非数学证明 |
| 身份旁证 | 自称身份、注入泄漏探测（启发式） | 仅旁证，可被上游伪造 |
| 性能 | TTFT、TPS（SSE 帧间统计）、p50/p95 延迟 | 环境相关，仅供参考 |
| 稳定性 | 重复调用成功率与错误分类 | 快照，非长期质量 |

**结论分级**：`基础验证通过` / `行为异常` / `身份存疑` / `证据不足`。

**明确不能证明的事**：thinking signature 字段存在 ≠ 密码学真实；任何短时测试都无法证明服务商不盗用数据。

## 🧪 自助测试（推荐）

用你自己的 Key 在本地跑，Key 不离开你的机器，零信任要求：

```bash
curl -fsSL https://raw.githubusercontent.com/cfrs2005/awesome-claude-code-relay/main/mq/mq.py -o mq.py
python3 mq.py --base-url https://api.example.com --key sk-your-key
```

详见 [mq/README.md](mq/README.md)。

## 🤝 提交与收录规则

1. **必须先 Watch（关注）本仓库**。未关注项目的提交者，PR 会被自动化检查拒绝。Watch 入口：页面右上角 → Watch → All Activity。
2. 只修改 `providers/<id>.json`（模板见 [providers/schema.json](providers/schema.json) 与任一现有条目）。此类 PR 在校验通过后**自动合并**；触碰 README/workflow/脚本的 PR 一律转人工审查。
3. **任何链接不得携带 aff / invite / ref / code 等推广参数**——自动检查一票否决。
4. `models_claimed` 等字段是服务商声称，未经核实；描述性字段请保持中性，不写"稳定""高速"等营销词。
5. 自动合并的确定性依据是 **Providers Check** 工作流（schema / 推广参数 / 重复 id / URL 安全 / Watch 检查）；Claude/GLM 的分诊评论仅供参考，无合并权限。

## 🔑 官方验证（临时 Key）

新收录条目必须完成 MQ 官方验证，入口：**https://mq.80aj.com**

1. 提 PR 后，Action 自动把 PR 声明的 `api_base` 注册到验证 Hub，并在 PR 下发这个 PR 的专属验证地址（`https://mq.80aj.com/pr/<PR号>`）
2. **PR 作者**打开这个专属地址 → 完成绑定 → 提交**一次性临时 Key**（仅存内存，20 分钟过期，触发即焚）→ 点击运行验证
3. 引擎在服务端执行，报告自动回贴 PR，`verification` 状态自动更新
4. 实测端点必须与 PR 声明的 `api_base` 完全一致（防"测 A 卖 B"），验证通过 + 全部检查通过后自动合并

请提交**低额度、短有效期**的专用 Key，验证完成后立即吊销。架构与安全边界：[docs/verification-design.md](docs/verification-design.md)

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
