"""AI chat and summarize endpoints for the news dashboard."""

import hashlib
import logging
import os
import re
import time

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from storage.database import NewsDatabase

load_dotenv()

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("NEWS_DB_PATH", "./data/news.db")

_summary_cache: dict[str, dict] = {}
_CACHE_TTL = 3600  # 1 hour

SUMMARIZE_SYSTEM_PROMPT = """你是 AI News 的智能助手。用户给你一组 AI 领域的新闻，请生成一份结构化但自然的摘要。

格式要求：
## 📌 今日要点
用 2-3 句自然的话概括最重要的事情，就像跟朋友聊天一样。

## 🔥 热门趋势
列出 3-5 个趋势方向，每个用一行简述。

## ⭐ 值得关注
挑 3-5 个最值得关注的具体项目/产品/论文，每个简要说明为什么值得关注。

## 💡 一句话总结
用一句话总结整体态势。

保持语气自然亲切，像一个懂行的朋友在跟你聊天。避免过于正式的表述。"""

CHAT_SYSTEM_PROMPT = """你是 AI News 的智能助手。以下是用户当前查看的 AI 领域新闻数据，请基于这些数据回答用户的问题。回答要自然亲切，像一个懂行的朋友。如果问题超出数据范围，坦诚说明。"""


def _load_llm_config() -> dict:
    with open("config.yaml") as f:
        raw = f.read()
    raw = re.sub(r"\$\{(\w+)\}", lambda m: os.getenv(m.group(1), ""), raw)
    cfg = yaml.safe_load(raw)
    return cfg.get("llm", {})


def _get_db() -> NewsDatabase:
    db = NewsDatabase(DB_PATH)
    db.connect()
    return db


def _cache_key(params: dict) -> str:
    s = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
    return hashlib.md5(s.encode()).hexdigest()


def _get_cached(key: str) -> str | None:
    entry = _summary_cache.get(key)
    if entry and (time.time() - entry["timestamp"]) < _CACHE_TTL:
        return entry["summary"]
    return None


def _set_cache(key: str, summary: str) -> None:
    _summary_cache[key] = {"summary": summary, "timestamp": time.time()}


def _fetch_top_items(params: dict) -> list:
    db = _get_db()
    try:
        items, _ = db.search_items(
            date=params.get("date"),
            date_from=params.get("date_from"),
            date_to=params.get("date_to"),
            source=params.get("source"),
            category=params.get("category"),
            min_score=params.get("min_score"),
            page=1,
            page_size=30,
        )
        return items
    finally:
        db.close()


def _build_news_context(items: list) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        score = f"{item.ai_score:.1f}" if item.ai_score is not None else "N/A"
        summary = item.ai_summary or item.title
        lines.append(f"{i}. [{score}] {item.title} ({item.source_type.value})\n   {summary}")
    return "\n".join(lines)


async def _call_llm(messages: list[dict], max_tokens: int) -> str:
    cfg = _load_llm_config()
    model = cfg.get("model", "gpt-4o-mini")
    api_key = cfg.get("api_key", "")
    base_url = cfg.get("base_url", "https://api.openai.com/v1").rstrip("/")
    temperature = cfg.get("temperature", 0.3)
    proxy = os.getenv("HTTP_PROXY", "") or None

    client_kwargs: dict = {"timeout": httpx.Timeout(60.0)}
    if proxy:
        client_kwargs["proxy"] = proxy

    async with httpx.AsyncClient(**client_kwargs) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


class SummarizeRequest(BaseModel):
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    source: str | None = None
    category: str | None = None
    min_score: float | None = None


class ChatRequest(BaseModel):
    messages: list[dict]
    date: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    source: str | None = None
    category: str | None = None
    min_score: float | None = None


def register_ai_routes(app: FastAPI) -> None:
    @app.post("/api/summarize")
    async def summarize(req: SummarizeRequest):
        params = req.model_dump()
        key = _cache_key(params)
        cached = _get_cached(key)
        if cached:
            return {"summary": cached}

        items = _fetch_top_items(params)
        if not items:
            return {"summary": "当前筛选条件下没有找到相关新闻。"}

        news_context = _build_news_context(items)
        user_msg = f"以下是 {len(items)} 条 AI 新闻，请生成摘要：\n\n{news_context}"
        messages = [
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        try:
            summary = await _call_llm(messages, max_tokens=1024)
        except Exception as e:
            logger.warning("Summarize LLM call failed: %s", e)
            return {"summary": "抱歉，AI 摘要生成失败，请稍后重试。"}

        _set_cache(key, summary)
        return {"summary": summary}

    @app.post("/api/chat")
    async def chat(req: ChatRequest):
        params = {k: v for k, v in req.model_dump().items() if k != "messages"}
        items = _fetch_top_items(params)

        news_context = _build_news_context(items) if items else "（当前筛选条件下暂无新闻数据）"
        system_content = f"{CHAT_SYSTEM_PROMPT}\n\n当前新闻数据（共 {len(items)} 条）：\n{news_context}"

        messages = [{"role": "system", "content": system_content}] + req.messages

        try:
            reply = await _call_llm(messages, max_tokens=800)
        except Exception as e:
            logger.warning("Chat LLM call failed: %s", e)
            return {"reply": "抱歉，AI 助手暂时无法响应，请稍后重试。"}

        return {"reply": reply}
