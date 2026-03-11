"""AI News Aggregator - CLI entry point."""

import argparse
import asyncio
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import yaml
from dotenv import load_dotenv

from collectors.base import ContentItem, SourceType
from collectors.bilibili_collector import BilibiliCollector
from collectors.github_collector import GitHubCollector
from collectors.hackernews_collector import HackerNewsCollector
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
from processor.dedup import deduplicate
from processor.scorer import AIScorer
from storage.database import NewsDatabase

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def load_config(config_path: str = "config.yaml") -> dict:
    """Load config and resolve ${ENV_VAR} references."""
    with open(config_path, "r", encoding="utf-8") as f:
        raw = f.read()

    def replace_env(match: re.Match) -> str:
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    resolved = re.sub(r"\$\{(\w+)\}", replace_env, raw)
    return yaml.safe_load(resolved)


def build_collectors(
    config: dict, client: httpx.AsyncClient
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
        tw_cfg["proxy"] = config.get("proxy", {}).get("http", "")
        collectors.append(("Twitter", TwitterCollector(tw_cfg, client)))

    if sources.get("twitter_trending", {}).get("enabled"):
        tt_cfg = sources["twitter_trending"]
        tt_cfg["proxy"] = config.get("proxy", {}).get("http", "")
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
    proxy_url = proxy_cfg.get("http")

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        since = datetime.now(timezone.utc) - timedelta(days=args.days)

        client_kwargs: dict = {
            "timeout": httpx.Timeout(30.0),
            "follow_redirects": True,
        }
        if proxy_url and not args.no_proxy:
            client_kwargs["proxy"] = proxy_url
            logger.info("Using proxy: %s", proxy_url)
        else:
            logger.info("Direct connection (no proxy)")

        async with httpx.AsyncClient(**client_kwargs) as client:
            collectors = build_collectors(config, client)

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
            focus_areas = config.get("focus_areas", [])
            if focus_areas:
                classifier = KeywordClassifier(focus_areas)
                items = classifier.classify_items(items)

            # Save to database
            new_count = db.save_items(items)
            logger.info("New items saved: %d (duplicates skipped: %d)",
                        new_count, len(items) - new_count)

        # AI scoring + classification + summarization
        llm_cfg = config.get("llm", {})
        if llm_cfg.get("api_key") and not args.skip_ai:
            scorer_cfg = {**llm_cfg}
            if proxy_url and not args.no_proxy:
                scorer_cfg["proxy"] = proxy_url
            scorer = AIScorer(scorer_cfg)

            today = datetime.now().strftime("%Y-%m-%d")
            unscored = [
                item for item in db.get_items_by_date(today)
                if item.ai_score is None
            ]

            if unscored:
                logger.info("AI scoring %d unscored items...", len(unscored))
                await scorer.process_items(unscored)
                db.update_ai_results(unscored)
                logger.info("AI scoring complete")

        # Output
        output_cfg = config.get("output", {})
        today = datetime.now().strftime("%Y-%m-%d")
        all_today = db.get_items_by_date(today)

        if output_cfg.get("markdown", {}).get("enabled"):
            md_dir = output_cfg["markdown"].get("output_dir", "./reports/markdown")
            writer = MarkdownWriter(md_dir)
            filepath = writer.write(all_today, today)
            logger.info("Markdown report: %s (%d items)", filepath, len(all_today))

        # GitHub Pages static output
        ghpages_cfg = output_cfg.get("github_pages", {})
        if ghpages_cfg.get("enabled"):
            gh_dir = ghpages_cfg.get("output_dir", "./docs")
            gh_writer = GitHubPagesWriter(gh_dir)
            gh_writer.write(all_today, today)

        # Notion output
        notion_cfg = output_cfg.get("notion", {})
        if notion_cfg.get("enabled") and notion_cfg.get("api_key"):
            notion_proxy = proxy_url if (proxy_url and not args.no_proxy) else None
            notion = NotionWriter(
                notion_cfg["api_key"], notion_cfg["database_id"], proxy=notion_proxy
            )
            await notion.write_items(all_today)

        # Feishu bot output
        feishu_cfg = output_cfg.get("feishu", {})
        if feishu_cfg.get("enabled") and feishu_cfg.get("webhook_url"):
            feishu_proxy = proxy_url if (proxy_url and not args.no_proxy) else None
            bot = FeishuBot(feishu_cfg["webhook_url"], proxy=feishu_proxy)
            await bot.send_daily_digest(all_today, today)

    finally:
        db.close()


async def backfill_notion(args: argparse.Namespace) -> None:
    """Backfill AI results to existing Notion pages that are missing them."""
    load_dotenv()
    config = load_config(args.config)

    proxy_cfg = config.get("proxy", {})
    proxy_url = proxy_cfg.get("http")

    db = NewsDatabase(config.get("database", {}).get("path", "./data/news.db"))
    db.connect()

    try:
        notion_cfg = config.get("output", {}).get("notion", {})
        if not notion_cfg.get("api_key"):
            logger.error("Notion API key not configured")
            return

        notion_proxy = proxy_url if (proxy_url and not args.no_proxy) else None
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
    elif args.backfill_notion:
        asyncio.run(backfill_notion(args))
    else:
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
