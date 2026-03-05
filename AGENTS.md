# XD-AIGC AI News Aggregator

## Project Overview
全自动每日 AI 资讯聚合系统。多源采集 + LLM 摘要 + 多渠道输出。

## Focus Areas (关注领域)
- **开源模型**: Stable Diffusion, Flux, HunyuanVideo, CogView, Wan, 新发布的开源权重/架构
- **ComfyUI 技术**: 新节点、工作流、插件更新、版本变更
- **商用产品**: Lovart, Gemini, OpenAI (GPT/DALL-E/Sora), Claude/Anthropic, Midjourney
- **Agent & Skills**: AI Agent 框架、MCP 生态、应用案例、自动化工作流
- **训练与部署**: Fine-tune, LoRA, RLHF, 推理优化, 量化, 部署方案

## Data Sources
- YouTube (AI 频道, via YouTube Data API v3)
- Bilibili (AI UP主, via RSSHub)
- Twitter/X (AI 大佬/机构, via RSSHub)
- GitHub Trending (AI 相关项目, 直接抓取)
- RSS Feeds (OpenAI/Google/Anthropic/HuggingFace/Stability AI 博客)
- 微信公众号 (V1: 手动 URL 输入; V2: 付费服务)

## Output Destinations
- Notion Database (结构化存储 + 浏览)
- Static Web Dashboard (Jinja2 生成的 HTML 日报)
- WeChat Push (Server酱/PushPlus)
- Markdown Archive (本地存档)

## Project Structure
```
XD-AIGC-ai-news/
├── main.py                   # CLI 入口
├── config.yaml               # 数据源 + 输出配置
├── .env                      # API keys (git ignored)
├── collectors/               # 数据采集层
│   ├── base.py               # NewsItem dataclass + BaseCollector
│   ├── rss_collector.py      # 通用 RSS (feedparser)
│   ├── youtube_collector.py  # YouTube Data API v3
│   ├── github_collector.py   # GitHub Trending
│   └── manual_collector.py   # 手动 URL 采集
├── processor/                # 内容处理层
│   ├── summarizer.py         # LLM 摘要 (OpenAI/Claude)
│   ├── classifier.py         # 领域分类 + 重要度评分
│   └── dedup.py              # 去重 (URL + 标题相似度)
├── outputs/                  # 输出层
│   ├── notion_writer.py      # Notion SDK
│   ├── web_generator.py      # Jinja2 HTML
│   ├── markdown_writer.py    # Markdown 日报
│   └── push_notifier.py      # 微信推送
├── storage/                  # 持久化
│   ├── database.py           # SQLite
│   └── models.py             # DB schema
├── templates/                # Jinja2 模板
├── deploy/                   # 部署文件
│   ├── docker-compose.rsshub.yml
│   ├── ai-news.service
│   └── ai-news.timer
├── reports/                  # 输出目录 (git ignored)
└── data/                     # 运行时数据 (git ignored)
```

## Coding Style
- Python 3.10+, 4-space indent, snake_case, type hints
- Single file <= 500 lines, single function <= 50 lines
- Use `config.yaml` for all configuration, `.env` for secrets
- HTTP requests must use configured proxy (http://172.24.12.140:18888)

## Deployment
- Server: L20_1 (10.102.80.15), path: /AIGC/XD-AIGC-ai-news
- Scheduling: systemd timer (daily)
- RSSHub: Docker container on same server

## Key Dependencies
- feedparser: RSS 解析
- google-api-python-client: YouTube API
- openai: LLM 摘要
- notion-client: Notion 写入
- jinja2: HTML 模板
- beautifulsoup4 + httpx: 网页抓取
- pyyaml: 配置解析
- python-dotenv: 环境变量
