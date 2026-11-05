# docs 索引

本目录存放面向贡献者和用户的公开设计、流程和事故文档。内部部署位置、凭证信息和运维步骤不写入公开文档。

| 文档 | 内容 |
|------|------|
| [verification-design.md](verification-design.md) | RelayQuality 公共验证流程、MQ 探针范围和结果边界 |
| [2026-11-04-mq-detectors-vs-veridrop.md](2026-11-04-mq-detectors-vs-veridrop.md) | 检测项对照 canarybyte/veridrop 的取舍：照搬什么、升级什么、以及它未做的签名回验 |
| [2026-11-04-mq-report-gate.md](2026-11-04-mq-report-gate.md) | 收录验证改为「提交者本地跑、报告贴进 PR」的 NQ 式流程（含机器可读块与核验规则） |
| [2026-11-04-mq-verdict-layering-and-catalog-diff.md](2026-11-04-mq-verdict-layering-and-catalog-diff.md) | MQ v0.2.0：结论分层、模型目录升为第一组结论、跨批次目录对比（含实测案例） |
| [2026-11-04-comment-self-trigger-loop.md](2026-11-04-comment-self-trigger-loop.md) | 评论触发工作流自循环的根因、修复原则和安全自查 |
| [2026-11-04-release-cutover-and-legacy-migration.md](2026-11-04-release-cutover-and-legacy-migration.md) | 发布切换点、历史条目一次性迁移 PR/MR、每个 PR 的专属验证地址与新规则 |
| [2026-11-04-legacy-pr-inventory.md](2026-11-04-legacy-pr-inventory.md) | 发布切换前历史 PR 清单、状态和重新提交规则 |
| [2026-11-05-pipeline-hardening-and-release.md](2026-11-05-pipeline-hardening-and-release.md) | 链路止血（回写静默失败）、契约单一事实源、测试网、tag 即部署 |

## 命名约定

新增文档按 `YYYY-MM-DD-<english-kebab-title>.md` 命名，正文使用中文，并在本索引登记。
