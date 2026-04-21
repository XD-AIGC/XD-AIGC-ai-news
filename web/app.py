"""FastAPI web dashboard for AI News Aggregator."""

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from storage.database import NewsDatabase

load_dotenv()

STATIC_DIR = Path(__file__).parent / "static"
DB_PATH = os.getenv("NEWS_DB_PATH", "./data/news.db")

app = FastAPI(title="AI News Dashboard", docs_url="/api/docs")


class NewsItemResponse(BaseModel):
    id: str
    source_type: str
    title: str
    url: str
    content: str
    author: str
    published_at: Optional[str]
    collected_at: str
    ai_score: Optional[float]
    ai_summary: Optional[str]
    ai_categories: list[str]
    ai_tags: list[str]
    theme: str = "ai"


class PaginatedNews(BaseModel):
    items: list[NewsItemResponse]
    total: int
    page: int
    page_size: int
    pages: int


def _get_db() -> NewsDatabase:
    db = NewsDatabase(DB_PATH)
    db.connect()
    return db


@app.get("/api/news", response_model=PaginatedNews)
def list_news(
    date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD range start"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD range end"),
    source: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    theme: Optional[str] = Query(None, description="ai | fashion"),
    q: Optional[str] = Query(None, description="Search query"),
    min_score: Optional[float] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    db = _get_db()
    try:
        items, total = db.search_items(
            date=date, date_from=date_from, date_to=date_to,
            source=source, category=category, theme=theme,
            q=q, min_score=min_score, page=page, page_size=page_size,
        )
        pages = (total + page_size - 1) // page_size if total else 0
        return PaginatedNews(
            items=[_item_to_resp(i) for i in items],
            total=total, page=page, page_size=page_size, pages=pages,
        )
    finally:
        db.close()


@app.get("/api/dates")
def available_dates():
    db = _get_db()
    try:
        return db.get_available_dates()
    finally:
        db.close()


@app.get("/api/stats")
def stats(
    date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD range start"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD range end"),
    theme: Optional[str] = Query(None, description="ai | fashion"),
):
    db = _get_db()
    try:
        return db.get_stats(date=date, date_from=date_from, date_to=date_to, theme=theme)
    finally:
        db.close()


def _item_to_resp(item) -> NewsItemResponse:
    return NewsItemResponse(
        id=item.id,
        source_type=item.source_type.value,
        title=item.title,
        url=item.url,
        content=item.content[:500],
        author=item.author,
        published_at=item.published_at.isoformat() if item.published_at else None,
        collected_at=item.collected_at.isoformat(),
        ai_score=item.ai_score,
        ai_summary=item.ai_summary,
        ai_categories=item.ai_categories,
        ai_tags=item.ai_tags,
        theme=item.theme.value if hasattr(item.theme, "value") else str(item.theme),
    )


DOCS_DIR = Path(__file__).parent.parent / "docs"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Serve weekly digest data (images, JSON) from docs/data/weekly/
weekly_data_dir = DOCS_DIR / "data" / "weekly"
if weekly_data_dir.exists():
    app.mount(
        "/data/weekly",
        StaticFiles(directory=str(weekly_data_dir)),
        name="weekly-data",
    )


@app.get("/")
@app.get("/index.html")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/weekly")
def weekly():
    weekly_html = DOCS_DIR / "weekly.html"
    if weekly_html.exists():
        return FileResponse(weekly_html)
    return {"error": "Weekly page not found"}


@app.get("/weekly.js")
def weekly_js():
    weekly_js_file = DOCS_DIR / "weekly.js"
    if weekly_js_file.exists():
        return FileResponse(weekly_js_file, media_type="application/javascript")
    return {"error": "weekly.js not found"}


@app.get("/subscribe.html")
def subscribe_page():
    return FileResponse(STATIC_DIR / "subscribe.html")


@app.get("/explore")
def explore():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=301)


from web.routers.subscribe import router as subscribe_router
app.include_router(subscribe_router)

from web.ai_chat import register_ai_routes
register_ai_routes(app)
