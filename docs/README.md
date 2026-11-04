# docs 索引

本目录存放**公开**的设计与事故文档（运维细节、服务器信息、密钥清单在本地私有目录 `docs-private/`，不入库）。

| 文档 | 内容 |
|------|------|
| [verification-design.md](verification-design.md) | MQ 官方验证架构、威胁模型、Hub API、关键安全属性 |
| [2026-11-04-comment-self-trigger-loop.md](2026-11-04-comment-self-trigger-loop.md) | 事故复盘：providers-check 评论自触发死循环（`/mq-done` 全文字匹配 + PAT 评论回灌），含修复与可复用自查清单 |

## 命名约定

新增文档按 `YYYY-MM-DD-<english-kebab-title>.md` 命名（文件名用英文 kebab-case，正文用中文），并在本索引登记。
