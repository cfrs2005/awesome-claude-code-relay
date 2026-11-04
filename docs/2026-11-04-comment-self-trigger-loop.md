# 事故复盘：providers-check 评论自触发死循环（PR #23）

> 一句话：把 `/mq-done` 当全文字匹配的触发条件，叠加"失败提示里也写着 `/mq-done`"和"评论用有回灌能力的 PAT 发出"，
> 让一条失败评论变成永动机——**24 分钟 262 条评论、777 次工作流运行**，最后靠 GitHub 限流才被动停下。

- **发现时间**：2026-11-04 15:33 UTC（维护者看到 PR 上连续刷屏）
- **影响面**：单个 PR（#23）的评论区 + Actions 运行次数；无数据、无密钥、无仓库内容受损
- **修复版本**：`32435e7`（已直接进入 main）
- **状态**：已修复、已清理、已验证无残留

## 1. 时间线（UTC）

| 时间 | 事件 |
|---|---|
| 14:56:47 | PR #23 打开（含 `providers/86gamestore.json` + `mq/mq.py` + `.github/workflows/claudecode.yml`） |
| 14:56:59 | `register-verify` 发布验证指引评论，第 5 步写着"在 PR 下评论 **`/mq-done`** 触发自动合并" ← **点火** |
| 14:57:00 | `providers-check` 被 `issue_comment` 触发；校验失败（含 `providers/` 之外的文件） |
| 14:57:0x | 失败评论发布，正文含"完成验证后评论 **/mq-done**" ← **回灌进触发条件** |
| 14:57–15:20 | 自循环：失败 → 评论 → 触发 → 失败，重复约 262 次 |
| 15:20:46 | `addComment` 被 GitHub 限流拒绝（`GraphQL: was submitted too quickly`），链条断裂 |
| 15:37 | 修复提交 `32435e7` |
| 15:39 | 修复进入 main（`mq-bot` 同步 README 的 commit 在其之上，未回退改动） |
| 15:40–15:51 | 清理 259 条重复评论，保留 3 条（验证指引 / 代码评审 / 最新一条结果） |

## 2. 根因：三个条件同时成立才成环

```yaml
# 修复前
if: |
  github.event_name == 'pull_request' ||
  (github.event_name == 'issue_comment'
   && github.event.issue.pull_request != null
   && contains(github.event.comment.body, '/mq-done'))   # ← 条件①：全文字匹配
```

```yaml
# 修复后
if: |
  github.event_name == 'pull_request' ||
  (github.event_name == 'issue_comment'
   && github.event.issue.pull_request != null
   && github.event.comment.user.type != 'Bot'             # ← 排除机器人身份
   && startsWith(github.event.comment.body, '/mq-done'))  # ← 条件①：只认命令开头
```

| # | 条件 | 说明 |
|---|---|---|
| ① | 触发用 `contains()` 全文字匹配 | 评论正文里任何位置出现 `/mq-done` 都算命令 |
| ② | 自动化评论的正文自带触发词 | 指引评论、失败提示都写了"评论 /mq-done" |
| ③ | 评论用带回灌能力的身份发出 | `MQ_BOT_TOKEN` 是人工账号 PAT；**PAT 发出的评论会再次触发 `issue_comment`**，而 `GITHUB_TOKEN` 不会 |

只要三者在，就构成：**失败 → 发评论 → 评论触发 → 再失败**。少断任何一个都能停，本次全部断掉。

### 为什么 24 分钟才停

不是逻辑停的，是 GitHub 限流拦住的。失败评论发布失败 → 不产生新的 `issue_comment` 事件 → 链条才断。
换句话说：**这次是外部限流救了场，代码自身没有任何终止条件**。

## 3. 影响评估（含"会不会被封号"）

| 维度 | 实测 | GitHub 文档阈值 |
|---|---|---|
| 评论速率（峰值） | ≈14 次/分钟 | 内容生成类：80 次/分钟 |
| 24 分钟评论总量 | 262 条 | 500 次/小时 |
| 运行次数 | 777 次（Providers Check + Claude Code 各半） | 公开仓库不计费 |
| 跨用户打扰 | 0（无 @ 陌生人、无跨仓库评论） | spam 判定核心看"对其他用户的批量打扰" |
| 限流残留 | `core 4974/5000`、`graphql 4961/5000` | 无惩罚标记 |

结论：属"自身事故"，未达到 spam 判定线。但请注意文档里的红线原话——
*"Continuing to make requests while you are rate limited may result in the banning of your integration."*
本次每轮在 403 后仍会由下一轮重试，只是恰好被事件链中断；**若循环持续更久，"限流后继续请求"才是真正会挨刀的行为**。

## 4. 修复内容（`32435e7`）

1. **触发条件收紧**：`contains` → `startsWith('/mq-done')`，并排除 `comment.user.type == 'Bot'`。机器人生成的评论不以命令开头，永远打不通入口。
2. **结果评论改幂等**：带隐藏标记 `<!-- providers-check-result -->`，先查已有评论再 `PATCH` 就地更新。**即使以后逻辑再错，同一个 PR 也只会有 1 条评论。**
3. **串行化**：加 `concurrency: providers-check-<PR 号>`，评论风暴时排队而不是并发堆叠。
4. **正文中和触发词**：回贴 Hub 报告前，在正文的 `/mq-done` 中插入零宽字符（显示无变化，不再命中匹配）——纵深防御，防止未来任何"评论正文含触发词"的路径复活。

## 5. 验证

- YAML 解析通过；8 个 `run` 段全部 `bash -n` 通过。
- 失败评论正文以 `❌ **Providers Check 未通过**` 开头，`startsWith('/mq-done')` 为假 → 不触发（本地用同一份判断逻辑验证过）。
- 零宽字符中和后，原文仍可读，但 `contains` / `startsWith` 均返回假。
- 修复上线后无新增 `issue_comment` 触发运行（最后一次为真人的正常触发之外，仅有 `Sync README`）。

## 6. 遗留改进

- [ ] **自动化评论换专用身份**：`MQ_BOT_TOKEN` 仍为人工账号 PAT。一旦再出问题，消耗的是主账号的评论配额与信誉；应改用独立机器账号 PAT 或 GitHub App。
- [ ] **Hub 侧评论同样幂等**：`mq/hub/app.py` 回贴报告目前是"新发一条"，同一 PR 反复验证会累积评论，应改为带标记 upsert。
- [ ] **`claudecode.yml` 同类反模式**：`contains(body, '@claude')` 也是全文字匹配，建议加 `comment.user.type != 'Bot'`。目前只是被 skip，未成环。

## 7. 可复用自查清单（任何"评论 → 触发工作流"的设计）

1. 触发条件能否被**本工作流自己发出的内容**命中？→ 命令类一律 `startsWith`，不用 `contains`。
2. 自动化评论用的 token 是 `GITHUB_TOKEN` 还是 PAT？→ **PAT 会回灌事件，`GITHUB_TOKEN` 不会**。
3. 评论是"每次新发"还是"就地更新"？→ 只有后者在逻辑出错时有上限。
4. 有没有按 PR / issue 的 `concurrency` 收口？
5. 被限流后是继续重试还是终止？→ 403/429 必须退避，否则会从"限流"升级为"处置"。
