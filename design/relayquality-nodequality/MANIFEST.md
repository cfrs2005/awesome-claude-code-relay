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


### 第 2 轮 · 报告页改版（深色仪表盘）

- 工具：`generate_screen_from_text`（Stitch MCP，项目 37768472514992686）
- 屏 ID：`f2c5b4e7c2ab4a65ad1fe9b2be109a33`
- 尺寸：2560 × 3914（DESKTOP，1440 基准）
- 生成时间：2026-11-04
- 落盘：`04-report-dark.html` / `04-report-dark.png`

**背景**：第 1 轮的报告页是三张表格平铺，信息层级扁，用户反馈"看着很蠢"。
第 2 轮重新定视觉方向：深色技术仪表盘，把结论做成视觉锚点。

**关键约束（写进了 prompt，也被采纳）**：
- **不做总分。** MQ 没有加权评分口径，画一个 85/100 的是假精度。
  大视觉锚点改为「结论 + 检查项分布条 + 通过/失败计数」。
- 单一强调色（琥珀 `#F59E0B`），绿/红只用于状态点。
- 分组顺序固定：模型目录 → 端点可用性 → 协议兼容性 → 身份证据 → 稳定性与性能。

> 注：`list_screens` 对这个项目返回空对象 `{}`，但用 `get_screen` 按完整资源名
> （`projects/{pid}/screens/{sid}`）逐个查，第 1 轮三个屏全部存在且可下载。
> **结论：`list_screens` 不可靠，判断屏是否存在只能靠 `get_screen`。**
>
> 第 1 轮的 `03-provider-report` 实际是一份完整产品页（左侧栏 + 通过率 KPI + 协议矩阵表 +
> 右侧元数据/本地复现/合规声明），并非平铺表格。之前把它当成"表格稿"是误读。

## token 映射（第 2 轮）

| 设计稿 | 用途 | 生产实现 |
|---|---|---|
| `#0F1115` | 页面背景 | `--bg` |
| `#171A20` | 卡片表面 | `--surface` |
| `rgba(255,255,255,.08)` | 边框 | `--line` |
| `#F1F3F5` / `#9AA2B1` / `#5F6775` | 三级文字 | `--text` / `--text-2` / `--text-3` |
| `#F59E0B` | 唯一强调色（注意、警示） | `--amber` |
| `#10B981` | 通过 | `--green` |
| `#EF4444` | 失败 | `--red` |
| `#6B7280` | 信息 | `--grey` |
| JetBrains Mono | host / 模型 id / 时间 / 指标 / 序号 | `--mono` |

**落码位置**：`scripts/render_report.py`（`build()` 函数）。设计稿用了 Tailwind CDN + Google Fonts +
Material Symbols，落码时全部去掉，改成一份自包含 `<style>`，产物约 13KB、零外部请求。

**未采纳的设计元素**：综合得分环、权重条（`权重 15`）、单价 `$0.02`、竞品对比。
理由：MQ 没有对应口径，编一个就成了假数据。


### 第 3 轮 · Claude 品牌配色（定稿方向）

- 工具：`generate_screen_from_text`（Stitch MCP，项目 37768472514992686）
- 屏 ID：`713146053f6a445c85719c5d83d5e827`
- 标题：RelayQuality 质量评测报告 - Claude Editorial
- 尺寸：2560 × 4672
- 落盘：`05-report-claude.html` / `05-report-claude.png`

**背景**：上一版是深色仪表盘，用户判定「用户平台别这样设计」，要求 Claude 品牌配色。
产品定位是公开的质量报告页，读者是普通开发者，不是运维看板。

**视觉语言**：暖纸底 + 陶土强调色 + 衬线标题，走 Anthropic / Claude 的编辑感。
明令禁止：深色、霓虹、蓝紫、纯黑纯白、左上角导航栏、渐变色徽章。

