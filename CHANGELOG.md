# Changelog

版本号与 `mq/mq.py` 的 `MQ_VERSION` 保持一致，tag 形如 `v0.2.0`。
打 tag 会触发 `Deploy Hub`：打包 → 上传 → 重启 → 健康检查（版本不符自动回滚）。

## [Unreleased]

### 站点
- 首页补回「目录」区：服务商条目与验证报告在同一页，不再只有报告索引
- 404 / 无报告 / OAuth 失败页改为统一暖纸风错误页（原来返回裸 JSON，OAuth 页还有未转义异常）
- 报告页与首页共用 header/footer/nav，导航不再有死链接
- 补齐设计 token：`--clay-soft` / `--warn` / `--line-2`；七级结论各给独立配色语义
- 移动端增加 640px 断点

## [0.2.0] - 2026-11-05

### 修复
- **合并后 verification 不回写**：`sync-readme.yml` 的 PR 号没有传进子进程，
  `gh pr view ""` 静默失败导致状态丢失且 job 仍绿。回写逻辑抽成
  `scripts/writeback.py`，用退出码 0/2/3 表达「已回写 / 无需回写 / 做不到」，
  做不到时判红并在 PR 留言。
- **合并失败被吞**：`gh pr merge` 失败改为重试 2 次后判红，已合并的 PR 直接跳过。
- **schema 变更可被顺手合并**：`providers/schema.json` 变更改判失败，必须单独提 PR。
- **旧引擎报告可绕过新检查**：门禁新增 `engine_too_old`，低于 `MIN_ENGINE_VERSION` 不放行。
- `evidence_insufficient` 缺排序权重，README 里会被排到最后。
- `$VAR` 紧跟中文导致 bash 报 `unbound variable`（部署脚本与 providers-check 失败文案各一处）。
- README badge 长期漂移（服务商数 30→31、引擎 v0.1.0→v0.2.0），改由
  `build_readme.py` 自动同步。

### 变更
- 新增 `mq/contracts.py`：结论枚举、中文文案、配色语义、可合并集合、家族词表、
  目录状态全部收敛到一处；引擎保留内嵌副本以维持单文件分发，由测试强制一致。
- 引擎分发从 `main` 改为 tag（`ENGINE_URL`），命令不再随主干漂移。
- Hub `healthz` 返回 `version` 与 `engine_version`。
- Hub 死代码清理：bind/key/run 四组 410 接口的不可达实现。
- `mq.py --self-test` 去掉一条恒真断言，补家族判定与 family_reach 分支。

### 新增
- 91 个 pytest 用例（契约 / 引擎端到端 / 门禁状态机 / 条目校验 / 回写 / 渲染快照 / 工作流）。
- `.github/workflows/ci.yml`：pytest × Python 3.9、3.11 + ruff + 字节编译 + README 漂移检查。
- `.github/workflows/deploy.yml` + `scripts/deploy.sh`：打 tag 即部署，失败自动回滚。
- `requirements-dev.txt`、`pyproject.toml`。
