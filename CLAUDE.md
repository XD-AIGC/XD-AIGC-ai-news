# AI News Aggregator

全自动每日 AI 资讯聚合系统。多源采集 + LLM 摘要 + 多渠道输出。

## Architecture

- `main.py` is CLI entry point only - no business logic
- `collectors/` handles data fetching from external sources
- `processor/` handles LLM summarization, classification, dedup
- `outputs/` handles writing to Notion, web, markdown, push notifications
- `storage/` handles SQLite persistence
- `web/` FastAPI dashboard (started with `--serve`)
- `config.yaml` for all configuration, `.env` for secrets (NEVER commit)

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
2. Add source config section in `config.yaml` under `sources:`
3. Register collector in `main.py` `build_collectors()`

## When Adding New Output

1. Create `outputs/new_output.py`
2. Add output config section in `config.yaml` under `output:`
3. Register output in `main.py` `run()`

## Deployment

- Server: L20_1 (10.102.80.15), path: /AIGC/XD-AIGC-ai-news
- Scheduling: systemd timer (daily)
- RSSHub: Docker container on same server

## Commit Messages

- Use English for all commit messages
- Short imperative style: "Add YouTube collector", "Fix dedup logic"

## Key Dependencies

feedparser, httpx, beautifulsoup4, pydantic, pyyaml, python-dotenv, openai, notion-client, google-api-python-client, fastapi, uvicorn
