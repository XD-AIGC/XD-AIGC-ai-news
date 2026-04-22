"""Subscription analyzer: URL type detection + sample fetch + LLM judgment."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import feedparser
import httpx

logger = logging.getLogger(__name__)


@dataclass
class DetectionResult:
    type: str                                  # 'rss' | 'youtube' | 'twitter' | 'bilibili' | 'reddit' | 'telegram' | 'github' | 'unknown'
    config: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None                # populated when type='unknown'


def detect_url_type(
    url: str,
    rsshub_routes: list[dict],
    rsshub_base_url: str = "",
) -> DetectionResult:
    """Run detector chain from most-specific to most-generic. First match wins.

    Covers all detectors determinable from URL pattern alone. Direct-RSS
    probing and HTML autodiscovery require HTTP — call probe_rss_feed(url)
    separately when detect_url_type returns 'unknown'.
    """
    # Strip fragment, normalize
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")

    # 1) YouTube
    if host in ("youtube.com", "m.youtube.com"):
        m = re.match(r"^/channel/(UC[\w-]+)", path)
        if m:
            return DetectionResult("youtube", {"channel_id": m.group(1)})
        m = re.match(r"^/@([\w.-]+)", path)
        if m:
            return DetectionResult("youtube", {"handle": m.group(1)})

    # 2) Bilibili space
    if host == "space.bilibili.com":
        m = re.match(r"^/(\d+)", path)
        if m:
            return DetectionResult("bilibili", {"uid": m.group(1)})

    # 3) Twitter / X
    if host in ("twitter.com", "x.com"):
        m = re.match(r"^/([\w_]+)$", path) or re.match(r"^/([\w_]+)/status/", path)
        if m:
            return DetectionResult("twitter", {"handle": m.group(1)})

    # 4) Reddit subreddit
    if host == "reddit.com" or host.endswith(".reddit.com"):
        m = re.match(r"^/r/([\w_]+)", path)
        if m:
            return DetectionResult("reddit", {"subreddit": m.group(1)})

    # 5) Telegram
    if host == "t.me":
        m = re.match(r"^/([\w_]+)", path)
        if m:
            return DetectionResult("telegram", {"channel": m.group(1)})

    # 6) GitHub repo
    if host == "github.com":
        m = re.match(r"^/([\w.-]+)/([\w.-]+)", path)
        if m:
            return DetectionResult("github", {"owner": m.group(1), "repo": m.group(2)})

    # 7) RSSHub routes (full URL match including host)
    for route in rsshub_routes or []:
        pattern = route.get("pattern", "")
        template = route.get("template", "")
        if not pattern or not template:
            continue
        full_url = f"{parsed.hostname or ''}{parsed.path}"
        m = re.search(pattern, full_url)
        if m:
            feed_url = _fill_template(template, m)
            if rsshub_base_url:
                feed_url = rsshub_base_url.rstrip("/") + feed_url
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    # 8) Fallback: unknown (caller may try probe_rss_feed next)
    return DetectionResult("unknown", error="No detector matched URL")


def _fill_template(template: str, match: re.Match) -> str:
    """Replace {1}, {2}, ... in template with match groups."""
    result = template
    for i, group in enumerate(match.groups(), start=1):
        result = result.replace(f"{{{i}}}", group)
    return result


async def probe_rss_feed(url: str, client: httpx.AsyncClient) -> DetectionResult:
    """HTTP-dependent fallback probe for RSS: try direct fetch + HTML autodiscovery."""
    try:
        response = await client.get(url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except httpx.HTTPError as e:
        return DetectionResult("unknown", error=f"HTTP error: {e}")
    except Exception as e:
        return DetectionResult("unknown", error=f"Fetch failed: {e}")

    ctype = (response.headers.get("content-type") or "").lower()
    body = response.text

    # Direct RSS: content-type indicates feed
    if any(t in ctype for t in ("application/rss", "application/atom", "text/xml", "application/xml")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # Body starts with <rss or <feed — another direct hint
    stripped = body.lstrip()[:200].lower()
    if stripped.startswith(("<?xml", "<rss", "<feed")):
        return DetectionResult("rss", {"feed_url": url, "name": url})

    # HTML autodiscovery: look for <link rel="alternate" type="application/rss+xml" href="...">
    m = re.search(
        r'<link[^>]+rel=["\']alternate["\'][^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]*>',
        body, flags=re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r'<link[^>]+type=["\']application/(?:rss|atom)\+xml["\'][^>]+rel=["\']alternate["\'][^>]*>',
            body, flags=re.IGNORECASE,
        )
    if m:
        link_tag = m.group(0)
        href_m = re.search(r'href=["\']([^"\']+)["\']', link_tag, flags=re.IGNORECASE)
        if href_m:
            feed_url = urljoin(url, href_m.group(1))
            return DetectionResult("rss", {"feed_url": feed_url, "name": url})

    return DetectionResult("unknown", error="No feed detected in page")


async def fetch_sample(
    detection: DetectionResult,
    client: httpx.AsyncClient,
    n: int = 5,
) -> list[dict]:
    """Fetch up to N most recent items from the detected source.

    Returns list of dicts: {title, url, published_at (str), snippet}.
    Empty list if fetch fails.
    """
    if detection.type == "rss":
        return await _sample_rss(detection.config["feed_url"], client, n)

    # For non-RSS types, v1 doesn't implement ad-hoc samplers (user would need
    # an RSSHub route for Western non-RSS sources, already handled upstream).
    if detection.type in ("youtube", "bilibili", "twitter", "reddit", "telegram"):
        logger.info(
            "Sample fetch skipped for type %s (no ad-hoc non-RSS sampler in v1)",
            detection.type,
        )
        return []

    return []


async def _sample_rss(feed_url: str, client: httpx.AsyncClient, n: int) -> list[dict]:
    """Fetch and parse RSS feed, returning up to N items."""
    try:
        response = await client.get(feed_url, follow_redirects=True, timeout=10.0)
        response.raise_for_status()
    except Exception as e:
        logger.warning("Sample RSS fetch failed for %s: %s", feed_url, e)
        return []

    feed = feedparser.parse(response.text)
    samples = []
    for entry in feed.entries[:n]:
        published = entry.get("published") or entry.get("updated") or ""
        snippet = entry.get("summary") or entry.get("description") or ""
        # Strip HTML tags crudely for LLM input
        snippet = re.sub(r"<[^>]+>", "", snippet)[:400]
        samples.append({
            "title": entry.get("title", "Untitled"),
            "url": entry.get("link", ""),
            "published_at": published,
            "snippet": snippet,
        })
    return samples


# ---------------------------------------------------------------------------
# LLM orchestration
# ---------------------------------------------------------------------------

DEFAULT_PROMPT_TEMPLATE = """你是订阅分析助手。判断以下源是否值得订阅到"AI + 时尚"聚合系统。

