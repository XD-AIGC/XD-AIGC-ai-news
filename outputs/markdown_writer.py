"""Markdown daily report writer."""

import logging
from datetime import datetime
from pathlib import Path

from collectors.base import ContentItem, SourceType

logger = logging.getLogger(__name__)

SOURCE_LABELS = {
    SourceType.RSS: "RSS Feeds",
    SourceType.YOUTUBE: "YouTube",
    SourceType.BILIBILI: "Bilibili",
    SourceType.TWITTER: "Twitter / X",
    SourceType.GITHUB: "GitHub",
    SourceType.HACKERNEWS: "Hacker News",
    SourceType.REDDIT: "Reddit",
    SourceType.TELEGRAM: "Telegram",
    SourceType.MANUAL: "Manual",
}


class MarkdownWriter:
    def __init__(self, output_dir: str = "./reports/markdown"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(self, items: list[ContentItem], date: str | None = None) -> Path:
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        grouped: dict[SourceType, list[ContentItem]] = {}
        for item in items:
            grouped.setdefault(item.source_type, []).append(item)

        lines: list[str] = []
        lines.append(f"# AI 资讯日报 - {date}\n")
        lines.append(f"> 共 {len(items)} 条资讯\n")

        for source_type in SourceType:
            source_items = grouped.get(source_type, [])
            if not source_items:
                continue

            label = SOURCE_LABELS.get(source_type, source_type.value)
            lines.append(f"\n## {label} ({len(source_items)} 条)\n")

            for item in source_items:
                lines.append(f"### {item.title}\n")
                lines.append(f"- **链接**: {item.url}")
                if item.author:
                    lines.append(f"- **作者**: {item.author}")
                if item.published_at:
                    lines.append(
                        f"- **发布时间**: {item.published_at.strftime('%Y-%m-%d %H:%M')}"
                    )
                if item.ai_score is not None:
                    lines.append(f"- **AI 评分**: {item.ai_score}/10")
                if item.metadata.get("trending"):
                    likes = item.metadata.get("likes", 0)
                    retweets = item.metadata.get("retweets", 0)
                    lines.append(f"- **热度**: {likes} likes / {retweets} retweets")
                if item.metadata.get("view_count"):
                    vc = item.metadata["view_count"]
                    lines.append(f"- **播放量**: {vc:,}")
                if item.metadata.get("subtype") == "explosive":
                    stars = item.metadata.get("stars", 0)
                    spd = item.metadata.get("stars_per_day", 0)
                    age = item.metadata.get("age_days", 0)
                    lines.append(f"- **增长**: {stars:,} stars / {age}天 (+{spd:.0f}/天)")
                if item.ai_summary:
                    lines.append(f"\n{item.ai_summary}")
                elif item.content:
                    preview = item.content[:300].replace("\n", " ")
                    if len(item.content) > 300:
                        preview += "..."
                    lines.append(f"\n> {preview}")
                lines.append("")

        filepath = self.output_dir / f"{date}.md"
        filepath.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Markdown report saved: %s", filepath)
        return filepath
