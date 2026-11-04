# 历史 PR 一次性迁移清单

本清单记录发布切换前的 GitHub PR。它们不自动获得 MQ 验证状态。需要继续收录的条目，应重新提交为新的 `providers/<id>.json` PR，并使用新的 PR 专属验证地址。

| PR | 标题摘要 | 当前状态 | 处理方式 |
|---:|---|---|---|
| #3 | 修复表单 Header 与 API URL | MERGED | 历史维护 PR，不作为服务商验证记录 |
| #4 | 修复 Star History 项目地址 | MERGED | 历史维护 PR，不作为服务商验证记录 |
| #5 | AIFast HK 入口 | CLOSED | 已由 #13 替代；如继续收录，重新提交 provider JSON |
| #6 | CoderPlan | MERGED | 已迁移为 `providers/coderplan.json`；保持 `unverified`，待补端点后验证 |
| #13 | AI快站 AIFast | MERGED | 已迁移为 `providers/aifast.json`；保持 `unverified`，待补端点后验证 |
| #15 | Twinkle Model | CLOSED | 旧 README-only PR；历史资料只能作为未验证来源 |
| #16 | TeapotRouter | CLOSED | 旧 README-only PR；历史资料只能作为未验证来源 |
| #17 | TeamoRouter | MERGED | 已迁移为 `providers/teamorouter.json`；保持 `unverified`，待补端点后验证 |
| #21 | Code By AI | MERGED | 已迁移为 `providers/codebyai.json`；保持 `unverified`，待补端点后验证 |
| #22 | MQ 链路冒烟测试 | CLOSED | 测试 PR，不作为服务商条目 |
| #23 | 86GameStore | MERGED | 新规则切换期的首个验证样例；使用 `/pr/23` 作为专属工作台地址 |

## 迁移规则

1. 旧 PR 的 README 文字、星级、价格和注册链接不直接复制到新条目。
2. 每个要继续收录的服务商使用一个新的 `providers/<id>.json` PR。
3. PR 注册到 Hub 后，Action 必须发布 `https://mq.80aj.com/pr/<PR号>`。
4. 没有 `api_base` 的条目可以先收录为 `unverified`，但不能运行 MQ 验证。
5. 历史条目完成一次验证后，报告仍然是快照证据；后续是否持续观测由公开质量站的轮测策略决定。

