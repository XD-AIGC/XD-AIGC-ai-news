# AI News Aggregator 运维手册

## 系统概述

全自动 AI 资讯每日聚合系统，部署在 L20_1 服务器上，每天早上 8:00 自动采集、AI 评分、生成报告。

| 项目 | 信息 |
|------|------|
| 服务器 | L20_1 (10.102.80.15) |
| 项目路径 | `/AIGC_Group/XD-AIGC-ai-news` |
| Conda 环境 | `xd-aigc-ainews` |
| Web Dashboard | http://10.102.80.15:8800 |
| GitHub | https://github.com/XD-AIGC/XD-AIGC-ai-news |

## 数据源

| 源 | 数量 | 说明 |
|----|------|------|
| RSS | 6 个 feed | OpenAI、Anthropic、Google AI、HuggingFace、Gemini、Mistral |
| YouTube | 6 个频道 | Two Minute Papers、Yannic Kilcher、Bycloud、Olivio Sarikas、Fireship、Matt Wolfe |
| GitHub | Trending + 3 仓库 | 每日趋势 + ComfyUI/Flux/SD-WebUI releases |
| HackerNews | Top 30 | 分数 >= 100 |
| Reddit | 3 个子版 | r/MachineLearning、r/LocalLLaMA、r/StableDiffusion |
| Telegram | 1 个频道 | 在花频道 |

## 日常使用

### 查看新闻

浏览器打开 http://10.102.80.15:8800 即可，支持：

- 按日期切换
- 按来源筛选（RSS / GitHub / HN / Reddit / Telegram / YouTube）
- 按分类筛选（开源模型 / ComfyUI / 商用产品 / Agent & Skills / 训练与部署）
- AI 评分过滤（滑块调节最低分）
- 关键词搜索
- 暗色/亮色主题切换

### 手动触发采集

```bash
ssh ubuntu@10.102.80.15
cd /AIGC_Group/XD-AIGC-ai-news
conda activate xd-aigc-ainews
python main.py --days 1
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--days 3` | 采集最近 3 天的内容 |
| `--skip-ai` | 只采集不评分（快速测试） |
| `--no-proxy` | 不走代理（调试用） |
| `-v` | 显示详细日志 |

## 服务管理

系统通过 systemd 管理两个服务：

### ai-news.timer — 每日定时采集

```bash
# 查看定时器状态
systemctl status ai-news.timer

# 查看下次执行时间
systemctl list-timers ai-news.timer

# 查看最近一次采集日志
journalctl -u ai-news.service --since today

# 停止/启动定时器
sudo systemctl stop ai-news.timer
sudo systemctl start ai-news.timer
```

### ai-news-web.service — Web Dashboard

```bash
# 查看状态
systemctl status ai-news-web

# 重启（更新代码后需要）
sudo systemctl restart ai-news-web

# 查看日志
journalctl -u ai-news-web -f

# 停止/启动
sudo systemctl stop ai-news-web
sudo systemctl start ai-news-web
```

## 更新部署

当代码有更新时：

```bash
cd /AIGC_Group/XD-AIGC-ai-news
git pull
sudo systemctl restart ai-news-web
```

如果更新了 Python 依赖：

```bash
conda activate xd-aigc-ainews
pip install -r requirements.txt
sudo systemctl restart ai-news-web
```

## 配置文件

| 文件 | 用途 | 是否提交 Git |
|------|------|-------------|
| `config.yaml` | 数据源、模型、输出、代理等配置 | 是 |
| `.env` | API 密钥 | 否（gitignore） |

### .env 当前配置项

```
YOUTUBE_API_KEY=xxx        # YouTube Data API v3
OPENAI_API_KEY=xxx         # Google AI Studio API key
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
NOTION_API_KEY=            # 待配置
NOTION_DATABASE_ID=        # 待配置
FEISHU_WEBHOOK_URL=        # 待配置
GITHUB_TOKEN=              # 可选，提高 API 限额
```

