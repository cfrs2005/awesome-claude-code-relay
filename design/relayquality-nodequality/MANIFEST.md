# RelayQuality · NodeQuality Style · Stitch 设计记录

## 基本信息

| 项 | 值 |
|---|---|
| Stitch 项目名 | RelayQuality · MQ Hub · NodeQuality Style |
| Stitch 项目 ID | 37768472514992686 |
| 归属产品 / 仓库 | awesome-claude-code-relay |
| 复用还是新建 | 新建 |
| 新建理由 | 现有 Stitch 项目没有 Claude Relay / MQ / NodeQuality 质量站方向；仓库也没有现成 design/ 资产。 |
| 创建时间 | 2026-11-04 |
| 本次设计人 | Codex + Stitch |

## 屏清单

| # | 屏 ID | 标签 | 设备 | 用途 | 落盘文件 |
|---|---|---|---|---|---|
| 1 | b14ece6b3ccf423f875ff9126330ab96 | RelayQuality 公立中转质量索引仪表盘 | DESKTOP | 公开质量总览 | `01-overview.html` / `01-overview.png` |
| 2 | 03ae88135f54495cbcce0ff44215f24d | RelayQuality PR 独立验证工作台 | DESKTOP | 每个 PR 的直达验证地址 | `02-pr-verification.html` / `02-pr-verification.png` |
| 3 | cef3fbca19ec48f7a3f7bb74f20a8763 | RelayQuality 服务商质量评测与快照证据报告 | DESKTOP | 单端点指标与报告 | `03-provider-report.html` / `03-provider-report.png` |

## 生成记录

### 第 1 轮

- 工具：`generate_screen_from_text`
- deviceType：`DESKTOP`
- modelId：默认
- 设计体系：生成首屏时由 Stitch 产出 `Technical Benchmark Index`
- prompt 原文：

```text
RelayQuality public dashboard for a free, neutral Claude relay quality index. This is the first desktop screen, 1440px base. Light technical data product, no ads, no affiliate links, no rankings, no vendor promotions.
Layout: fixed 224px navy left rail with RelayQuality logo and nav items 质量总览, 服务商, 验证说明, 提交服务商. Main canvas: 64px top bar with search, last updated and GitHub link. Intro banner headline 免费、开放、无 AFF 的中转站质量测试站; subtitle 统一探针、公开证据、任何人可复现. Four KPI cards: 已收录, 已完成测试, 基础协议通过, 最近测试. Dense filter toolbar. Provider grid/table with 8 visible cards. Each card has name, type, endpoint host, precise status badge, last test timestamp, success rate, TTFT, and 查看报告. Side note 如何阅读结果 says passing does not prove safety or model authenticity.
Visual: deep navy rail, white cool canvas, cobalt primary, cyan measurement accents, green pass, amber warning, red anomaly. Flat surfaces, 1px borders, 8px radii, compact density, clear technical typography. No gradients, glow, glass, stars, prices, signup, fake charts, or best/fastest claims. Chinese UI copy, English layout description. Device DESKTOP.
```

- 结果：首屏已产出；Stitch 返回 2560×4390 设计稿，设计体系为 `Technical Benchmark Index`。

设计稿中的数量、延迟、历史时间和报告内容是视觉占位数据，不是线上验证结论。生产落码时只能读取 Hub / MQ 报告中的真实字段；示例域名已统一为 `mq.80aj.com` 和当前仓库的 86GameStore PR 场景。

## token 映射

| Stitch 值 | 用途 | 仓库 token | 结论 |
|---|---|---|---|
| `#2563EB` | 主操作 / 选中状态 | 当前 Hub `--acc` 需升级为产品 token | 待落码时映射 |
| `#0F172A` / 深藏青 | 结构导航 | 当前 Hub `--bg` / `--card` 需升级为产品 token | 待落码时映射 |
| `#ECFDF5` / `#059669` | 基础协议通过 | 当前 Hub `--ok` | 可复用语义 |
| `#FFFBEB` / `#D97706` | 身份存疑 / 警告 | 当前 Hub `--warn` | 可复用语义 |
| `#FEF2F2` / `#DC2626` | 行为异常 | 当前 Hub `--err` | 可复用语义 |
| JetBrains Mono | 指标、端点、时间 | 生产层尚无 token | 待补产品 token |

## 落码记录

| 项 | 内容 |
|---|---|
| 目标目录 | `mq/hub/app.py`（现有内嵌页面）或后续拆出的 Hub 前端目录 |
| 新增文件 | 当前仅保存设计稿层，不覆盖生产 UI |
| 修改文件 | 无 |
| 复用的既有组件 | 待落码时确认 |
| 视口校验 | Stitch 设计稿为 DESKTOP；生产落码前需按 1440px / 1024px 检查 |

## 未解决

- [x] 生成 PR 验证页
- [x] 生成服务商报告页
- [ ] 将 Stitch 设计 token 映射到生产 UI token
- [ ] 确认历史条目一次性迁移 PR 的展示方式
