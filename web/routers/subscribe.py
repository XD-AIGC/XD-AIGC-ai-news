"""Subscribe API: analyze URLs and manage user_sources."""

import json
import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from processor.subscribe_analyzer import analyze_url
from storage.database import NewsDatabase
from storage.user_sources import (
    UserSource, compute_url_hash, get_by_id, get_by_url_hash,
    insert_user_source, list_by_status, list_all, update_fields,
    update_status,
)

logger = logging.getLogger(__name__)
load_dotenv()

router = APIRouter(prefix="/api/subscribe", tags=["subscribe"])

DB_PATH = os.getenv("NEWS_DB_PATH", "./data/news.db")


def _load_config_for_analyzer() -> dict:
    """Load config.yaml for analyzer (re-reads each request — simple but OK for v1)."""
    import re
    import yaml

    with open("config.yaml", "r", encoding="utf-8") as f:
        raw = f.read()

    def replace_env(match):
        return os.getenv(match.group(1), match.group(0))

    resolved = re.sub(r"\$\{(\w+)\}", replace_env, raw)
    return yaml.safe_load(resolved)


def _get_db() -> NewsDatabase:
    db = NewsDatabase(DB_PATH)
    db.connect()
    return db


class AnalyzeRequest(BaseModel):
    url: str


class AnalyzeResponse(BaseModel):
    analysis_id: int
    url_hash: str
    detected_type: str
    sample: list[dict]
    llm: dict
    cached: bool = False
    already_subscribed: bool = False
    previously_rejected: bool = False


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(req: AnalyzeRequest):
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    url_hash = compute_url_hash(url)
    db = _get_db()

    try:
        existing = get_by_url_hash(db, url_hash)

        if existing and existing.status == "active":
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "rss",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme,
                    "suggested_focus_areas": json.loads(existing.focus_areas or "[]"),
                    "quality_score": 0,
                    "verdict": "accept",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
                already_subscribed=True,
            )

        if existing and existing.status == "pending":
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "unknown",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme,
                    "suggested_focus_areas": json.loads(existing.focus_areas or "[]"),
                    "quality_score": 0,
                    "verdict": "accept" if existing.theme in ("ai", "fashion") else "manual_review",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
            )

        if existing and existing.status == "rejected":
            return AnalyzeResponse(
                analysis_id=existing.id,
                url_hash=url_hash,
                detected_type=existing.source_type or "unknown",
                sample=json.loads(existing.sample_json or "[]"),
                llm={
                    "theme": existing.theme or "neither",
                    "suggested_focus_areas": [],
                    "quality_score": 0,
                    "verdict": "reject",
                    "reasoning": existing.llm_reasoning,
                },
                cached=True,
                previously_rejected=True,
            )

        # Fresh analysis
        cfg = _load_config_for_analyzer()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0), follow_redirects=True) as client:
            result = await analyze_url(url, cfg, client)

        # Persist as pending
        src = UserSource(
            url=url,
            url_hash=url_hash,
            status="pending",
            source_type=result["detected_type"],
            normalized_config=json.dumps(result.get("normalized_config", {})),
            theme=result["llm"].get("theme", "ai"),
            focus_areas=json.dumps(result["llm"].get("suggested_focus_areas", [])),
            llm_reasoning=result["llm"].get("reasoning", ""),
            sample_json=json.dumps(result["sample"]),
            name="",
        )
        analysis_id = insert_user_source(db, src)

        return AnalyzeResponse(
            analysis_id=analysis_id,
            url_hash=url_hash,
            detected_type=result["detected_type"],
            sample=result["sample"],
            llm=result["llm"],
        )
    finally:
        db.close()


class ConfirmOverrides(BaseModel):
    theme: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    name: Optional[str] = None


class ConfirmRequest(BaseModel):
    analysis_id: int
    action: str                     # 'accept' | 'reject'
    overrides: Optional[ConfirmOverrides] = None


class ConfirmResponse(BaseModel):
    status: str
    source_id: int


