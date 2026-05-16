"""Scoring engine for The Daily Llama.

Computes keyword-match scores, recency decay, and source credibility
multipliers, then classifies articles into featured_video, runner_up,
news_card, novel_finding, or discarded.

Section reference: 3.1-3.8 of architecture plan.
"""

import os
import re
from datetime import datetime, timedelta, timezone

from utils.config_loader import load_config

# Named YouTube channels - videos from these get a minimum score floor
# so they always appear in the carousel regardless of keyword matches.
NAMED_YT_CHANNELS = ["David Ondrej", "Codacus", "Alex Finn", "Fireship", "Two Minute Papers", "Matt Wolfe"]
NAMED_YT_KEYWORD_FLOOR = 0.5  # Minimum keyword score for named channel videos

# Compile once so repeated scoring is fast.
# We build pattern dicts per-run because the config might change.

def score_articles(articles, now=None):
    """Score and classify every article.

    Parameters
    ----------
    articles : list[dict]
        Each dict has: title, url, blog_name, blog_url, published_date (ISO str or None),
        categories (list[str]).
    now : datetime or None
        Timestamp for recency calculation. Uses UTC now when None.

    Returns
    -------
    dict with keys:
        featured_video  : dict or None
        runner_ups      : list[dict]
        news_cards      : list[dict]
        novel_findings  : list[dict]
        all_scored      : list[dict]  (unfiltered, scored)
    """
    if now is None:
        now = datetime.now(timezone.utc)

    config = load_config()
    categories = config.get("categories", {})
    source_multipliers = config.get("source_multipliers", {})
    youtube_multipliers = config.get("youtube_source_multipliers", {})
    thresholds = config.get("thresholds", {})
    recency_cfg = config.get("recency", {})
    display_cfg = config.get("display", {})

    half_life_hours = recency_cfg.get("half_life_hours", 48)
    max_age_hours = recency_cfg.get("max_age_hours", 168)

    featured_video_min = thresholds.get("featured_video_min_score", 0.80)
    runner_up_min = thresholds.get("runner_up_min_score", 0.65)
    news_card_min = thresholds.get("news_card_min_score", 0.30)
    novel_min = thresholds.get("novel_finding_min_score", 0.55)
    novel_src_max = thresholds.get("novel_finding_source_multiplier_max", 0.0)

    max_weight = max((c["weight"] for c in categories.values()), default=1)

    # Pre-compile keyword patterns: (category_name, weight, [regex_patterns])
    cat_patterns = _build_patterns(categories)

    scored = []
    for article in articles:
        s = _score_one(
            article, now, cat_patterns, max_weight,
            source_multipliers, youtube_multipliers,
            half_life_hours, max_age_hours,
        )
        scored.append(s)

    # Classify
    featured_video = None
    runner_ups = []
    news_cards = []
    novel_findings = []
    discarded = []

    # Separate videos and non-videos, sort by score desc.
    videos = [s for s in scored if s["is_video"]]
    non_videos = [s for s in scored if not s["is_video"]]

    videos.sort(key=lambda x: x["score"], reverse=True)
    non_videos.sort(key=lambda x: x["score"], reverse=True)

    # --- featured_video ---
    for v in videos:
        if v["score"] >= featured_video_min:
            featured_video = v
            # Don't let this one be a runner-up too.
            break

    # --- runner_ups ---
    for v in videos:
        if featured_video is not None and v is featured_video:
            continue
        if v["score"] >= runner_up_min:
            runner_ups.append(v)

    # Cap runner_ups
    runner_up_max = display_cfg.get("runner_up_count_max", 4)
    runner_ups = runner_ups[:runner_up_max]

    # --- news_cards ---
    for a in non_videos:
        if a["score"] >= news_card_min:
            news_cards.append(a)

    # Soft cap news cards
    news_cap = display_cfg.get("news_card_soft_cap", 50)
    news_cards = news_cards[:news_cap]

    # --- novel_findings ---
    for a in scored:
        if a.get("classification"):
            continue  # Already classified
        src_mult = a.get("source_multiplier", 0.7)
        if a["score"] >= novel_min and src_mult <= novel_src_max:
            a["classification"] = "novel_finding"
            novel_findings.append(a)

    # --- discarded ---
    classified_ids = set()
    if featured_video:
        classified_ids.add(featured_video.get("url"))
    for a in runner_ups + news_cards + novel_findings:
        classified_ids.add(a.get("url"))

    for a in scored:
        if not a.get("classification"):
            a["classification"] = "discarded"

    return {
        "featured_video": featured_video,
        "runner_ups": runner_ups,
        "news_cards": news_cards,
        "novel_findings": novel_findings,
        "all_scored": scored,
    }


