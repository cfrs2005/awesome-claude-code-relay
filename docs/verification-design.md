# RelayQuality 验证架构说明

RelayQuality 是一个免费的、开放的 Claude Code / Anthropic 兼容中转站质量测试服务。项目不收广告费、不做 AFF、不接受付费置顶，也不出售“验证通过”。

GitHub PR 负责提交公开的服务商资料，MQ Hub 负责验证流程，MQ 引擎负责执行统一探针。三者共同组成公开质量站的测量链路。

## 公共流程

```text
服务商作者提交 providers/<id>.json
  → GitHub Actions 检查字段、URL 和推广参数
  → PR 注册到 MQ Hub
  → Hub 为 PR 提供专属验证地址 /pr/<PR号>
  → 作者绑定 PR 身份并提交短期测试 Key
  → MQ 引擎执行统一探针
  → 报告回贴 PR，并提供公开报告地址
  → 作者评论 /mq-done
  → 检查通过后才允许合并
```

每个 PR 的验证地址都遵循：

```text
https://mq.80aj.com/pr/<PR号>
```

## 测量内容

MQ 引擎检查 Anthropic Messages 兼容接口的公开行为，包括：

- 基础 Messages 响应结构
- SSE 流式事件顺序
- system 指令透传
- tool_use 与 tool_result 闭环
- 重复请求的 usage 一致性
- extended thinking 字段存在性
- 身份旁证和注入泄漏启发式信号
- 多次请求的成功率、延迟和流速

这些检查只描述指定时间、指定端点和指定模型的测试结果。

## Key 处理边界

测试 Key 只用于一次验证任务。服务端不把 Key 写入公开 PR、报告或仓库文件。作者应使用低额度、短有效期的专用测试 Key，并在验证结束后主动吊销。

RelayQuality 不能证明服务商不会留存或转卖请求，也不能通过短时黑盒测试证明底层模型一定是真实 Claude。`basic_passed` 只表示基础协议探针在本次采样中通过。

## 端点一致性

验证任务使用 PR 中声明的 `api_base`。如果实际测试端点与 PR 声明不一致，结果不能作为该 PR 的验证结果。这样可以避免“测试一个端点、收录另一个端点”。

## 公开 API

```text
GET  /api/prs                 公开的待验证 PR 列表，不含 Key
GET  /pr/<PR号>               某个 PR 的专属验证工作台
GET  /reports/<PR号>/<报告>   脱敏后的验证报告
GET  /healthz                 服务健康状态
```

内部认证、部署位置、凭证名称和运维步骤不写入公开文档。需要维护服务时，使用受控的内部运维记录。

## 结果边界

验证结果是快照证据，不是安全背书、合规认证、模型真实性证明或商业推荐。用户应在自己的环境中使用 `mq/mq.py` 重跑，并避免把敏感代码和密钥交给任何第三方中转站。
