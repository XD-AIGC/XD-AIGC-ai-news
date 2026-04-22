"""AI News Aggregator - CLI entry point."""

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from collectors.base import ContentItem, SourceType
from collectors.bilibili_collector import BilibiliCollector
from collectors.github_collector import GitHubCollector
from collectors.hackernews_collector import HackerNewsCollector
from collectors.hf_papers_collector import HFPapersCollector
from collectors.reddit_collector import RedditCollector
from collectors.rss_collector import RSSCollector
from collectors.telegram_collector import TelegramCollector
from collectors.twitter_collector import TwitterCollector
from collectors.twitter_trending_collector import TwitterTrendingCollector
from collectors.youtube_collector import YouTubeCollector
from outputs.feishu_bot import FeishuBot
from outputs.github_pages_writer import GitHubPagesWriter
from outputs.markdown_writer import MarkdownWriter
from outputs.notion_writer import NotionWriter
from processor.classifier import KeywordClassifier
from processor.comic_generator import ComicGenerator
from processor.dedup import deduplicate, deduplicate_semantic
from processor.scorer import AIScorer
from processor.weekly_digest import generate_weekly_digest
from storage.config_loader import load_config, load_themes
from storage.database import NewsDatabase
from storage.user_sources import list_by_status

logger = logging.getLogger(__name__)

TEST_URL = "https://huggingface.co"


def select_proxy(proxy_cfg: dict) -> str | None:
    """Try each proxy URL in order, return the first reachable one."""
    raw = proxy_cfg.get("urls", [])
    # Support comma-separated string from env var or list from yaml
    if isinstance(raw, str):
        urls = [u.strip() for u in raw.split(",") if u.strip()]
    else:
        urls = raw
    if not urls:
        return None

    import socket
    from urllib.parse import urlparse

    for url in urls:
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 18888
        try:
            sock = socket.create_connection((host, port), timeout=3)
            sock.close()
            logger.info("Proxy reachable: %s", url)
            return url
        except (OSError, socket.timeout):
            logger.warning("Proxy unreachable: %s", url)
            continue

    logger.warning("All proxies unreachable, falling back to direct connection")
    return None


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _merge_user_sources_into_config(config: dict, db) -> dict:
    """Merge active user_sources into a mutable copy of config['sources'].

    Each UserSource has source_type + normalized_config (JSON).
    We append its normalized_config to the matching collector's source list.
    Returns modified config.
    """
    active = list_by_status(db, "active")
    if not active:
        return config

    sources = config.setdefault("sources", {})
    count_added = 0

    for src in active:
        try:
            cfg = json.loads(src.normalized_config or "{}")
        except json.JSONDecodeError:
            logger.warning("Skipping user_source #%d: malformed config", src.id)
            continue

        if src.source_type == "rss":
            rss = sources.setdefault("rss", {"enabled": True, "feeds": []})
            rss["enabled"] = True
            feed_url = cfg.get("feed_url") or cfg.get("url") or src.url
            feed = {**cfg, "url": feed_url, "theme": src.theme, "name": src.name or cfg.get("name", src.url)}
            rss.setdefault("feeds", []).append(feed)
            count_added += 1

        elif src.source_type == "youtube":
            yt = sources.setdefault("youtube", {"enabled": True, "channels": []})
            yt["enabled"] = True
            channel = {**cfg, "theme": src.theme, "name": src.name}
            yt.setdefault("channels", []).append(channel)
            count_added += 1

        elif src.source_type == "bilibili":
            bili = sources.setdefault("bilibili", {"enabled": True, "users": []})
            bili["enabled"] = True
            user = {**cfg, "theme": src.theme, "name": src.name}
            bili.setdefault("users", []).append(user)
            count_added += 1

        elif src.source_type == "twitter":
            tw = sources.setdefault("twitter", {"enabled": True, "users": []})
            tw["enabled"] = True
            user = {**cfg, "theme": src.theme, "name": src.name}
            tw.setdefault("users", []).append(user)
            count_added += 1

        elif src.source_type == "reddit":
            rd = sources.setdefault("reddit", {"enabled": True, "subreddits": []})
            rd["enabled"] = True
            sub = {**cfg, "theme": src.theme}
            rd.setdefault("subreddits", []).append(sub)
            count_added += 1

        elif src.source_type == "telegram":
            tg = sources.setdefault("telegram", {"enabled": True, "channels": []})
            tg["enabled"] = True
            ch = {**cfg, "theme": src.theme, "name": src.name}
            tg.setdefault("channels", []).append(ch)
            count_added += 1

        else:
            logger.warning("Unknown source_type '%s' for user_source #%d", src.source_type, src.id)

    if count_added:
        logger.info("Merged %d dynamic user_sources into config", count_added)

    return config


