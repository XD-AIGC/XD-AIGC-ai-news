# XD-AIGC AI News Aggregator

全自动每日 AI 资讯聚合系统，多源采集 + LLM 摘要 + 多渠道推送。

## 关注领域

- **开源模型** — Stable Diffusion, Flux, HunyuanVideo, CogView 等
- **ComfyUI** — 新节点、工作流、插件更新
- **商用产品** — Lovart, Gemini, OpenAI, Claude, Midjourney
- **Agent & Skills** — AI Agent 框架、MCP 生态、自动化案例
- **训练与部署** — Fine-tune, LoRA, 推理优化, 量化

## 数据源

| 来源 | 方式 |
|------|------|
| YouTube | YouTube Data API v3 |
| Bilibili | RSSHub |
| Twitter/X | RSSHub |
| GitHub Trending | HTML 抓取 |
| AI 博客 (OpenAI/Google/Anthropic...) | RSS |
| 微信公众号 | 手动 URL / 付费服务 |

## 输出

- **Notion 数据库** — 结构化浏览、搜索、过滤
- **Web 日报** — 静态 HTML，可部署到任意 web server
- **微信推送** — 每日摘要推送到微信 (Server酱)
- **Markdown 存档** — 本地日报文件

## Quick Start

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置
cp docs/CONFIG_EXAMPLE.yaml config.yaml   # 编辑配置
cp .env.example .env                       # 填入 API keys

# 3. 运行
python main.py                             # 采集今日资讯
python main.py --days 3                    # 采集最近 3 天
```

## 部署 (systemd)

```bash
# 部署 RSSHub
cd deploy && docker-compose -f docker-compose.rsshub.yml up -d

# 部署定时任务
sudo ln -sf $(pwd)/deploy/ai-news.service /etc/systemd/system/
sudo ln -sf $(pwd)/deploy/ai-news.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ai-news.timer
```

## 详细规划

见 [docs/PLAN.md](docs/PLAN.md)
