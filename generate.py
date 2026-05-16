import os
import sys
sys.path.insert(0, '/home/shawnz/daily-llama')
os.chdir('/home/shawnz/daily-llama')

import json
import logging
from datetime import datetime, timedelta, timezone

from utils.paths import SITE_DATA, FEED_PATH, SITE_NEW, SITE_LIVE, ARCHIVE_DIR, LOGS_DIR
from collectors.blogwatcher_collector import collect_articles, collect_youtube_videos
from collectors.kanban_collector import collect_task_reports
from collectors.health_collector import collect_health
from collectors.thumbnail_collector import batch_generate, THUMB_DIR
from generators.html_generator import generate_html
from scoring.scorer import score_articles, compute_empty_day
from utils.atomic_writer import atomic_swap

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the site generator.

    1. Collects data from all sources
    2. Scores articles
    3. Generates HTML
    4. Atomically swaps directories
    """
    try:
        now = datetime.now(timezone.utc)

        # Collect data
        articles = collect_articles()
        yt_videos = collect_youtube_videos()

        # Merge YT videos into articles (deduplicate by URL, YT wins)
        seen_urls = {a["url"] for a in articles}
        for yt in yt_videos:
            if yt["url"] not in seen_urls:
                articles.append(yt)
                seen_urls.add(yt["url"])

        task_reports = collect_task_reports()  # Already returns dict with completed/blocked/running
        health = collect_health()

        # Score articles
        scored_articles = score_articles(articles, now=now)

        # Collect all videos (from regular + named channels) sorted by score
        all_video_results = [s for s in scored_articles["all_scored"] if s["is_video"]]
        all_video_results.sort(key=lambda x: x["score"], reverse=True)

        # Classify videos for the carousel: use scored results
        featured_video = scored_articles.get("featured_video")
        carousel_videos = scored_articles.get("runner_ups", [])[:]
        # If featured exists, it's the top; add it as the first carousel item
        # Runner-ups make up the rest of the carousel
        # If no featured but we have videos, the top-scored video becomes featured
        if not featured_video and all_video_results:
            featured_video = all_video_results[0]

        # Build feed data with video carousel
        feed_data = {
            "generated_at": now.isoformat(),
            "generation_status": "ok",
            "last_successful_run": now.isoformat(),
            "failed_steps": [],
            "featured_video": featured_video,
            "runner_ups": carousel_videos,
            "news_cards": scored_articles.get("news_cards", []),
            "video_carousel": all_video_results,  # All videos for the cover-flow carousel
            "task_reports": task_reports,
            "stack_health": health,
            "novel_findings": scored_articles.get("novel_findings", []),
            "archive_months": _list_archive_months(),
        }

        # Generate thumbnails for news cards
        logging.info("Generating thumbnails for news cards...")
        feed_data["news_cards"] = batch_generate(feed_data.get("news_cards", []))

        # Empty-day prospecting: if 0 news cards, try carryover from yesterday
        if len(feed_data.get("news_cards", [])) == 0:
            yesterday = now - timedelta(days=1)
            yesterday_str = yesterday.strftime("%Y-%m-%d")
            yesterday_feed_path = os.path.join(ARCHIVE_DIR, yesterday_str + ".json")
            compute_empty_day(feed_data, yesterday_feed_path)

        # Write feed data to site-data location
        with open(FEED_PATH, "w") as f:
            json.dump(feed_data, f, indent=2)

        # Archive the daily feed for the archive page (monthly format)
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
        month_str = now.strftime("%Y-%m")
        archive_path = os.path.join(ARCHIVE_DIR, f"{month_str}.json")
        with open(archive_path, "w") as f:
            json.dump(feed_data, f, indent=2)

        # Regenerate archive index.json (list of available months)
        months = sorted(
            fname[:-5] for fname in os.listdir(ARCHIVE_DIR)
            if fname.endswith(".json") and len(fname) == 12 and fname != "index.json"
        )
        index_path = os.path.join(ARCHIVE_DIR, "index.json")
        with open(index_path, "w") as f:
            json.dump(months[-12:], f)

        # Generate HTML into SITE_NEW
        generate_html(feed_data, SITE_NEW)

        # Atomic swap: rename SITE_LIVE -> SITE_OLD, SITE_NEW -> SITE_LIVE
        atomic_swap()

        # Ensure archive symlink survives the swap
        archive_link = os.path.join(SITE_LIVE, "archive")
        if not os.path.islink(archive_link):
            if os.path.exists(archive_link):
                os.remove(archive_link)
            os.symlink(ARCHIVE_DIR, archive_link)

        # Ensure thumbnails symlink
        thumb_link = os.path.join(SITE_LIVE, "thumbnails")
        if not os.path.islink(thumb_link):
            if os.path.exists(thumb_link):
                os.remove(thumb_link)
            os.symlink(THUMB_DIR, thumb_link)

        logger.info("Site generation completed successfully")
    except Exception as e:
        logger.error(f"Site generation failed: {e}", exc_info=True)
        # Write error log
        error_log = {
            "status": "error",
            "message": str(e),
            "timestamp": now.isoformat() if 'now' in dir() else datetime.now(timezone.utc).isoformat(),
            "failed_steps": ["generate:main"],
        }
        os.makedirs(LOGS_DIR, exist_ok=True)
        with open(os.path.join(LOGS_DIR, "last_error.json"), "w") as f:
            json.dump(error_log, f, indent=2)
        raise


def _list_archive_months():
    """List available archive month slugs from the archive directory."""
    if not os.path.isdir(ARCHIVE_DIR):
        return []
    months = []
    for fname in sorted(os.listdir(ARCHIVE_DIR)):
        if fname.endswith(".json") and len(fname) == 12:  # e.g. "2026-05.json"
            months.append(fname[:-5])
    return months[-12:]  # Last 12 months max


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