def build_collectors(
    config: dict, client: httpx.AsyncClient, proxy_url: str | None = None
) -> list[tuple[str, object]]:
    """Create collector instances based on config."""
    collectors = []
    sources = config.get("sources", {})

    if sources.get("rss", {}).get("enabled"):
        feeds = sources["rss"].get("feeds", [])
        if feeds:
            collectors.append(("RSS", RSSCollector(feeds, client)))

    if sources.get("github", {}).get("enabled"):
        collectors.append(("GitHub", GitHubCollector(sources["github"], client)))

    if sources.get("hackernews", {}).get("enabled"):
        collectors.append(
            ("HackerNews", HackerNewsCollector(sources["hackernews"], client))
        )

    if sources.get("youtube", {}).get("enabled"):
        collectors.append(
            ("YouTube", YouTubeCollector(sources["youtube"], client))
        )

    if sources.get("bilibili", {}).get("enabled"):
        bili_cfg = sources["bilibili"]
        bili_cfg["cookie"] = os.getenv("BILIBILI_COOKIE", bili_cfg.get("cookie", ""))
        collectors.append(("Bilibili", BilibiliCollector(bili_cfg, client)))

    if sources.get("twitter", {}).get("enabled"):
        tw_cfg = sources["twitter"]
        tw_cfg["auth_token"] = os.getenv("TWITTER_AUTH_TOKEN", tw_cfg.get("auth_token", ""))
        tw_cfg["proxy"] = proxy_url or ""
        collectors.append(("Twitter", TwitterCollector(tw_cfg, client)))

    if sources.get("twitter_trending", {}).get("enabled"):
        tt_cfg = sources["twitter_trending"]
        tt_cfg["proxy"] = proxy_url or ""
        tt_cfg["auth_token"] = os.getenv("TWITTER_AUTH_TOKEN", tt_cfg.get("auth_token", ""))
        tt_cfg["ct0"] = os.getenv("TWITTER_CT0", tt_cfg.get("ct0", ""))
        collectors.append(
            ("TwitterTrending", TwitterTrendingCollector(tt_cfg, client))
        )

    if sources.get("reddit", {}).get("enabled"):
        collectors.append(
            ("Reddit", RedditCollector(sources["reddit"], client))
        )

    if sources.get("telegram", {}).get("enabled"):
        collectors.append(
            ("Telegram", TelegramCollector(sources["telegram"], client))
        )

    if sources.get("hf_papers", {}).get("enabled"):
        collectors.append(
            ("HFPapers", HFPapersCollector(sources["hf_papers"], client))
        )

    return collectors


async def collect_all(
    collectors: list[tuple[str, object]], since: datetime
) -> list[ContentItem]:
    """Run all collectors concurrently."""
    tasks = []
    for name, collector in collectors:
        tasks.append(collector.fetch(since))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_items: list[ContentItem] = []
    for (name, _), result in zip(collectors, results):
        if isinstance(result, Exception):
            logger.error("Collector [%s] failed: %s", name, result)
        else:
            logger.info("Collector [%s]: %d items", name, len(result))
            all_items.extend(result)

    return all_items


