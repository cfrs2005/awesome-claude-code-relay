# 发布切换与历史条目迁移

## 目的

本项目的公开产品是免费的 RelayQuality 质量测试站。项目不收广告费、不做 AFF、不接受付费置顶，也不出售“验证通过”。GitHub PR、MQ Hub 和 MQ 引擎只是完成公开测量的协作工具。

## 发布切换点

切换点以前的服务商记录和历史 PR 属于 **legacy（历史数据）**。它们可以保留在目录中，但不能因为过去曾经出现在 README、旧 PR 或旧榜单中，就被解释为已经通过 MQ 验证。

切换点以后，新收录必须满足下面的流程：

```text
PR 修改一个 providers/<id>.json
  → Providers Check 做确定性检查
  → Register Verify 注册到 MQ Hub
  → Action 在 PR 评论发布专属验证地址
  → 作者在 /pr/<PR号> 完成身份绑定和临时 Key 测试
  → 报告回贴 PR
  → 作者评论 /mq-done
  → Providers Check 通过后才允许自动合并
```

## 历史条目的一次性迁移

历史条目要进入新规则时，使用一次性的迁移 PR/MR 重新提交。迁移 PR 只负责把历史资料整理成 `providers/*.json`，并明确标记为 `unverified`；它不把旧的星级、推荐词、注册链接或服务商自称内容变成事实。

历史条目的验证需要单独的 PR 记录，因为 MQ Hub 以 PR 为身份和端点绑定单位。每个需要验证的 PR 都有一个固定地址：

```text
https://mq.80aj.com/pr/<PR号>
```

这个地址会由 `register-verify` 自动写入 PR 评论，也会出现在 Hub 的 API、PR 面板、验证报告回贴和每个 PR 卡片中。不要要求作者在全局列表里寻找自己的 PR。

## 历史 PR 的处理边界

- 旧的 README-only PR 不会自动变成验证通过记录。
- 旧 PR 的推广参数、星级和营销描述不能带入新的 provider JSON。
- 旧 PR 如果要继续收录，维护者应按新的 `providers/<id>.json` 规则重新提交。
- 历史条目没有可用 `api_base` 时，只能保留为 `unverified`，不能进入 MQ 运行阶段。
- 迁移阶段的结果要区分“历史收录”和“新规则验证”，不能用一个状态混在一起。
- 发布切换后新 PR 不接受绕过专属验证地址的手工流程；特殊情况只能由维护者使用 `mq-manual` 转人工审查。

## 证据边界

`basic_passed` 只表示指定时间、指定端点和指定模型下的基础协议探针通过。它不证明底层模型一定是真实 Claude，不证明服务商不留存请求，也不构成安全或商业推荐。

