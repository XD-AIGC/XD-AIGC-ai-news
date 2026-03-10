# AI 每日资讯聚合系统 - 实施规划

## 整体架构

```
数据源 (YouTube/Bilibili/Twitter/GitHub/RSS)
    │
    ▼
RSSHub (Docker, 统一 RSS 化) ──┐
YouTube API ─────────────────┤
GitHub Trending 抓取 ──────────┤
    │                         │
    ▼                         ▼
    Python Collectors (采集层)
            │
            ▼
    SQLite 去重 + 存储
            │
            ▼
    LLM 摘要 + 分类 + 评分 (gpt-4o-mini)
            │
            ▼
    ┌───────┼───────┬──────────┐
    ▼       ▼       ▼          ▼
  Notion   Web    微信推送   Markdown
  数据库   日报   (Server酱)   存档
```

## 关注领域

| 领域 | 关键词 |
|------|--------|
| 开源模型 | Stable Diffusion, Flux, HunyuanVideo, CogView, Wan, LoRA, open source weights |
| ComfyUI | ComfyUI, custom node, workflow, comfy |
| 商用产品 | Lovart, Gemini, GPT, OpenAI, Claude, Anthropic, Midjourney, DALL-E, Sora |
| Agent & Skills | agent, MCP, tool use, function calling, autonomous, agentic |
| 训练与部署 | fine-tune, training, LoRA, RLHF, inference, quantization, deployment |

## 各数据源技术方案

| 数据源 | 主方案 | 备选 | 难度 |
|--------|--------|------|------|
| YouTube | YouTube Data API v3 (免费 10K units/天) | RSSHub | 低 |
| Bilibili | RSSHub `/bilibili/user/video/:uid` | bilibili-api-python | 低 |
| GitHub | 抓取 trending 页 + watch_repos releases API | RSSHub | 低 |
| RSS | feedparser 直接解析 | - | 低 |
| Twitter/X | RSSHub (需配置 cookie) | 接受部分丢失 | 中 |
| 微信公众号 | V1: 手动输入 URL; V2: WeRSS 付费 | - | 高 |

## Notion 数据库结构

- **Title** (title): 中文标题
- **Source** (select): YouTube / Bilibili / Twitter / GitHub / RSS / Manual
- **Category** (multi_select): 开源模型 / ComfyUI / 商用产品 / Agent&Skills / 训练与部署 / 其他
- **Summary** (rich_text): AI 生成的 2-3 句中文摘要
- **Importance** (number 1-5): LLM 评估的重要度
- **URL** (url): 原文链接
- **Author** (rich_text): 作者/频道名
- **Date** (date): 发布日期
- **Collected** (date): 采集日期

## 分阶段实施

### Phase 1: 基础骨架（2-3 天） — 已完成
- [x] `collectors/base.py`: ContentItem dataclass + BaseScraper 抽象类
- [x] `storage/models.py` + `storage/database.py`: SQLite 建表 + CRUD
- [x] `collectors/rss_collector.py`: feedparser 通用 RSS 采集
- [x] `collectors/github_collector.py`: GitHub Trending 页面解析
- [x] `outputs/markdown_writer.py`: 本地 Markdown 日报输出
- [x] `main.py`: CLI 入口，串联 采集 -> 存储 -> 输出 流程
- [x] `config.yaml`: 基础配置文件
- [x] `requirements.txt`: 依赖管理
- [x] 端到端验证：运行一次，输出 Markdown 日报

### Phase 2: 扩展数据源 + LLM（2-3 天） — 已完成
- [x] `deploy/docker-compose.rsshub.yml`: 部署 RSSHub Docker
- [x] `collectors/youtube_collector.py`: YouTube Data API v3
- [x] `collectors/bilibili_collector.py`: Bilibili 采集
- [x] `collectors/twitter_collector.py`: Twitter/X 采集（改用 Nitter RSS，不依赖 RSSHub）
- [x] `processor/scorer.py`: LLM 摘要 + 分类 + 评分（合并了原计划的 summarizer）
- [x] `processor/classifier.py`: 按 focus_areas 关键词预分类
- [x] `processor/dedup.py`: URL + 标题相似度去重
- [x] `collectors/hackernews_collector.py`: HackerNews Top Stories（超额）
- [x] `collectors/reddit_collector.py`: Reddit 子版采集（超额）
- [x] `collectors/telegram_collector.py`: Telegram 频道采集（超额）
- [x] `collectors/twitter_trending_collector.py`: Twitter 全站 AI 高赞搜索 Top 10（超额）

### Phase 3: 输出集成（2 天） — 已完成
- [x] `outputs/notion_writer.py`: Notion SDK 数据库写入（代码完成，enabled: false）
- [x] `web/app.py`: FastAPI Web Dashboard（替代原计划的 Jinja2 静态页，功能更强）
- [x] `outputs/feishu_bot.py`: 飞书机器人推送（替代原计划的 Server酱微信推送）
- ~~`templates/daily_report.html`~~: 不再需要（Web Dashboard 改用 FastAPI JSON API + 前端内嵌）

### Phase 4: 部署与完善（1-2 天） — 已完成
- [x] `deploy/ai-news.service` + `ai-news.timer`: systemd 定时任务
- [x] 在服务器上部署：L20_1 (10.102.80.15)，路径 /AIGC_Group/XD-AIGC-ai-news
- [x] 错误处理、重试、日志
- [x] `CLAUDE.md`: Claude Code 项目规则（替代原计划的 Cursor Skill）
- [x] README 使用文档 + `docs/OPERATIONS.md` 运维手册

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| RSS 统一化 | RSSHub (Docker) | 一个服务覆盖多平台 |
| RSS 解析 | feedparser | Python 标准 RSS 库 |
| HTTP 客户端 | httpx | 异步 + 代理支持好 |
| YouTube | google-api-python-client | 官方 SDK |
| 本地存储 | SQLite | 轻量，无需额外服务 |
| LLM 摘要 | OpenAI API (gpt-4o-mini) | 成本低 (~$0.15/天) |
| Notion 写入 | notion-client | 官方 SDK |
| Web 日报 | Jinja2 静态 HTML | 简单，无需前端框架 |
| 微信推送 | Server酱 HTTP API | 免费，简单 |
| 定时调度 | systemd timer | 稳定可靠 |
| 代理 | http://172.24.12.140:18888 | 复用现有代理 |

## 风险和备选

| 风险 | 缓解方案 |
|------|----------|
| Twitter/RSSHub 不稳定 | 接受部分丢失；后续可接入付费 API |
| 微信公众号无免费方案 | V1 手动 URL；V2 WeRSS 付费 |
| YouTube API 额度用尽 | 降级到 RSSHub 路由 |
| LLM API 不可用 | 降级为只输出标题+链接 |