可选主题与 focus_area：
- ai: [开源模型, ComfyUI, 商用产品, Agent & Skills, 3D生成与重建, 训练与部署]
- fashion: [潮流, 时装, AI × 时尚]

样本（最近 {n} 条）：
{samples}

请以 JSON 返回（不要加 markdown 代码块）：
{{
  "theme": "ai" | "fashion" | "neither",
  "suggested_focus_areas": ["..."],
  "quality_score": 0-10,
  "verdict": "accept" | "reject" | "manual_review",
  "reasoning": "2-3 句说明"
}}

评分参考:
- 更新频率高、内容深度、原创性 → 加分
- 纯带货/营销、内容低质、与两个主题都无关 → 减分
- verdict: >=6 accept, <4 reject, 4-5.9 manual_review
"""


async def analyze_url(
    url: str,
    config: dict,
    client: httpx.AsyncClient,
) -> dict:
    """Orchestrate: detect → probe RSS if unknown → sample → LLM analyze.

    Returns a dict with keys: detected_type, sample, llm, normalized_config.
    """
    rsshub_cfg = config.get("rsshub", {})
    routes = rsshub_cfg.get("routes", [])
    rsshub_base = rsshub_cfg.get("base_url", "")

    detection = detect_url_type(url, rsshub_routes=routes, rsshub_base_url=rsshub_base)

    # If URL didn't match any specific pattern, try HTTP probing for RSS
    if detection.type == "unknown":
        detection = await probe_rss_feed(url, client)

    # If still unknown, return without LLM call
    if detection.type == "unknown":
        return {
            "detected_type": "unknown",
            "sample": [],
            "llm": {
                "theme": "neither",
                "suggested_focus_areas": [],
                "quality_score": 0,
                "verdict": "reject",
                "reasoning": detection.error or "无法识别此 URL 的订阅类型",
            },
            "normalized_config": {},
        }

    # Fetch sample
    sample = await fetch_sample(detection, client, n=5)

    # Build LLM prompt
    sa_cfg = config.get("subscribe_analyzer", {})
    # Merge: top-level llm provides defaults (api_key/base_url), subscribe_analyzer.llm
    # overrides only what it sets (e.g. model, temperature). Previously this was a
    # straight replace, which forced us to re-duplicate api_key/base_url under
    # subscribe_analyzer.llm and silently went stale on rotation (commit 716baeb).
    llm_cfg = {**config.get("llm", {}), **sa_cfg.get("llm", {})}
    prompt_template = sa_cfg.get("prompt_template", DEFAULT_PROMPT_TEMPLATE)
    prompt = _build_prompt(prompt_template, sample)

    # LLM analyze with one retry on failure
    llm_result = None
    for attempt in (1, 2):
        try:
            llm_result = await _call_llm(prompt, llm_cfg, client)
            break
        except Exception as e:
            logger.warning("LLM subscription analysis attempt %d failed: %s", attempt, e)

    if llm_result is None:
        llm_result = {
            "theme": "neither",
            "suggested_focus_areas": [],
            "quality_score": 0,
            "verdict": "manual_review",
            "reasoning": "AI 分析暂时不可用，请根据样本自行判断 (LLM failed)",
        }

    return {
        "detected_type": detection.type,
        "sample": sample,
        "llm": llm_result,
        "normalized_config": detection.config,
    }


def _build_prompt(template: str, samples: list[dict]) -> str:
    """Fill prompt template using .replace() to avoid breaking on JSON { in template."""
    if not samples:
        sample_text = "(无法抓取样本，请仅基于 URL 本身判断)"
    else:
        lines = []
        for i, s in enumerate(samples, 1):
            lines.append(f"{i}. {s['title']}\n   {s.get('snippet', '')[:200]}")
        sample_text = "\n".join(lines)
    return template.replace("{n}", str(len(samples))).replace("{samples}", sample_text)


async def _call_llm(prompt: str, llm_cfg: dict, client: httpx.AsyncClient) -> dict:
    """POST to OpenAI-compatible /chat/completions and parse JSON response."""
    api_key = llm_cfg.get("api_key", "")
    base_url = llm_cfg.get("base_url", "https://api.openai.com/v1")
    model = llm_cfg.get("model", "gpt-4o-mini")
    temperature = llm_cfg.get("temperature", 0.2)

    if not api_key:
        raise ValueError("LLM api_key not configured for subscribe_analyzer")

    resp = await client.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a subscription analysis assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": 512,
        },
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    text = data["choices"][0]["message"]["content"].strip()

    # Strip code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1]) if len(lines) >= 3 else text.strip("`")

    return json.loads(text)