**Stitch 稿的问题**：它自行编造了 14 个检测项（DNS 解析、TLS 证书、OPTIONS 探测……），
分组名也自己起了（「网络连通与反向代理指纹」）。这些都不是 MQ 的真实探针。
落码时**只取视觉与布局，内容全部换回真实字段**——13 个检查项、5 个分组、七级结论。

## token 映射（第 3 轮 · 定稿）

| 设计稿 | 用途 | 生产实现 |
|---|---|---|
| `#F0EEE6` | 页面底色（暖纸） | `--paper` |
| `#FAF9F5` | 卡片 / 复现块 | `--surface` |
| `#E3DFD5` / `#EDEAE1` | 分隔线（两级） | `--line` / `--line-2` |
| `#141413` / `#6B6862` / `#8A8578` | 三级文字 | `--ink` / `--ink-2` / `--ink-3` |
| `#D97757` | 唯一强调色（Claude clay） | `--clay` |
| `#F4E4DD` | 强调色浅底（pill 背景） | `--clay-soft` |
| `#5B7F5B` 苔绿 | 通过 | `--ok` |
| `#B58238` 赭石 | 注意 | `--warn` |
| `#B3462F` 陶红 | 失败 | `--err` |
| `#8A8578` | 信息 | `--info` |
| Georgia / 宋体 | 标题、host、分组名、通过率数字 | `--serif` |
| 系统无衬线 | 正文、标签 | `--sans` |
| 等宽 | 模型 id、时间、指标、序号 | `--mono` |

**改版要点**：
- 结论区不再是卡片，改成开放区块 + 底部细线；右侧放「N / M 项通过」+ 细分段条，仍然没有总分。
- 四元信息用竖线分隔，不用方框。
- 分组用衬线小标题 + 右侧计数，行内用 6px 状态点，不用表格边框。
- 补了「本地复现」块（吸收自第 1 轮 `03-provider-report`）。

**落码位置**：`scripts/render_report.py`（`CSS` + `build()`）。零外部依赖，产物 12.7KB。


## 第 3 轮修订 · 按规范校色

用户给出明确色彩系统后，第 3 轮初版的配色全部纠正：

| 项 | 初版（错） | 规范（已改） |
|---|---|---|
| 主背景 | `#F0EEE6` | **`#F4F1EA`** |
| 容器色 | `#FAF9F5`（比底色浅） | **`#EAE5DC`（比底色深）** |
| 主文本 | `#141413` | **`#1C1B1A`** |
| 次文本 | `#6B6862` | **`#5C5A56`** |
| 边框 | `#E3DFD5` | **`#D6D0C4`** |
| 辅助强调 | 无 | **`#4A6B5D` 墨绿** |

**最关键的纠正**：容器色必须比页面底色**深**。靠背景色差分块，而不是白色卡片 + 投影 ——
这是这套风格和「AI 生成的 SaaS 皮肤」的分水岭。

**语义色收敛到调色板内**：通过=墨绿 `#4A6B5D`、注意=珊瑚 `#D97757`、失败=陶红 `#A6472F`（clay 深阶）、
信息=`#857F74`。不再引入无关的蓝/绿/红。

**字体自托管**：Instrument Serif / Inter（可变）/ JetBrains Mono 的 latin 子集共 82KB，
放在 `design/fonts/`，渲染时 base64 内联进 HTML。产物 124KB，零外部请求。
本机一个都没装，不内联就全回退到 Georgia。

**视觉禁忌清单逐条自检**：无渐变、圆角 ≤8px、无彩色竖条、无 emoji、无 box-shadow、
无外链字体脚本、无纯白卡片 —— 7 项全部通过。


## 未解决

- [x] 生成 PR 验证页
- [x] 生成服务商报告页
- [x] 将 Stitch 设计 token 映射到生产 UI token（第 2 轮，见上表）
- [ ] 确认历史条目一次性迁移 PR 的展示方式
