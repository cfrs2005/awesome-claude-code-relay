# 链路止血、契约收口与发布工程化

日期：2026-11-05
范围：`.github/workflows/`、`scripts/`、`mq/contracts.py`、`tests/`、`mq/hub/app.py`

## 一句话

把「能跑」变成「跑得住」：修掉合并后状态静默丢失，补上 91 个自动化测试，
契约从 6 处硬编码收敛到一处，发布从手工 scp 变成打 tag 即部署。

## 三个当时正在发生的问题

### 一、合并后 verification 不回写（静默）

`sync-readme.yml` 里 `PR_NUMBER: ${{ inputs.pr }}` 在 push 触发时是空串；
脚本从提交信息里解析出了 PR 号，却只导出成 `PR_URL`，没有写回 `PR_NUMBER`。
于是内嵌的 Python 执行 `gh pr view ""` → 拿不到文件列表 → `sys.exit(0)`。

结果：**PR 合并成功、目录状态没变、job 还是绿的。** 上一次 `fd1aa8c`
（LINUX DO Hub 回写）是手动 `workflow_dispatch` 补跑出来的，不是自动跑出来的。

### 二、门禁失败被吞

- `providers-check.yml` 的 `gh pr merge` 失败只打 `::warning`，job 仍绿 →
  「所有检查都过了但没合并」在 Actions 里看不出来。
- `check_providers.py` 把 `providers/schema.json` 的变更记为 warning →
  放宽 schema 可以搭条目 PR 的车一起被自动合并。

### 三、同一份枚举写了 6 遍

结论中文名、可合并集合、家族词表、目录状态枚举分别硬编码在
`mq.py` / `check_mq_report.py` / `render_report.py` / `build_readme.py` /
`update_verification.py` / `hub/app.py` / `schema.json`。漂移已经发生：
README badge 停在 v0.1.0、门禁评论缺 `family_mismatch` 与 `mode_too_small` 两个分支、
两处 tone 映射对同一个 verdict 给出相反颜色（`identity_suspect` 一边 warn 一边 err）。

## 改了什么

### 1. 回写抽成可测脚本

新增 `scripts/writeback.py`，退出码表达三态：

| 退出码 | 含义 | 工作流行为 |
|---:|---|---|
| 0 | 已回写 | 继续重建 README |
| 2 | 确认无需回写（纯 infra PR、无 PR 直推） | 跳过，绿 |
| 3 | 应当回写但做不到（拿不到 PR 号、无报告、API 失败） | **判红 + 在 PR 上留提示** |

PR 号解析、条目定位、报告挑选都是纯函数（`resolve_pr_number` /
`provider_files` / `pick_latest_report`），各有单测。报告挑选改成
「域名精确匹配优先，其次最新」——与门禁的排序规则一致。

### 2. 失败不再被吞

- merge 失败重试 2 次，仍失败 `exit 1`；已合并的 PR 再触发时直接跳过。
- 结果评论补 `family_mismatch` / `mode_too_small` / `engine_too_old` 三个分支；
  `not_applicable` 的文案从「正在自动合并」改成「转人工」（原来文案与 if 条件不符）。
- `providers/schema.json` 变更改判**失败**，schema PR 必须单独提、单独审。

### 3. 契约单一事实源

新增 `mq/contracts.py`（纯标准库），承载：

```
VERDICT_LABEL / VERDICT_PILL / VERDICT_TONE / MERGEABLE / RETRY /
FULL_ENOUGH_MODES / VERIFICATION_STATUSES / STATUS_ORDER / STATUS_LABEL /
FAMILY_ALIAS / FAMILY_ORDER / FAMILY_ZH / ENTRY_FAMILY_LABEL /
MIN_ENGINE_VERSION / ENGINE_TAG / ENGINE_URL / version_lt()
```

`mq.py` **故意不 import** 它——引擎要能作为一个文件被 `curl` 下来直接跑，
所以保留内嵌副本，由 `tests/test_contracts.py` 强制两边逐键相等（含
`providers/schema.json` 的 enum）。改一处漏一处，测试立刻红。

### 4. 引擎分发版本锚定

6 处硬编码的 `raw.githubusercontent.com/.../main/mq/mq.py` 收敛为
`contracts.ENGINE_URL`，指向 **tag** 而不是 `main`。同时门禁新增
`engine_too_old` 状态：低于 `MIN_ENGINE_VERSION` 的报告不再放行——
旧引擎没有家族一致性与档位检查，它的 `basic_passed` 不能当证据。

### 5. 测试网（91 个用例）

| 文件 | 覆盖 |
|---|---|
| `test_contracts.py` | 7 份表的同源性、schema enum 对齐、版本比较、分发 URL 不指向 main |
| `test_engine_e2e.py` | 真起 mock 端点跑真引擎：通过 / 家族翻转 / 401 / 502 / 畸形 SSE / `/v1` 归一 / key 不泄露 / 目录翻转 |
| `test_check_report.py` | 门禁 11 个状态各一条，对着真实 git 仓库跑 |
| `test_check_providers.py` | 白名单、AFF、schema 变更、非 https |
| `test_writeback.py` | 三个退出码 + 旧 verdict 映射 |
| `test_render.py` | 金标准快照、XSS 转义、零外部请求、零 JS |
| `test_workflows.py` | YAML 解析、每个 `run` 块 `bash -n`、以及四条历史事故的回归护栏 |

