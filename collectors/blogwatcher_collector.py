"""Blogwatcher collector for The Daily Llama.

Collects articles from the blogwatcher SQLite database and
extracts YouTube videos from named channels regardless of age.
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta, timezone
import logging

from utils.paths import BLOGWATCHER_DB, SITE_DIR

logger = logging.getLogger(__name__)

# How far back to look for articles (hours).
LOOKBACK_HOURS = 24

# Named YouTube channels — always include their latest videos.
NAMED_YT_CHANNELS = ["David Ondrej", "Codacus", "Alex Finn", "Fireship", "Two Minute Papers", "Matt Wolfe"]
NAMED_YT_LOOKBACK_DAYS = 7  # Look back 7 days for named channels
MIN_YT_VIDEOS_PER_CHANNEL = 1  # Fetch the latest 1 per named channel
OTHER_YT_VIDEOS_MIN = 5  # Minimum "other" YouTube finds from any blog source
OTHER_YT_LOOKBACK_DAYS = 14  # Wider net for non-named YouTube finds


def collect_articles():
    """Return a list of article dicts discovered in the past 24 hours.

    Each dict has:
        title, url, published_date (ISO str or None),
        discovered_date (ISO str),
        blog_name, blog_url, categories (list of str)

    Uses discovered_date for scoring recency when the RSS pubDate
    is missing or too old to avoid all articles scoring 0.0.

    Returns an empty list when no articles are found or the DB is
    unavailable.
    """
    if not os.path.isfile(BLOGWATCHER_DB):
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).isoformat()

    conn = sqlite3.connect(BLOGWATCHER_DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT a.title, a.url, a.published_date, a.discovered_date, a.categories,
                   b.name AS blog_name, b.url AS blog_url
            FROM articles a
            JOIN blogs b ON a.blog_id = b.id
            WHERE a.discovered_date >= ?
            ORDER BY a.discovered_date DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    articles = []
    for r in rows:
        cats = []
        if r["categories"]:
            raw_cats = r["categories"]
            # Try JSON parse first (blogwatcher-cli stores as JSON array)
            try:
                parsed = json.loads(raw_cats)
                if isinstance(parsed, list):
                    cats = [str(c).strip() for c in parsed if str(c).strip()]
            except (json.JSONDecodeError, TypeError):
                # Fall back to comma-split
                cats = [c.strip() for c in raw_cats.split(",") if c.strip()]

        # Use discovered_date for scoring when RSS pubDate is missing
        rss_date = r["published_date"]
        discovered = r["discovered_date"]

        # If RSS pubDate is missing, fall back to discovered_date
        pub_date = rss_date if rss_date else discovered

        articles.append(
            {
                "title": r["title"],
                "url": r["url"],
                "published_date": pub_date,
                "discovered_date": discovered,
                "blog_name": r["blog_name"],
                "blog_url": r["blog_url"],
                "categories": cats,
            }
        )
    return articles


class BlogwatcherCollector:
    def __init__(self):
        self.db_path = BLOGWATCHER_DB
        self.site_dir = SITE_DIR
        self.feed_path = os.path.join(self.site_dir, "feed.json")
        self.new_sources_path = os.path.join(self.site_dir, "new_sources.json")
        self.feed_data = {}
        self.new_sources = {}

    def collect(self):
        self._load_feed()
        self._collect_new_sources()
        self._write_feed()

    def _load_feed(self):
        try:
            with open(self.feed_path, "r") as f:
                self.feed_data = json.load(f)
        except FileNotFoundError:
            self.feed_data = {
                "featured_video": None,
                "runner_ups": [],
                "news": [],
                "task_reports": [],
                "health": []
            }
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in feed file: {e}")

    def _collect_new_sources(self):
        try:
            with open(self.new_sources_path, "r") as f:
                sources = json.load(f)

            for category, category_list in sources.items():
                for src in category_list:
                    if category == "youtube_channels":
                        self.add_runner_up(src)
                    elif category == "hermes_agent":
                        self.add_news_item(src)
        except FileNotFoundError:
            logger.warning(f"New sources file not found: {self.new_sources_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in new sources file: {e}")

    def _write_feed(self):
        with open(self.feed_path, "w") as f:
            json.dump(self.feed_data, f, indent=2)

    def add_featured_video(self, video):
        self.feed_data["featured_video"] = video

    def add_runner_up(self, runner_up):
        self.feed_data["runner_ups"].append(runner_up)

    def add_news_item(self, news_item):
        self.feed_data["news"].append(news_item)

    def add_task_report(self, task_report):
        self.feed_data["task_reports"].append(task_report)

    def add_health_item(self, health_item):
        self.feed_data["health"].append(health_item)

    def get_feed_data(self):
        return self.feed_data

    def get_new_sources(self):
        return self.new_sources


def collect_youtube_videos():
    """Fetch latest YouTube videos from named channels, ignoring the 24-hr lookback.

    Returns a list of article dicts (same shape as collect_articles).
    Always returns at least MIN_YT_VIDEOS_PER_CHANNEL per named channel
    within NAMED_YT_LOOKBACK_DAYS.
    """
    if not os.path.isfile(BLOGWATCHER_DB):
        return []

    cutoff = (datetime.now(timezone.utc) - timedelta(days=NAMED_YT_LOOKBACK_DAYS)).isoformat()

    conn = sqlite3.connect(BLOGWATCHER_DB)
    conn.row_factory = sqlite3.Row
    results = []
    seen_urls = set()
    try:
        # 1. Latest video from each named channel
        for channel in NAMED_YT_CHANNELS:
            rows = conn.execute(
                """
                SELECT a.title, a.url, a.published_date, a.discovered_date, a.categories,
                       b.name AS blog_name, b.url AS blog_url
                FROM articles a
                JOIN blogs b ON a.blog_id = b.id
                WHERE b.name = ?
                  AND a.discovered_date >= ?
                  AND (a.url LIKE '%youtube.com/watch%' OR a.url LIKE '%youtu.be/%')
                ORDER BY a.discovered_date DESC
                LIMIT ?
                """,
                (channel, cutoff, MIN_YT_VIDEOS_PER_CHANNEL),
            ).fetchall()

            for r in rows:
                if r["url"] in seen_urls:
                    continue
                seen_urls.add(r["url"])
                cats = _parse_categories(r["categories"])
                rss_date = r["published_date"]
                discovered = r["discovered_date"]
                pub_date = rss_date if rss_date else discovered
                results.append({
                    "title": r["title"],
                    "url": r["url"],
                    "published_date": pub_date,
                    "discovered_date": discovered,
                    "blog_name": r["blog_name"],
                    "blog_url": r["blog_url"],
                    "categories": cats,
                })

        # 2. Other YouTube finds from ANY blog (not named channels) — 14-day lookback
        other_cutoff = (datetime.now(timezone.utc) - timedelta(days=OTHER_YT_LOOKBACK_DAYS)).isoformat()
        remaining = max(OTHER_YT_VIDEOS_MIN, OTHER_YT_VIDEOS_MIN * 2 - len(results))
        if remaining > 0:
            placeholders = ",".join(["?"] * len(NAMED_YT_CHANNELS))
            other_rows = conn.execute(
                f"""
                SELECT a.title, a.url, a.published_date, a.discovered_date, a.categories,
                       b.name AS blog_name, b.url AS blog_url
                FROM articles a
                JOIN blogs b ON a.blog_id = b.id
                WHERE b.name NOT IN ({placeholders})
                  AND a.discovered_date >= ?
                  AND (a.url LIKE '%youtube.com/watch%' OR a.url LIKE '%youtu.be/%')
                ORDER BY a.discovered_date DESC
                LIMIT ?
                """,
                tuple(NAMED_YT_CHANNELS) + (other_cutoff, remaining),
            ).fetchall()

            for r in other_rows:
                if r["url"] in seen_urls:
                    continue
                seen_urls.add(r["url"])
                cats = _parse_categories(r["categories"])
                rss_date = r["published_date"]
                discovered = r["discovered_date"]
                pub_date = rss_date if rss_date else discovered
                results.append({
                    "title": r["title"],
                    "url": r["url"],
                    "published_date": pub_date,
                    "discovered_date": discovered,
                    "blog_name": r["blog_name"],
                    "blog_url": r["blog_url"],
                    "categories": cats,
                })
    finally:
        conn.close()

    logger.info(f"collect_youtube_videos: fetched {len(results)} total ({len([r for r in results if r['blog_name'] in NAMED_YT_CHANNELS])} named, {len([r for r in results if r['blog_name'] not in NAMED_YT_CHANNELS])} other)")
    return results


def _parse_categories(raw_cats):
    """Parse categories from blogwatcher DB (JSON array or comma-separated)."""
    if not raw_cats:
        return []
    try:
        parsed = json.loads(raw_cats)
        if isinstance(parsed, list):
            return [str(c).strip() for c in parsed if str(c).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    return [c.strip() for c in raw_cats.split(",") if c.strip()]
