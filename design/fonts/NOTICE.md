# 字体文件

报告页 `scripts/render_report.py` 会在渲染时把这些 woff2 内联成 base64，
使产物完全自包含（零外部请求）。文件缺失时自动回退到 Georgia / 系统无衬线，不会报错。

| 文件 | 字体 | 字重 | 许可 |
|---|---|---|---|
| `instrument-serif-400-*.woff2` | Instrument Serif | 400 | SIL Open Font License 1.1 |
| `inter-400-*.woff2` | Inter（可变字体，覆盖 100–900） | 100 900 | SIL Open Font License 1.1 |
| `jetbrains-mono-400-*.woff2` | JetBrains Mono | 400 | SIL Open Font License 1.1 |

均为 Google Fonts 的 latin 子集。只含拉丁字符，中文走系统字体（PingFang SC / 宋体）。