def _score_one(article, now, cat_patterns, max_weight,
               source_multipliers, youtube_multipliers,
               half_life_hours, max_age_hours):
    """Score a single article."""
    title = (article.get("title") or "").lower()
    url = (article.get("url") or "").lower()
    blog_name = article.get("blog_name", "")
    cats = article.get("categories", [])
    pub_date = article.get("published_date")

    # 1. Keyword score (0.0 - 1.0)
    keyword_score = 0.0
    matched_categories = []
    word_boundary_patterns = _get_word_boundary_patterns(title)

    for cat_name, weight, patterns in cat_patterns:
        match_count = 0
        for pat in patterns:
            if pat.search(title):
                match_count += 1
        if match_count > 0:
            weighted = match_count * weight / max_weight
            if weighted > keyword_score:
                keyword_score = weighted
            matched_categories.append(cat_name)

    # RSS category bonus: +0.1 per matching category
    rss_bonus = 0.0
    rss_cats_lower = [c.lower() for c in cats]
    for cat_name, _, _ in cat_patterns:
        if cat_name.lower() in rss_cats_lower:
            rss_bonus += 0.1
    keyword_score = min(keyword_score + rss_bonus, 1.0)

    # Named channel boost: ensure named YouTubers always score at least the floor
    if _is_video_url(url) and blog_name in NAMED_YT_CHANNELS:
        keyword_score = max(keyword_score, NAMED_YT_KEYWORD_FLOOR)

    # 2. is_video detection
    is_video = _is_video_url(url)

    # 3. Source credibility multiplier
    if is_video:
        source_mult = youtube_multipliers.get(blog_name, 0.7)
    else:
        source_mult = source_multipliers.get(blog_name, 0.7)

    # 4. Recency decay
    recency_factor = _recency_decay(pub_date, now, half_life_hours, max_age_hours)

    # 5. Combined score
    raw_score = keyword_score * recency_factor * source_mult
    score = max(0.0, min(raw_score, 1.0))
    score = round(score, 4)

    # 6. "why picked" - one sentence based on top category match
    why_picked = ""
    if matched_categories:
        why_picked = "Matches " + ", ".join(matched_categories[:3]) + " interest areas"

    return {
        "title": article.get("title", ""),
        "url": article.get("url", ""),
        "blog_name": blog_name,
        "blog_url": article.get("blog_url", ""),
        "channel": blog_name,  # Alias for display (used by carousel/overlay)
        "published_date": pub_date,
        "categories": cats,
        "matched_categories": matched_categories,
        "keyword_score": round(keyword_score, 4),
        "recency_factor": round(recency_factor, 4),
        "source_multiplier": source_mult,
        "score": score,
        "is_video": is_video,
        "why_picked": why_picked,
        "thumbnail": _yt_thumbnail(article.get("url", "")) if is_video else "",
        "summary": _first_sentence(article.get("title", "")),
        "age_days": round(_article_age(pub_date, now), 1) if pub_date else 0,
    }