async def run(args: argparse.Namespace) -> None:
    load_dotenv()
    config = load_config(args.config)

    proxy_cfg = config.get("proxy", {})
    proxy_url = select_proxy(proxy_cfg) if not args.no_proxy else None

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        # Merge dynamic sources from DB into config before building collectors
        config = _merge_user_sources_into_config(config, db)

        since = datetime.now(timezone.utc) - timedelta(days=args.days)

        client_kwargs: dict = {
            "timeout": httpx.Timeout(30.0),
            "follow_redirects": True,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
            logger.info("Using proxy: %s", proxy_url)
        else:
            logger.info("Direct connection (no proxy)")

        async with httpx.AsyncClient(**client_kwargs) as client:
            collectors = build_collectors(config, client, proxy_url)

            if not collectors:
                logger.warning("No collectors enabled in config")
                return

            logger.info(
                "Starting collection (%d sources, since %s)...",
                len(collectors),
                since.strftime("%Y-%m-%d"),
            )

            items = await collect_all(collectors, since)
            logger.info("Total collected: %d items", len(items))

            # Dedup
            items = deduplicate(items)
            logger.info("After dedup: %d items", len(items))

            # Keyword pre-classification
            themes = load_themes(config)
            if any(themes.values()):
                classifier = KeywordClassifier(themes)
                items = classifier.classify_items(items)

            # Save to database
            new_count = db.save_items(items)
            logger.info("New items saved: %d (duplicates skipped: %d)",
                        new_count, len(items) - new_count)

        # AI scoring + classification + summarization
        llm_cfg = config.get("llm", {})
        if llm_cfg.get("api_key") and not args.skip_ai:
            scorer_cfg = {**llm_cfg}
            if proxy_url:
                scorer_cfg["proxy"] = proxy_url
            scorer = AIScorer(scorer_cfg)

            today = datetime.now().strftime("%Y-%m-%d")
            unscored = [
                item for item in db.get_items_by_date(today)
                if item.ai_score is None
            ]

            # Pre-filter: only score items matching focus areas
            if unscored and any(themes.values()):
                pre_filter = KeywordClassifier(themes)
                before = len(unscored)
                unscored = pre_filter.filter_relevant(unscored)
                logger.info(
                    "Pre-filter for AI scoring: %d -> %d items",
                    before, len(unscored),
                )

            if unscored:
                logger.info("AI scoring %d unscored items...", len(unscored))
                await scorer.process_items(unscored)
                db.update_ai_results(unscored)
                logger.info("AI scoring complete")

        # Output
        output_cfg = config.get("output", {})
        today = datetime.now().strftime("%Y-%m-%d")
        all_today = db.get_items_by_date(today)

        # Cross-source semantic dedup (after AI scoring)
        all_today = deduplicate_semantic(all_today)
        logger.info("After semantic dedup: %d items", len(all_today))

        if output_cfg.get("markdown", {}).get("enabled"):
            try:
                md_dir = output_cfg["markdown"].get("output_dir", "./reports/markdown")
                writer = MarkdownWriter(md_dir)
                filepath = writer.write(all_today, today)
                logger.info("Markdown report: %s (%d items)", filepath, len(all_today))
            except Exception as e:
                logger.error("Markdown output failed: %s", e)

        # GitHub Pages static output
        ghpages_cfg = output_cfg.get("github_pages", {})
        if ghpages_cfg.get("enabled"):
            try:
                gh_dir = ghpages_cfg.get("output_dir", "./docs")
                gh_writer = GitHubPagesWriter(gh_dir)
                gh_writer.write(all_today, today)
            except Exception as e:
                logger.error("GitHub Pages output failed: %s", e)

        # Notion output
        notion_cfg = output_cfg.get("notion", {})
        if notion_cfg.get("enabled") and notion_cfg.get("api_key"):
            try:
                notion_proxy = proxy_url if (proxy_url) else None
                notion = NotionWriter(
                    notion_cfg["api_key"], notion_cfg["database_id"], proxy=notion_proxy
                )
                await notion.write_items(all_today)
            except Exception as e:
                logger.error("Notion output failed: %s", e)

        # Feishu bot output
        feishu_cfg = output_cfg.get("feishu", {})
        if feishu_cfg.get("enabled") and feishu_cfg.get("webhook_url"):
            try:
                feishu_proxy = proxy_url if (proxy_url) else None
                bot = FeishuBot(feishu_cfg["webhook_url"], proxy=feishu_proxy)
                await bot.send_daily_digest(all_today, today)
            except Exception as e:
                logger.error("Feishu output failed: %s", e)

    finally:
        db.close()


async def backfill_notion(args: argparse.Namespace) -> None:
    """Backfill AI results to existing Notion pages that are missing them."""
    load_dotenv()
    config = load_config(args.config)

    proxy_cfg = config.get("proxy", {})
    proxy_url = select_proxy(proxy_cfg) if not args.no_proxy else None

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        notion_cfg = config.get("output", {}).get("notion", {})
        if not notion_cfg.get("api_key"):
            logger.error("Notion API key not configured")
            return

        notion_proxy = proxy_url if (proxy_url) else None
        notion = NotionWriter(
            notion_cfg["api_key"], notion_cfg["database_id"], proxy=notion_proxy
        )

        # Get all items with AI scores from database
        all_items = db.get_recent_items(limit=10000, min_score=0.0)
        logger.info("Found %d items with AI scores in database", len(all_items))

        updated = await notion.backfill_ai_results(all_items)
        logger.info("Backfill complete: %d pages updated", updated)
    finally:
        db.close()


async def run_weekly(args: argparse.Namespace) -> None:
    """Generate weekly comic digest."""
    load_dotenv()
    config = load_config(args.config)

    proxy_cfg = config.get("proxy", {})
    proxy_url = select_proxy(proxy_cfg) if not args.no_proxy else None

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        llm_cfg = config.get("llm", {})
        weekly_cfg = config.get("weekly", {})
        ghpages_cfg = config.get("output", {}).get("github_pages", {})
        output_dir = ghpages_cfg.get("output_dir", "./docs")

        comic_config = {
            "llm_model": llm_cfg.get("model", "gemini-2.5-flash"),
            "image_model": weekly_cfg.get("image_model", "nano-banana-pro-preview"),
            "api_key": llm_cfg.get("api_key", ""),
            "base_url": llm_cfg.get("base_url", ""),
            "proxy": proxy_url,
            "max_concurrent_images": weekly_cfg.get("max_concurrent_images", 3),
        }

        comic_gen = ComicGenerator(comic_config)

        ref_date = None
        if args.week_date:
            ref_date = datetime.strptime(args.week_date, "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )

        digest = await generate_weekly_digest(
            db, comic_gen, output_dir, ref_date=ref_date
        )

        if digest:
            logger.info("Weekly digest generated: %s", digest["week"])
        else:
            logger.warning("Weekly digest skipped (no data)")
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI News Aggregator")
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Collect news from the last N days (default: 1)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--no-proxy",
        action="store_true",
        help="Disable proxy (for local development)",
    )
    parser.add_argument(
        "--skip-ai",
        action="store_true",
        help="Skip AI scoring (collect only)",
    )
    parser.add_argument(
        "--backfill-notion",
        action="store_true",
        help="Backfill AI scores/summaries to existing Notion pages",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start web dashboard server instead of collecting",
    )
    parser.add_argument(
        "--weekly",
        action="store_true",
        help="Generate weekly comic digest",
    )
    parser.add_argument(
        "--week-date",
        type=str,
        default=None,
        help="Reference date for weekly digest (YYYY-MM-DD), generates the week containing this date",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8800,
        help="Web server port (default: 8800)",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.serve:
        import uvicorn
        load_dotenv()
        config = load_config(args.config)
        db_path = config.get("database", {}).get("path", "./data/news.db")
        os.environ["NEWS_DB_PATH"] = db_path
        web_cfg = config.get("output", {}).get("web", {})
        host = web_cfg.get("host", "0.0.0.0")
        port = args.port or web_cfg.get("port", 8800)
        logger.info("Starting web dashboard at http://%s:%d", host, port)
        uvicorn.run("web.app:app", host=host, port=port, reload=False)
    elif args.weekly:
        asyncio.run(run_weekly(args))
    elif args.backfill_notion:
        asyncio.run(backfill_notion(args))
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
