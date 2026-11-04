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
  │ GitHub OAuth 登录 ──────────────────────────────────────► 身份=PR 作者，强校验
  │ 提交一次性临时 Key ─────────────────────────────────────► 仅内存，TTL 20 分钟
  │ 点击「运行验证」 ───────────────────────────────────────► 服务端跑 engine/mq.py
  │                      │                                │  Key 一次性消费即焚
  │                      │ ◄────────────────────────────── 报告回贴 PR 评论
  │                      │ ◄────────────────────────────── verification 状态提交 PR 分支
  │                      │ providers-check:               │
  │                      │  schema/aff/Watch/Hub 门禁 ✅ ──► 自动合并
  │                      │ sync-readme: 重新生成目录表      │
  │ 吊销测试 Key           │                                │
```

| 组件 | 位置 | 做什么 | 不做什么 |
|------|------|--------|----------|
| register-verify（Action） | GitHub | 从 PR 提取 `api_base`/`model`/`provider_id` 注册到 Hub，发指引评论 | 不接触 Key |
| MQ Hub | ntt197 | GitHub OAuth 身份绑定、Key 内存暂存（TTL/一次性）、运行引擎、回贴报告、提交状态 | 不落盘 Key、不打 Key 日志、不写库 |
| MQ 引擎（`mq/mq.py`） | ntt197 | 确定性检测：协议/tokenizer 一致性/TTFT/TPS/稳定性 | 不上报第三方 |
| providers-check（Action） | GitHub | 确定性校验 + Watch 门槛 + **Hub 门禁**（新收录必须验证通过），自动合并唯一依据 | AI 结论不参与门禁 |
| Claude Code + GLM（Action） | GitHub | PR 分诊与报告解读（参考信息） | 不判断真假、无合并权限、不接触 Key |

## 关键安全属性

- **实测端点 = PR 声明端点**：URL 由 Action 从 PR 提取，用户在 Hub 只能提交 Key；若用覆盖端点提测，结果标记 `base_mismatch` → 门禁拦截，必须先改 PR。防止"测 A 卖 B"。
- **身份强绑定**：只有 PR 作者（GitHub OAuth 登录）能提交 Key 与触发测试；PR 必须 open。
- **Key 生命周期**：HTTPS 传输 → 进程内存 → 触发即消费（一次性）→ 或 20 分钟 TTL 自动焚毁。不写库、不写日志、不进 GitHub。
- **`verified` 判定**：`verdict=basic_passed` 且端点一致，二者缺一不可。
- **绕过通道**：维护者打 `mq-manual` 标签 → 跳过 Hub 门禁 + 禁用自动合并，转人工。
- **引擎供应链**：Hub 只运行部署目录内固定的 `engine/mq.py`（部署时从本仓库 main 拷贝），绝不执行 PR head 代码。

## Hub API（供集成）

```
POST /api/prs                 X-Hub-Token: <Action 共享密钥>   # 注册（register-verify 调用）
GET  /api/prs/{n}             X-Hub-Token                      # 门禁查询（providers-check 调用）
POST /api/prs/{n}/key         会话（PR 作者）                   # 提交临时 Key {key, base_url?}
POST /api/prs/{n}/run         会话（PR 作者）                   # 触发测试，返回结果
GET  /reports/{n}/{ts}.md                                      # 公开报告
GET  /healthz                                                   # 健康检查
```

## 部署（ntt197）

- 代码：`/opt/mq-hub/app.py`、`/opt/mq-hub/engine/mq.py`、`/opt/mq-hub/venv`
- 配置：`/opt/mq-hub/env`（0600；HUB_TOKEN / SESSION_SECRET / GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET / GITHUB_TOKEN / BASE_URL）
- 进程：systemd `mq-hub.service`（uvicorn 127.0.0.1:8710）
- 入口：Caddy `mq.80aj.com` → 127.0.0.1:8710（自动 HTTPS）
- 数据：`/opt/mq-hub/data/`（prs.json 绑定关系 + reports/ 历史报告，均不含 Key）

引擎升级流程：本仓库 main 更新 `mq/mq.py` → 服务器 `rsync` 同步 → `systemctl restart mq-hub`。

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