顺带修掉的东西：`mq.py --self-test` 里那条恒真断言（拿本地硬编码列表做子集检查）、
`Report.get` 同类重复定义、`check_providers.py` 的死表达式、两处未使用的 import。

**这条测试网立刻抓到两个真 bug：**

1. `evidence_insufficient` 有中文文案却没有排序权重 → README 里会被排到最后。
2. `$VAR` 紧跟中文导致 bash 把中文当成变量名的一部分：
   `log "部署 $VERSION 成功（引擎 $live_engine）"` 报 `unbound variable`，
   部署脚本直接退出；`providers-check.yml` 的失败文案里也有同样写法，
   命中那个分支就会炸。已全部改为 `${VAR}` 并加了守卫测试。

### 6. 发布工程化

- `.github/workflows/ci.yml`：pytest（3.9 / 3.11 矩阵）+ ruff + 字节编译 +
  README 漂移检查（手改目录表会被判红）。
- `.github/workflows/deploy.yml`：打 `v*` tag 即部署。打包
  `app.py + contracts.py + render_report.py + engine/mq.py + fonts/` → scp →
  远端 `scripts/deploy.sh`：备份 → 解包 → 重启 → 校验 healthz 的 version
  等于刚部署的版本 → 失败自动回滚。公网 healthz 再确认一次。
- `healthz` 新增 `version` 与 `engine_version`，让「部署的到底是哪一版」可验证。
- `scripts/deploy.sh` 在本地用假 `sudo` / `systemctl` / `curl` 演练过四条路径：
  正常部署成功、healthz 报旧版本回滚、restart 被拒回滚、坏包（绝对路径）在动文件前被拒。
- `requirements-dev.txt` + `pyproject.toml`（ruff / pytest 配置）。

**未配置部署密钥时的行为**：`deploy.yml` 明确打 `::warning::` 并跳过，
不假装成功。配置 `DEPLOY_HOST` / `DEPLOY_USER` / `DEPLOY_SSH_KEY` 后自动生效。

### 6.1 部署权限模型

最初写成 `ssh ... "sudo bash /tmp/deploy.sh ..."` —— 等于把 root 交给 CI，
「最小权限」是句空话；脚本又先落在全局可写的 `/tmp`，从上传到执行之间有替换窗口。

现在：**部署账号是普通用户，脚本全程非 root 执行，唯一的提权是一条命令**。

| 主体 | 能做什么 | 不能做什么 |
|---|---|---|
| `deploy`（CI 用） | 写代码文件、`engine/`、`fonts/`、`.prev/`；`sudo systemctl restart mq-hub.service` | 读 `env`（凭证，root:600）；改 `data/`（绑定与报告）；执行其它 sudo |

配套的三条硬约束：

1. **不做 `chown -R /opt/mq-hub`**。整目录交给部署账号，`env`（含 `HUB_TOKEN`、
   `MQ_BOT_TOKEN`）和 `data/`（`prs.json` 决定门禁的 `verified`）会一起交出去 ——
   等于用「隔离凭据」换「凭据与验证记录可被篡改」。
2. **备份原子切换**。旧写法「先 rm 再 cp」在拷贝失败时会把上一版备份物理删除，
   回滚基准被自己毁掉；现在写 `.prev.tmp/`，成功后 `mv`。
3. **解包、写 VERSION、重启都纳入回滚**。原来只有健康检查失败才回滚，
   `tar` 失败或 `systemctl` 被拒会留下「文件半新半旧、服务跑着旧代码」，
   直到下一次重启才炸。

**这套模型挡什么、不挡什么**（必须写清）：

- 挡：CI 凭据泄露后的横向移动、部署脚本 bug 打偏毁系统、误操作。
- 不挡：**部署账号仍可间接拿到 root** —— 它能改 `app.py`，而服务以 root 运行，
  `restart` 正是被授权的那条命令。真正的关闸是 systemd `User=`，
  与「data 迁 `/var/lib/mq-hub`」「env 迁 `/etc`」是同一件事，列为后续专项。
- 另：`deploy` 仍可删除 `data/`（父目录写权限即可），这是 DoS 面，不是篡改面。

## 已知边界

- 报告机器块仍可被手改（设计如此，见 `2026-11-04-mq-report-gate.md`）。
- `engine_too_old` 上线后，旧引擎产出的报告在过渡期会被拒——这是预期行为，
  指引评论里已换成 tag 化命令。
- Hub 布局仍是扁平目录（`/opt/mq-hub/app.py`），没有做 release 目录与原子切换；
  当前靠「备份 + 失败回滚」保证可恢复。要做真正的蓝绿再改 systemd 单元。
- 复制按钮已做（用户拍板允许少量原生 JS）：全站唯一脚本，约 25 行，无框架无 CDN，
  只调用 `navigator.clipboard`，不发任何网络请求，非 https 退化为全选。
- 暗色主题未做（用户选择维持暖纸单主题）。