@router.post("/confirm", response_model=ConfirmResponse)
async def confirm(req: ConfirmRequest):
    if req.action not in ("accept", "reject"):
        raise HTTPException(status_code=400, detail="action must be 'accept' or 'reject'")

    db = _get_db()
    try:
        src = get_by_id(db, req.analysis_id)
        if not src:
            raise HTTPException(status_code=404, detail="Analysis not found")

        if req.action == "reject":
            update_status(db, req.analysis_id, "rejected")
            return ConfirmResponse(status="rejected", source_id=req.analysis_id)

        # Apply overrides
        fields = {}
        if req.overrides:
            if req.overrides.theme and req.overrides.theme not in ("ai", "fashion"):
                raise HTTPException(status_code=400, detail="theme must be 'ai' or 'fashion'")
            if req.overrides.theme:
                fields["theme"] = req.overrides.theme
            if req.overrides.focus_areas is not None:
                fields["focus_areas"] = json.dumps(req.overrides.focus_areas)
            if req.overrides.name:
                fields["name"] = req.overrides.name
        if fields:
            update_fields(db, req.analysis_id, fields)

        update_status(db, req.analysis_id, "active")
        return ConfirmResponse(status="active", source_id=req.analysis_id)
    finally:
        db.close()


class SubscriptionSummary(BaseModel):
    id: int
    url: str
    name: str
    source_type: str
    theme: str
    focus_areas: list[str]
    status: str
    created_at: Optional[str]
    activated_at: Optional[str]
    last_fetch_at: Optional[str]
    last_fetch_status: Optional[str]
    consecutive_failures: int


def _to_summary(src: UserSource) -> SubscriptionSummary:
    try:
        focus = json.loads(src.focus_areas or "[]")
    except json.JSONDecodeError:
        focus = []
    return SubscriptionSummary(
        id=src.id,
        url=src.url,
        name=src.name,
        source_type=src.source_type,
        theme=src.theme,
        focus_areas=focus,
        status=src.status,
        created_at=src.created_at,
        activated_at=src.activated_at,
        last_fetch_at=src.last_fetch_at,
        last_fetch_status=src.last_fetch_status,
        consecutive_failures=src.consecutive_failures,
    )


@router.get("/list", response_model=list[SubscriptionSummary])
def list_subscriptions(status: Optional[str] = Query(None)):
    db = _get_db()
    try:
        if status:
            return [_to_summary(s) for s in list_by_status(db, status)]
        return [_to_summary(s) for s in list_all(db)]
    finally:
        db.close()


@router.delete("/{source_id}")
def delete_subscription(source_id: int):
    """Soft-delete: mark as rejected. Preserves history / prevents re-analysis."""
    db = _get_db()
    try:
        src = get_by_id(db, source_id)
        if not src:
            raise HTTPException(status_code=404, detail="Not found")
        update_status(db, source_id, "rejected")
        return {"status": "rejected", "source_id": source_id}
    finally:
        db.close()


class PatchSubscription(BaseModel):
    status: Optional[str] = None            # 'active' | 'disabled' | 'rejected'
    theme: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    name: Optional[str] = None


@router.patch("/{source_id}", response_model=SubscriptionSummary)
def patch_subscription(source_id: int, patch: PatchSubscription):
    db = _get_db()
    try:
        src = get_by_id(db, source_id)
        if not src:
            raise HTTPException(status_code=404, detail="Not found")

        fields = {}
        if patch.theme and patch.theme not in ("ai", "fashion"):
            raise HTTPException(status_code=400, detail="theme must be 'ai' or 'fashion'")
        if patch.theme:
            fields["theme"] = patch.theme
        if patch.focus_areas is not None:
            fields["focus_areas"] = json.dumps(patch.focus_areas)
        if patch.name is not None:
            fields["name"] = patch.name
        if fields:
            update_fields(db, source_id, fields)

        if patch.status:
            if patch.status not in ("pending", "active", "rejected", "disabled"):
                raise HTTPException(status_code=400, detail="Invalid status")
            update_status(db, source_id, patch.status)

        updated = get_by_id(db, source_id)
        return _to_summary(updated)
    finally:
        db.close()
