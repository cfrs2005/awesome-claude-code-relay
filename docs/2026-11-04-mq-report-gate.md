# 收录验证改为「贴报告」模式

日期：2026-11-04
范围：`.github/workflows/`、`scripts/check_mq_report.py`、`scripts/pr_guide.py`、`mq/mq.py`

## 一句话

把收录验证从「提交绑定码 → 上传临时 Key → 服务端代跑」改成
「提交者本地跑 MQ → 报告贴进 PR → Action 核验端点一致性 → 自动合并」。

## 为什么改

原流程有三处别扭：

1. **形态错了。** 它是个审核系统：平台持有密钥、代跑测试、判定「你过不过」。
   而这类工具该长的样子是 VPS 圈的 NodeQuality —— 用户自己跑、自己贴，平台只核验和呈现。
2. **风险错了。** 服务端代跑意味着用户的 Key 要经过我们的机器。哪怕只在内存里放 20 分钟，
   也是个不该存在的攻击面，且在 PR 上解释起来成本极高。
3. **门槛错了。** 绑定码 → 评论 → 回 Hub → 交 Key → 点运行，五步。提交者跑一次测试
   比写这个 PR 还费劲。

真正需要的核验其实只有一件事：**这份报告测的是不是你这个 PR 要收录的那个端点。**

## 新流程

```
提交者本地                  GitHub                      结果
──────────                  ──────                      ────
mq.py --base-url <api_base>
  → report.md
                         贴进 PR 评论
                         （首行含机器可读块）
                         评论 /mq-done
                                                      check_mq_report.py
                                                        ├ 报告存在？
                                                        ├ host == api_base host？
                                                        ├ 30 天内？
                                                        └ 结论合格？
                                                      → 自动 squash 合并
                                                      → 合并后回写 verification
```

## 机器可读块

引擎在报告第一行输出一段 GitHub 上不可见的 HTML 注释：

```
<!--MQ-REPORT:eyJ2IjoxLCJlbmdpbmUiOiIwLjIuMCIs...-->
```

内容是 base64 的 JSON，字段固定：

| 字段 | 用途 |
|---|---|
| `v` / `engine` | 格式版本与引擎版本 |
| `tested_at` | 时间戳，用于过期判定 |
| `base_url` / `host` | 端点一致性判定 |
| `declared_model` / `tested_model` / `model_substituted` | 声明模型是否被替换 |
| `catalog_families` / `catalog_count` | 模型目录家族构成 |
| `verdict` | 七级结论之一 |
| `checks` | 各检测项 PASS/WARN/FAIL/INFO |
| `report_id` | 内容哈希前 16 位，便于引用与去重 |

**它不是防伪凭证。** 报告仍是可读可改的 markdown，任何人都能手改字段。
这一点和 NQ 一样：NQ 的报告也是一段可以手改的文本，信任来自社区监督与「改了没收益」。

真要防伪需要共享密钥签名，而共享密钥放在开源 CLI 里等于公开，做了也没有意义。
所以设计上明确不追求这个，只追求**端点一致性**这道真正有价值的闸。

## 核验规则

| 检查项 | 通过条件 | 不通过时 |
|---|---|---|
| 报告存在 | PR 正文或评论里能找到可解析块 | 等待 + 给重测指引 |
| 端点一致 | 报告 host == 条目 `api_base` host；允许 `api.` 前缀差异 | 拒绝，列出报告里出现的所有 host |
| 报告时效 | `tested_at` 在 30 天内 | 等待 + 给重测指引 |
| 结论合格 | `verdict == basic_passed` | 拒绝或提示重测（见下） |

结论不合格分两种处置：

- `endpoint_unreachable` / `auth_rejected` / `evidence_insufficient`
  → 这次测试根本没做成，提示**重跑**，不当作端点的罪名。
- `model_not_found` / `protocol_incompatible` / `behavior_anomaly` / `identity_suspect`
  → 报告本身说明端点有问题，不合并。

同一 PR 贴了多份报告时，优先取域名精确匹配且 `tested_at` 最新的那一份。

## 大模型做什么、不做什么

GLM 分诊（`claudecode.yml`）在两种时机运行：PR 打开时、以及提交者评论 `/mq-done` 后。

它读报告正文，按四组解读：模型目录 → 端点可用性 → 协议兼容性 → 身份证据。
重点要求它讲清楚**「看到了什么」+「这意味着什么」**，而不是复述表格。

三条硬约束写进了 prompt：

- 一个声明提供 Claude 的端点，目录里 claude 系数量为 0，必须放在最前面讲。
- HTTP 状态码要分辨性质：5xx 是端点挂了，401 是 Key 问题，404 + 模型不存在是声明不实。
- 「模型自述」无证据力，绝不能因为模型自称 Claude 就说它是真的。

**AI 不参与放行判定。** 放行是 `check_mq_report.py` 的确定性结果，
AI 的评论末尾固定写一句「以上解读仅供参考，不改变确定性核验结果」。

## 历史环境的处置

- `scripts/register_hub.py`、`scripts/hub_gate.py` 已删除（不再有调用方）。
- `.github/workflows/register-verify.yml` 已删除，替换为 `mq-guide.yml`（只发指引，不联网）。
- `mq/hub/` 保留但**不在关键路径上**：它是一个可选地托管/浏览报告的服务，
  不参与合并门禁。仓库可完全在没有它的情况下工作。
- `sync-readme.yml` 的验证回写改为从 PR 的机器可读块读取，不再查询 Hub。

## 已知边界

- **不防篡改。** 见上文机器可读块一节。
- **不防「真跑了一次但事后换上游」。** 这只能靠报告里的「与上次目录对比」发现，
  而对比需要提交者带 `--previous-report`。想强制的话可以后续加一条：
  要求报告 `catalog_families` 与声明的模型家族一致。
- **30 天有效期是拍的。** 中转站上游变化比 VPS 快，这个数字应当按实际观测调。
- 端点一致性只比 host，不验 TLS 证书链、不验 IP。要更严可以加证书指纹。
