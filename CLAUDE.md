# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

全自动每日 AI 资讯聚合系统。多源采集 + LLM 摘要 + 多渠道输出。

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run daily collection (collect + AI score + output)
python main.py

# Collect last N days
python main.py --days 3

# Collect only (skip AI scoring)
python main.py --skip-ai

# Local dev without proxy
python main.py --no-proxy --skip-ai

# Start web dashboard
python main.py --serve --port 8800

# Verbose/debug logging
python main.py -v
```

No test suite exists. Verify changes by running `python main.py --skip-ai --no-proxy -v` and checking logs.

## Architecture

- `main.py` — CLI entry point only, no business logic
- `collectors/` — data fetching from external sources
- `processor/` — LLM summarization, classification, dedup
- `outputs/` — writing to Notion, web, markdown, push notifications
- `storage/` — SQLite persistence
- `web/` — FastAPI dashboard (started with `--serve`)
- `config.yaml` — all configuration; `.env` — secrets (NEVER commit)

## Pipeline Flow

`main.py run()` executes this sequence:

1. **Collect** — all enabled collectors run concurrently via `asyncio.gather`, each returns `list[ContentItem]`
2. **Dedup** — URL exact match + Jaccard title similarity (threshold 0.7)
3. **Classify** — keyword-based pre-classification from `focus_areas` in config
4. **Save** — insert to SQLite, skip URL duplicates
5. **AI Score** — LLM scores/summarizes/categorizes unscored items (OpenAI-compatible API via raw `httpx`)
6. **Output** — markdown report, Notion, Feishu bot (each independently enabled)

## Core Data Model

`ContentItem` (pydantic, defined in `collectors/base.py`) is the universal data object passed through the entire pipeline. All collectors produce it, all outputs consume it.

## Focus Areas

- 开源模型: Stable Diffusion, Flux, HunyuanVideo, CogView, Wan, LoRA, Hugging Face
- ComfyUI: 新节点、工作流、插件更新
- 商用产品: Lovart, Gemini, OpenAI, Claude, Anthropic, Midjourney
- Agent & Skills: AI Agent, MCP, tool use, function calling
- 训练与部署: fine-tune, LoRA, RLHF, 推理优化, 量化

## Coding Conventions

- Python 3.10+, type hints required
- Single file MUST NOT exceed 500 lines
- Single function MUST NOT exceed 50 lines
- 4-space indent, snake_case
- All HTTP requests MUST use proxy from config (via `config.yaml` proxy section)
- All API keys come from `.env` file, referenced in `config.yaml` as `${VAR_NAME}`
- Use `httpx` for HTTP requests (async + proxy friendly)
- Use `logging` module, not print()

## When Adding New Data Source

1. Create `collectors/new_source_collector.py` inheriting `BaseScraper` from `collectors/base.py`
2. Implement `async fetch(self, since: datetime) -> list[ContentItem]`
3. Add source config section in `config.yaml` under `sources:`
4. Register collector in `main.py` `build_collectors()`

## When Adding New Output

1. Create `outputs/new_output.py`
2. Add output config section in `config.yaml` under `output:`
3. Register output in `main.py` `run()`

## Notable Implementation Details

- `AIScorer` uses raw `httpx` POST to OpenAI-compatible `/chat/completions` (not the openai SDK)
- Twitter collectors: `twitter_collector.py` scrapes user timelines; `twitter_trending_collector.py` uses `twikit` library (free, no API key needed)
- Config env var resolution: `${VAR_NAME}` in `config.yaml` is replaced by `os.getenv()` at load time
- Database dedup is URL-based (`url_exists()`); in-memory dedup also uses title similarity

## Deployment

- Server: L20_1 (10.102.80.15), path: /AIGC/XD-AIGC-ai-news
- Scheduling: systemd timer (daily)
- RSSHub: Docker container on same server

## Commit Messages

- Use English for all commit messages
- Short imperative style: "Add YouTube collector", "Fix dedup logic"

## Key Dependencies

feedparser, httpx, beautifulsoup4, pydantic, pyyaml, python-dotenv, openai, notion-client, google-api-python-client, fastapi, uvicorn, twikit
