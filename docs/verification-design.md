# MQ 官方验证：临时 Key 安全架构（Hub 部署于自有服务器）

> 回答核心问题：**模型指纹验证，单纯 GitHub Action 能不能做？**
> 结论：**检测引擎可以跑在服务器上，但外部提交者的临时 Key 绝不能只靠 GitHub 侧接收**。方案是一个部署在自有服务器（ntt197）的 MQ Hub，GitHub Action 只负责提取待测 URL 与门禁。

## 架构

```
提交者                  GitHub                          MQ Hub (ntt197, mq.80aj.com)
  │ 提交 PR              │                                │
  ├─────────────────────► providers/<id>.json             │
  │                      │ register-verify:               │
  │                      │  提取 api_base/model ──────────► /api/prs 注册（HUB_TOKEN）
  │                      │  发布指引评论（入口链接）         │
  │ 在 PR 下评论绑定码 ──────────────────────────────────────► 校验评论者 == PR 作者（无需 OAuth）
  │                      │                                │  → 发会话（7 天）
  │ 提交一次性临时 Key ─────────────────────────────────────► 仅内存，TTL 20 分钟
  │ 点击「运行验证」 ───────────────────────────────────────► 服务端跑 engine/mq.py
  │                      │                                │  Key 一次性消费即焚
  │                      │ ◄────────────────────────────── 报告回贴 PR 评论
  │ 评论 /mq-done ───────►│ providers-check(重跑):          │
  │                      │  schema/aff/Watch/Hub 门禁 ✅   │
  │                      │  全绿 → 直接 squash 合并         │
  │                      │ sync-readme: 解析 (#N) ◄──────── Hub 查询验证结果
  │                      │  回写 verification + 重建目录表   │
  │ 吊销测试 Key           │                                │
```

| 组件 | 位置 | 做什么 | 不做什么 |
|------|------|--------|----------|
| register-verify（Action） | GitHub | 从 PR 提取 `api_base`/`model`/`provider_id` 注册到 Hub，发指引评论 | 不接触 Key |
| MQ Hub | ntt197 | 绑定码身份验证（PR 评论=GitHub 身份证明）、Key 内存暂存（TTL/一次性）、运行引擎、回贴报告 | 不落盘 Key、不打 Key 日志、不执行合并 |
| MQ 引擎（`mq/mq.py`） | ntt197 | 确定性检测：协议/tokenizer 一致性/TTFT/TPS/稳定性 | 不上报第三方 |
| providers-check（Action） | GitHub | 确定性校验 + Watch 门槛 + **Hub 门禁**（`/mq-done` 触发重跑），全绿直接合并 | AI 结论不参与门禁 |
| sync-readme（Action） | GitHub | 合并后解析 `(#N)` 回写 verification 状态 + 重建目录表 | 不接触 Key |
| Claude Code + GLM（Action） | GitHub | PR 分诊与报告解读（参考信息，Key 未配置时优雅跳过） | 不判断真假、无合并权限、不接触 Key |

## 关键安全属性

- **实测端点 = PR 声明端点**：URL 由 Action 从 PR 提取，用户在 Hub 只能提交 Key；若用覆盖端点提测，结果标记 `base_mismatch` → 门禁拦截，必须先改 PR。防止"测 A 卖 B"。
- **身份强绑定（免 OAuth）**：提交者先在 Hub 获取一次性绑定码，用提交 PR 的 GitHub 账号在 PR 下评论该码；Hub 通过 PR 评论 API 校验「评论者 == PR 作者」后发会话。绑定码本身公开无妨——冒用它只能替作者"贡献"一次测试，无法获得任何秘密或绕过门禁；PR 必须 open。
- **Key 生命周期**：HTTPS 传输 → 进程内存 → 触发即消费（一次性）→ 或 20 分钟 TTL 自动焚毁。不写库、不写日志、不进 GitHub。
- **`verified` 动态计算**：门禁查询时实时比对 `tested_base == 当前 PR api_base`——验证通过后再偷改 PR 端点会立即失效（防"测后换端点"）。
- **绕过通道**：维护者打 `mq-manual` 标签 → 跳过 Hub 门禁 + 禁用自动合并，转人工。
- **引擎供应链**：Hub 只运行部署目录内固定的 `engine/mq.py`（部署时从本仓库 main 拷贝），绝不执行 PR head 代码。

## Hub API（供集成）

```
POST /api/prs                    X-Hub-Token  # 注册（register-verify 调用）
GET  /api/prs/{n}                X-Hub-Token  # 门禁查询（providers-check 调用，verified 动态计算）
GET  /api/prs                    公开          # 待验证 PR 列表（不含任何 Key）
POST /api/prs/{n}/bind/start     公开          # 获取一次性绑定码
POST /api/prs/{n}/bind/confirm   公开          # 校验 PR 评论中的绑定码 → 会话 Cookie
POST /api/prs/{n}/key            会话（作者）  # 提交临时 Key {key, base_url?}
POST /api/prs/{n}/run            会话（作者）  # 触发测试，返回结果
GET  /reports/{n}/{ts}.md        公开          # 验证报告
GET  /healthz                    公开          # 健康检查
```

## 部署

- Hub 自托管于独立服务器，公网入口 `https://mq.80aj.com`（Caddy 自动 HTTPS）
- 引擎以 main 分支部署副本运行，绝不执行 PR head 代码；升级 = 同步 `mq/mq.py` + 重启
- 数据目录仅存 PR 绑定关系与历史报告，**永不包含 Key**
- 服务器地址、密钥清单、运维手册等敏感细节保存在**不入库的本地目录** `docs-private/`（见 .gitignore），不进公开仓库

## 威胁模型：诚实边界

能防：

- Key 出现在 GitHub 任何公开位置（PR/评论/日志/dispatch payload）
- Key 被平台留存（内存 + 一次性 + TTL，无落盘路径）
- 冒名提测（OAuth 身份 = PR 作者）
- "测 A 卖 B"（端点一致性门禁）
- 恶意 PR 借验证执行代码（引擎固定于 main 部署副本）

不能防（如实告知）：

- 执行期间 Key 短暂存在于 Hub 与引擎进程内存
- 服务商提交他人被盗 Key 冒充验证
- 中转站"临场装真"、验证后切换上游（快照证据的固有局限）
- 服务商留存/转卖用户数据（任何短时测试都无法证明）

## 自动复测的凭证悖论

"Key 不落地" 与 "定期无人值守复测" 不可兼得。路线：

1. 每次复测重新提交一次性 Key（推荐，最诚实）
2. 社区自助报告聚合（任何人用 `mq/mq.py` 本地测试后自愿提交，标注"自报证据"）

## 路线图

- **P0（已完成）**：去 AFF 结构化目录、确定性 PR 校验 + Watch 门槛、MQ 引擎、GLM 分诊
- **P1（已完成）**：MQ Hub 上线（注册/登录/提测/回贴/门禁/自动合并闭环）
- **P2**：官方参考指纹库（tokenizer 计数基线版本化）
- **P3**：社区自助报告聚合页