def _build_patterns(categories):
    """Build list of (name, weight, [compiled_regex]) from config."""
    patterns = []
    for cat_name, cat_data in categories.items():
        weight = cat_data.get("weight", 5)
        keywords = cat_data.get("keywords", [])
        compiled = []
        for kw in keywords:
            try:
                compiled.append(re.compile(re.escape(kw), re.IGNORECASE))
            except re.error:
                compiled.append(re.compile(re.escape(kw), re.IGNORECASE))
        patterns.append((cat_name, weight, compiled))
    return patterns


def _get_word_boundary_patterns(title):
    """Not used directly - keyword patterns are case-insensitive substring matches."""
    return []


def _is_video_url(url):
    """Detect YouTube URLs."""
    if not url:
        return False
    url_lower = url.lower()
    return "youtube.com/watch" in url_lower or "youtu.be/" in url_lower


def _recency_decay(pub_date_str, now, half_life_hours, max_age_hours):
    """Compute recency decay factor (0.0 - 1.0)."""
    if not pub_date_str:
        return 0.5  # Unknown date -> moderate decay

    pub_date = None

    # 1. Primary: datetime.fromisoformat() handles all ISO 8601 variants
    try:
        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
    except Exception:
        pass

    # 2. Fallback: RFC 2822 (YouTube RSS format)
    if pub_date is None:
        try:
            from email.utils import parsedate_to_datetime
            pub_date = parsedate_to_datetime(pub_date_str)
        except Exception:
            pass

    # 3. Last resort: try common manual formats (no TZ suffix).
    if pub_date is None:
        for fmt in [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ]:
            try:
                naive = datetime.strptime(pub_date_str, fmt)
                pub_date = naive.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue

    if pub_date is None:
        return 0.5  # Unparseable -> moderate decay

    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)

    delta = now - pub_date
    age_hours = delta.total_seconds() / 3600.0

    if age_hours < 0:
        return 1.0  # Future date
    if age_hours > max_age_hours:
        return 0.0

    # Exponential decay: 0.5 ^ (age / half_life)
    return 0.5 ** (age_hours / max(half_life_hours, 1))


def _yt_thumbnail(url):
    """Extract YouTube video ID and return thumbnail URL."""
    if not url:
        return ""
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return "https://img.youtube.com/vi/" + m.group(1) + "/hqdefault.jpg"
    return ""


def _first_sentence(title):
    """Use title as summary fallback."""
    if not title:
        return ""
    return title.split(".")[0].strip()


def _article_age(pub_date_str, now):
    """Calculate age in days from published date string to now.

    Returns float days. Handles various ISO/RFC formats.
    Returns 0 on parse failure.
    """
    if not pub_date_str:
        return 0
    from email.utils import parsedate_to_datetime
    pub_date = None
    try:
        pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
    except Exception:
        pass
    if pub_date is None:
        try:
            pub_date = parsedate_to_datetime(pub_date_str)
        except Exception:
            pass
    if pub_date is None:
        for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
            try:
                naive = datetime.strptime(pub_date_str, fmt)
                pub_date = naive.replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
    if pub_date is None:
        return 0
    if pub_date.tzinfo is None:
        pub_date = pub_date.replace(tzinfo=timezone.utc)
    delta = now - pub_date
    return max(0, delta.total_seconds() / 86400.0)


def compute_empty_day(feed_data, yesterday_feed_path):
    """Handle empty-day prospecting and carryover.

    Populates carryover from yesterday if zero articles today.
    """
    if not os.path.isfile(yesterday_feed_path):
        return

    import json
    try:
        with open(yesterday_feed_path, "r") as f:
            yesterday = json.load(f)
    except (json.JSONDecodeError, OSError):
        return

    ru = yesterday.get("runner_ups", [])
    if ru:
        feed_data["carryover_runner_ups"] = ru
        feed_data["empty_day"] = True
        feed_data["generation_status"] = "partial"
        feed_data["failed_steps"] = feed_data.get("failed_steps", [])
        feed_data["failed_steps"].append("blogwatcher: zero new articles")