### 修改数据源

编辑 `config.yaml`，例如添加 YouTube 频道：

```yaml
youtube:
  channels:
    - { id: "频道ID", name: "频道名" }
```

频道 ID 获取方法：打开 YouTube 频道页面，URL 中 `/channel/` 后面的字符串。

### 修改 AI 模型

```yaml
llm:
  model: "gemini-3.1-flash-lite-preview"  # 当前使用
  temperature: 0.3
  score_threshold: 6.0  # 低于此分数的新闻会被标记为低优先级
```

## 数据存储

| 路径 | 内容 |
|------|------|
| `data/news.db` | SQLite 数据库，所有新闻数据 |
| `reports/markdown/` | 每日 Markdown 报告（按日期命名） |

### 查看数据库

```bash
cd /AIGC_Group/XD-AIGC-ai-news
sqlite3 data/news.db
```

常用查询：

```sql
-- 今天采集了多少条
SELECT COUNT(*) FROM news WHERE collected_at LIKE '2026-03-05%';

-- 按来源统计
SELECT source_type, COUNT(*) FROM news GROUP BY source_type;

-- 查看高分新闻
SELECT title, ai_score, ai_categories FROM news WHERE ai_score >= 7 ORDER BY ai_score DESC;

-- 数据库总大小
SELECT COUNT(*) AS total_items FROM news;
```

## 故障排查

### Web Dashboard 打不开

```bash
# 检查服务状态
systemctl status ai-news-web

# 如果显示 failed，查看原因
journalctl -u ai-news-web -n 20 --no-pager

# 重启
sudo systemctl restart ai-news-web
```

### 定时采集没有执行

```bash
# 确认 timer 在运行
systemctl status ai-news.timer

# 查看采集日志
journalctl -u ai-news.service --since "1 day ago"

# 手动触发一次测试
sudo systemctl start ai-news.service
journalctl -u ai-news.service -f
```

### AI 评分失败

- 检查 `.env` 中 `OPENAI_API_KEY` 是否正确
- 检查 Google AI Studio 是否有额度限制
- 可以加 `--skip-ai` 先只采集不评分

### RSS 源返回 404

某些博客会更换 RSS 地址，编辑 `config.yaml` 更新 URL，然后：

```bash
git add config.yaml && git commit -m "Update RSS URLs" && git push
sudo systemctl restart ai-news-web
```

## 待配置功能

| 功能 | 所需操作 |
|------|---------|
| 飞书机器人推送 | 在飞书群创建自定义机器人，将 webhook URL 填入 `.env` 的 `FEISHU_WEBHOOK_URL`，在 `config.yaml` 中设 `feishu.enabled: true` |
| Notion 输出 | 创建 Notion Integration + 数据库，填入 `.env` 的 `NOTION_API_KEY` 和 `NOTION_DATABASE_ID`，在 `config.yaml` 中设 `notion.enabled: true` |
| Bilibili/Twitter | 在服务器上启动 RSSHub：`cd deploy && docker compose -f docker-compose.rsshub.yml up -d`，然后在 `config.yaml` 中设 `bilibili.enabled: true` / `twitter.enabled: true` |

## 架构简图

```
                     ┌──────────────┐
                     │  systemd     │
                     │  timer 08:00 │
                     └──────┬───────┘
                            │
                            ▼
┌─────────┐  ┌─────────────────────────────┐  ┌──────────┐
│ RSS     │  │                             │  │ SQLite   │
│ YouTube │──▶  main.py (采集+AI评分)     │──▶│ news.db  │
│ GitHub  │  │                             │  └────┬─────┘
│ HN      │  └─────────────────────────────┘       │
│ Reddit  │                                        │
│ Telegram│         ┌──────────────────────┐       │
└─────────┘         │ FastAPI Web Dashboard│◀──────┘
                    │   :8800              │
                    └──────────────────────┘
                             ▲
                             │
                        浏览器访问
                   http://10.102.80.15:8800
```
