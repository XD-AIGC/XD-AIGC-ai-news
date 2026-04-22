"""Subscribe API: analyze URLs and manage user_sources."""

import ipaddress
import json
import logging
import os
import socket
from typing import Optional
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from processor.subscribe_analyzer import analyze_url
from storage.config_loader import load_config
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


_BLOCKED_HOSTNAMES = {"metadata.google.internal", "metadata"}


def _is_safe_external_url(url: str) -> tuple[bool, str]:
    """Reject URLs that resolve to private / loopback / link-local / metadata IPs.

    Returns (allowed, reason_if_blocked).
    """
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported scheme: {parsed.scheme!r}"

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return False, "URL has no hostname"

    # Cheap allowlist-by-denylist for well-known cloud metadata hostnames
    if hostname in _BLOCKED_HOSTNAMES:
        return False, f"Blocked hostname: {hostname}"

    # Resolve to IPs (all addresses — v4 and v6)
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False, f"Target IP {ip} is in a blocked range"

    return True, ""


def _pick_proxy(proxy_cfg: dict) -> Optional[str]:
    """Return first reachable proxy URL from config, or None."""
    raw = proxy_cfg.get("urls", [])
    if isinstance(raw, str):
        urls = [u.strip() for u in raw.split(",") if u.strip()]
    else:
        urls = raw
    for url in urls:
        parsed = urlparse(url)
        try:
            sock = socket.create_connection((parsed.hostname, parsed.port or 18888), timeout=2)
            sock.close()
            return url
        except (OSError, socket.timeout):
            continue
    return None


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

    # SSRF defense: reject private / loopback / metadata IPs
    allowed, reason = _is_safe_external_url(url)
    if not allowed:
        raise HTTPException(status_code=400, detail=f"URL rejected: {reason}")

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
        cfg = load_config()

        # Pick a reachable proxy if configured
        proxy_url = _pick_proxy(cfg.get("proxy", {}))

        client_kwargs = {
            "timeout": httpx.Timeout(30.0),
            "follow_redirects": False,  # SSRF defense (see SSRF fix)
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        async with httpx.AsyncClient(**client_kwargs) as client:
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
