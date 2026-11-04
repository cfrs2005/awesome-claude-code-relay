# MQ 官方验证：临时 Key 安全架构

> 回答一个核心问题：**模型指纹验证，单纯 GitHub Action 能不能做？**
> 结论：**检测引擎可以跑在 Action 里，但外部提交者的临时 Key 绝不能只靠 Action 接收**。需要一个极简 HTTPS 入口（一个 Cloudflare Worker 量级），但不需要一个"网站"。

## 为什么纯 Action 不行

| 约束 | 后果 |
|------|------|
| 外部 PR 作者拿不到仓库 Secrets | 无法把 Key 安全注入 workflow |
| fork PR 的 `GITHUB_TOKEN` 只读，且 Secrets 不注入 fork 触发的 run | fork PR 上无法安全消费 Key |
| PR / Issue / 评论全公开，GitHub Events API 有缓存 | 任何贴在讨论区的 Key 等于已泄露（删除也没用） |
| PR 里改 workflow 不能带 Secrets 跑（pwn request） | 验证代码必须固定跑 main 分支版本 |
| workflow_dispatch / repository_dispatch 的 client_payload 明文出现在 run 页面 | Key 本体绝不能放进 dispatch payload |

## 架构（四组件、职责分离）

```
服务商                GitHub                     MQ Key 入口 (Worker)            MQ Verify (Action)
  │ 提交 PR            │                           │                              │
  ├───────────────────► providers/<id>.json        │                              │
  │                    │ Providers Check(确定性) ✅ │                              │
  │                    │ Claude/GLM 分诊(参考) 💬   │                              │
  │ GitHub 登录 + 绑定 PR 号，HTTPS 提交一次性 Key   │                              │
  ├───────────────────────────────────────────────► 内存暂存(TTL 15min)              │
  │                    │                           ├─ repository_dispatch ───────►│
  │                    │                           │  payload 只有 fetch_token     │
  │                    │                           │  （不含 Key）                  │
  │                    │                           │◄────────── 一次性读取 Key ─────┤
  │                    │ MQ 引擎(确定性代码) 运行     │   读后即焚                    │
  │                    │ 报告回贴 PR + 更新 verification 状态                        │
  │ 立即吊销测试 Key     │                           │                              │
```

| 组件 | 做什么 | 不做什么 |
|------|--------|----------|
| Providers Check（Action） | schema/推广参数/重复 id/URL/Watch 校验，**自动合并唯一依据** | 不接触 Key |
| Claude Code + GLM（Action） | PR 分诊、报告中文解读 | 不判断模型真假、无合并权限、不接触 Key |
| MQ 引擎（`mq/mq.py`） | 发请求、收证据、算指标、出报告 | 不上报第三方、不落盘 Key |
| Key 入口（Worker） | GitHub OAuth 身份 + PR 绑定 + 一次性暂存 | 不写库、不打日志、TTL 过期即焚 |

## Key 入口（Worker）最小 API

```
POST /sessions   {github_oauth_code, pr_number}
  → 200 {session_token}            # 绑定 GitHub login + PR，校验 PR 作者与 login 一致
POST /keys/:session_token  {key, base_url?}
  → 202 {fetch_url, fetch_token, expires_in:900}
  # 服务端：Key 加密后仅存进程内存（键=fetch_token 的哈希），
  #         随即 repository_dispatch: mq-verify {pr_number, provider_id, fetch_url, fetch_token}
POST /fetch       Authorization: Bearer <fetch_token>
  → 200 {key}                      # 一次性；读取或 15 分钟 TTL 后永久删除
```

实现要点：

- **零持久化**：无 KV/无数据库；单实例内存 + TTL。重启即丢（可接受：丢了重新提交）。
- **一次性**：`fetch_token` 哈希为内存键，读取即 `delete`；重复读取返回 410。
- **payload 无 Key**：dispatch 到 GitHub 的 `client_payload` 只有 `fetch_url` + `fetch_token`，run 页面公开可见也不泄露。
- **Action 侧**（见 `mq-verify.yml`）：Key 写入 `/tmp/mq.key`（0600），步骤不 `set -x`，`always()` 清理；引擎只输出脱敏报告。
- **身份绑定**：只接受 PR 作者本人的 Key（`repos/{repo}/subscribers` 顺带核验 Watch 要求）。

## 威胁模型：诚实边界

能防：

- Key 出现在任何公开位置（PR/Issue/日志/dispatch payload/数据库）
- Key 被平台留存（内存 + 一次性 + TTL，无任何落盘路径）
- 恶意 PR 借验证流程执行自己的代码（引擎固定跑 main）

不能防（必须如实告知用户）：

- 执行期间 Key 短暂存在于 Worker 与 runner 内存中（内存级攻击/平台级记录超出本设计范围）
- 服务商提交他人被盗 Key 冒充验证
- 中转站在验证期间"临场装真"、事后切换（见下）

## 自动复测的凭证悖论

"Key 不落地" 与 "每周无人值守复测" 不可兼得。可选路径（按代价排序）：

1. **每次复测重新提交一次性 Key**（服务商人工操作，最诚实，推荐）
2. 服务商提供**限流专用验证 Key + 定期轮换**（落KV加密存储，需明确公示留存）
3. 仅被动收集社区自助报告（零信任要求，可信度打折）

## 路线图

- **P0（已完成）**：目录去 AFF、结构化数据、确定性 PR 校验 + Watch 门槛 + 自动合并、MQ 引擎与自助测试、GLM 分诊
- **P1**：Key 入口 Worker 上线（可部署至个人 Cloudflare 账号，域名单独申请，勿与业务域名混用）
- **P2**：官方参考指纹库（定期用官方端点刷新 tokenizer 计数基线，随仓库发布版本化）
- **P3**：社区自助报告聚合页（任何用户跑 `mq.py` 的报告可自愿提交，标注"自报证据"）

## 产品原则

无 AFF、不收认证费、不出售排名；测试标准、代码、结果尽量公开；结论只陈述证据强度，不替用户做选择。
