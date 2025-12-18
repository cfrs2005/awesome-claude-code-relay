# awesome-claude-code-relay

[![实时监控](https://img.shields.io/badge/监控状态-在线-brightgreen)](https://www.80aj.com/llm-monitor/)
[![中转站数量](https://img.shields.io/badge/中转站-5个-blue)](https://www.80aj.com/llm-monitor/)
[![最后更新](https://img.shields.io/badge/更新时间-2025.12-orange)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

> 🚀 Claude Code / Claude API 中转站导航 | 实时可用性监控 | 省钱省心

**在线监控面板**：👉 [https://www.80aj.com/llm-monitor/](https://www.80aj.com/llm-monitor/)

---

## 📊 中转站推荐榜

| 推荐 | 服务商 | 类型 | 注册/官网 | API Base URL |
|:---:|--------|:----:|:---------:|--------------|
| ⭐⭐⭐⭐⭐ | **智谱 BigModel** | 商业 | [注册](https://www.bigmodel.cn/claude-code?ic=H0RNPV3LNZ) | `https://open.bigmodel.cn/api/anthropic` |
| ⭐⭐⭐⭐⭐ | **Duckcoding** | 商业 | [注册](https://duckcoding.com/register?aff=zVon) | `https://jp.duckcoding.com` |
| ⭐⭐⭐⭐ | **Cubence** | 商业 | [注册](https://cubence.com/signup?code=SCJ7SAEL) | `https://cubence.com` |
| ⭐⭐⭐⭐ | **FoxCode** | 商业 | [注册](https://foxcode.rjj.cc/auth/register?aff=1YMQW) | `https://foxcode.rjj.cc` |
| ⭐⭐⭐⭐ | **CodeCli** | 商业 | [注册](https://code-cli.cn/user/register?invite=G28SUXSA) | `https://www.code-cli.cn/` |
| ⭐⭐⭐ | **EasyChat** | 商业 | [注册](http://easychat.site/#/user/login?ref=516e9c1c-0369-4bd3-9ccc-1a53e225b1d0) | `https://wwww.easychat.site` |
| ⭐⭐⭐ | **Anyrouter** | 公益 | [注册](https://anyrouter.top/register?aff=86mM) | `https://anyrouter.top` |
| ⭐⭐⭐ | **Ikuncode** | 商业 | [官网](https://api.ikuncode.cc) | `https://www.ikuncode.cc` |
| ⭐⭐⭐ | **GalaxyCode** | 商业 | [官网](https://nf.video) | `https://nf.video` |
| ⭐⭐⭐ | **SSSAiCode** | 商业 | [官网](https://www.sssaicode.com) | `https://www.sssaicode.com` |
| ⭐⭐⭐ | **MikuCode** | 商业 | [官网](https://mikucode.xyz) | `https://mikucode.xyz` |
| ⭐⭐⭐ | **JikeAI** | 商业 | [官网](https://magic666.top) | `https://magic666.top` |
| ⭐⭐ | **AICodeMirror** | 商业 | [官网](https://www.aicodemirror.com) | `https://www.aicodemirror.com` |
| ⭐⭐ | **Privnode** | 商业 | [官网](https://privnode.com) | `https://privnode.com` |
| ⭐⭐ | **Uucode** | 商业 | [官网](https://www.uucode.org) | `https://www.uucode.org` |
| ⭐⭐ | **AIMZ** | 商业 | [官网](https://mzlone.top) | `https://mzlone.top` |
| ⭐⭐ | **88code** | 商业 | [官网](https://www.88code.org) | `https://www.88code.org` |
| ⭐⭐ | **Xyai** | 商业 | [官网](https://new.xychatai.com/pastel/#/vibe-code) | `https://new.xychatai.com` |
| ⭐⭐ | **PackyCode** | 商业 | [官网](https://www.packyapi.com) | `https://www.packyapi.com` |
| ⭐⭐ | **Runanytime** | 商业 | [官网](https://runanytime.hxi.me) | `https://runanytime.hxi.me` |
| ⭐⭐ | **YesCode** | 商业 | [官网](https://co.yes.vg) | `https://co.yes.vg` |
| ⭐⭐ | **Elysiver** | 商业 | [官网](https://elysiver.h-e.top) | `https://elysiver.h-e.top` |

> 💡 推荐指数基于：可用性、延迟、稳定性、用户反馈综合评估

---

## 🔧 Claude Code 配置

### 环境变量

```bash
# 设置中转站地址
export ANTHROPIC_BASE_URL="https://jp.duckcoding.com"

# 设置 API Key（从中转站获取）
export ANTHROPIC_API_KEY="sk-your-api-key"

# 启动 Claude Code
claude
```

### 永久配置

```bash
# 写入 ~/.zshrc 或 ~/.bashrc
echo 'export ANTHROPIC_BASE_URL="https://jp.duckcoding.com"' >> ~/.zshrc
echo 'export ANTHROPIC_API_KEY="sk-your-api-key"' >> ~/.zshrc
source ~/.zshrc
```

### 支持的模型

| 模型 | Model ID | 特点 |
|------|----------|------|
| Claude Opus 4 | `claude-opus-4-20250514` | 最强推理能力 |
| Claude Sonnet 4 | `claude-sonnet-4-20250514` | 平衡性能与成本 |
| Claude Haiku 4.5 | `claude-haiku-4-5-20251001` | 快速响应低成本 |

### 常用命令

| 命令 | 说明 |
|------|------|
| `claude` | 启动交互式会话 |
| `claude "prompt"` | 单次提问 |
| `claude -p "prompt"` | 管道模式 |
| `claude --model sonnet` | 指定模型 |
| `claude --continue` | 继续上次会话 |
| `claude config` | 配置设置 |

---

## 🐍 Python SDK

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-your-api-key",
    base_url="https://jp.duckcoding.com"
)

message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Hello!"}]
)
print(message.content[0].text)
```

---

## 🧪 连通性测试

```bash
curl https://jp.duckcoding.com/v1/messages \
  -H "Authorization: Bearer sk-your-api-key" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5-20251001","max_tokens":10,"messages":[{"role":"user","content":"hi"}]}'
```

---

## 💰 价格对比

| 对比项 | 官方直连 | 中转站 |
|--------|---------|--------|
| Haiku 输入 | $0.25/M | ¥0.5-2/M |
| Haiku 输出 | $1.25/M | ¥2-5/M |
| Sonnet 输入 | $3/M | ¥5-15/M |
| Sonnet 输出 | $15/M | ¥20-50/M |
| 支付方式 | 外币卡 | 支付宝/微信 |
| 网络 | 需魔法 | 国内直连 |

---

## ❓ FAQ

<details>
<summary><b>Q: 中转站安全吗？</b></summary>

- 不传输敏感信息（密码、密钥）
- 生产环境优先选择智谱等官方合作方
- 定期更换 API Key
</details>

<details>
<summary><b>Q: Claude Code 报错 401/403？</b></summary>

```bash
echo $ANTHROPIC_BASE_URL  # 检查地址
echo $ANTHROPIC_API_KEY   # 检查密钥
# Base URL 不要带 /v1/messages 后缀
```
</details>

<details>
<summary><b>Q: 如何切换中转站？</b></summary>

```bash
export ANTHROPIC_BASE_URL="https://api.cubence.com"
```
</details>

---

## 📈 实时监控

👉 [https://www.80aj.com/llm-monitor/](https://www.80aj.com/llm-monitor/)

- ✅ 实时可用性状态
- ⏱️ API 响应延迟
- 📊 历史可用率趋势

---

## 🤝 贡献

欢迎 PR 补充更多中转站！

---

## ⚠️ 免责声明

本项目仅做信息汇总，不对任何中转站的服务质量、安全性、合规性负责。

---

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=your-username/awesome-claude-code-relay&type=Date)](https://star-history.com/#your-username/awesome-claude-code-relay&Date)

---

**关键词**：Claude Code, Claude API, API 中转站, Claude 代理, Anthropic API, Claude Sonnet, Claude Haiku, Claude Opus, AI 编程助手, 大模型 API, LLM API, Claude Code 配置, Claude Code 教程, Claude Code 中转, Claude API 国内, Claude API 代理, Claude API 便宜, Claude Code 省钱, awesome claude code
