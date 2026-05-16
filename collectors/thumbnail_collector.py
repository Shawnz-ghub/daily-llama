"""Thumbnail collector for The Daily Llama.

Extracts and caches thumbnail images from article URLs.
Stores cropped 16:9 thumbnails (320x180) in site-data/thumbnails/.
"""

import os
import json
import hashlib
import logging
import requests
from io import BytesIO
from urllib.parse import urljoin

try:
    from bs4 import BeautifulSoup
    from PIL import Image
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

logger = logging.getLogger(__name__)

# Config
THUMB_DIR = "/home/shawnz/site-data/thumbnails"
CACHE_INDEX = os.path.join(THUMB_DIR, "index.json")
THUMB_W = 320
THUMB_H = 180
USER_AGENT = "Mozilla/5.0 (DailyLlama/1.0)"


def _ensure_dir():
    os.makedirs(THUMB_DIR, exist_ok=True)


def _load_cache():
    if not os.path.isfile(CACHE_INDEX):
        return {}
    try:
        with open(CACHE_INDEX) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache):
    with open(CACHE_INDEX, "w") as f:
        json.dump(cache, f, indent=2)


def _url_hash(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()


def _crop_center(img, target_w, target_h):
    """Crop to target aspect ratio from center, then resize."""
    src_w, src_h = img.size
    src_aspect = src_w / src_h
    target_aspect = target_w / target_h

    if src_aspect > target_aspect:
        # Source is wider - crop width
        new_w = int(src_h * target_aspect)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    elif src_aspect < target_aspect:
        # Source is taller - crop height
        new_h = int(src_w / target_aspect)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _extract_image_url(html, base_url):
    """Extract best image URL from HTML using meta tags and fallbacks."""
    soup = BeautifulSoup(html, "html.parser")

    # Priority 1: og:image
    for meta in soup.find_all("meta", attrs={"property": "og:image"}):
        content = meta.get("content", "")
        if content:
            return urljoin(base_url, content)

    # Priority 2: twitter:image
    for meta in soup.find_all("meta", attrs={"name": "twitter:image"}):
        content = meta.get("content", "")
        if content:
            return urljoin(base_url, content)

    # Priority 3: article:image
    for meta in soup.find_all("meta", attrs={"property": "article:image"}):
        content = meta.get("content", "")
        if content:
            return urljoin(base_url, content)

    # Priority 4: first img with a reasonable size hint
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src:
            continue
        w = img.get("width")
        if w and w.isdigit() and int(w) < 100:
            continue
        if src.startswith("data:"):
            continue
        lower = src.lower()
        if any(k in lower for k in ("logo", "avatar", "icon", "spacer", "pixel", "badge", "favicon")):
            continue
        return urljoin(base_url, src)

    return None


def get_thumbnail(article_url, title="", force=False):
    """Fetch and cache a thumbnail for the given article URL.

    Returns a dict with 'url' (relative thumbnail path), 'status' (ok|error|no_image).
    """
    if not HAS_DEPS:
        logger.warning("Pillow/BeautifulSoup not available - skipping thumbnails")
        return {"url": "", "status": "no_deps"}

    _ensure_dir()
    cache = _load_cache()

    url_hash = _url_hash(article_url)
    thumb_filename = url_hash + ".jpg"
    thumb_path = os.path.join(THUMB_DIR, thumb_filename)

    # Check cache
    if not force and article_url in cache:
        cached = cache[article_url]
        if os.path.isfile(thumb_path):
            return cached

    # Fetch the page
    try:
        resp = requests.get(
            article_url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning("Failed to fetch %s: %s", article_url[:60], e)
        result = {"url": "", "status": "fetch_error", "error": str(e)}
        cache[article_url] = result
        _save_cache(cache)
        return result

    # Extract image URL
    img_url = _extract_image_url(html, article_url)
    if not img_url:
        logger.info("No image found for %s", article_url[:60])
        result = {"url": "", "status": "no_image"}
        cache[article_url] = result
        _save_cache(cache)
        return result

    # Download image
    try:
        img_resp = requests.get(
            img_url,
            headers={"User-Agent": USER_AGENT},
            timeout=15,
        )
        img_resp.raise_for_status()
        img = Image.open(BytesIO(img_resp.content))
    except Exception as e:
        logger.warning("Failed to download image from %s: %s", img_url[:60], e)
        result = {"url": "", "status": "download_error", "error": str(e)}
        cache[article_url] = result
        _save_cache(cache)
        return result

    # Crop to thumbnail
    try:
        # Convert to RGB if needed (JPEG doesn't support RGBA/P)
        if img.mode in ("P", "RGBA"):
            img = img.convert("RGB")
        thumb = _crop_center(img, THUMB_W, THUMB_H)
        thumb.save(thumb_path, "JPEG", quality=85)
    except Exception as e:
        logger.warning("Failed to crop/save thumbnail: %s", e)
        result = {"url": "", "status": "crop_error", "error": str(e)}
        cache[article_url] = result
        _save_cache(cache)
        return result

    # Success
    relative_url = "../thumbnails/" + thumb_filename
    result = {"url": relative_url, "status": "ok"}
    cache[article_url] = result
    _save_cache(cache)
    logger.info("Thumbnail saved for %s: %s", article_url[:60], thumb_filename)
    return result


def batch_generate(news_cards):
    """Generate thumbnails for all news cards that don't have one yet.

    Returns the cards with 'thumbnail' field populated.
    """
    if not HAS_DEPS:
        return news_cards

    _ensure_dir()

    count_total = len(news_cards)
    count_new = 0
    count_existing = 0
    count_failed = 0

    for card in news_cards:
        url = card.get("url", "")
        if not url:
            continue

        cache = _load_cache()
        url_hash = _url_hash(url)
        thumb_path = os.path.join(THUMB_DIR, url_hash + ".jpg")

        if url in cache and cache[url].get("status") == "ok" and os.path.isfile(thumb_path):
            card["thumbnail"] = cache[url]["url"]
            count_existing += 1
            continue

        result = get_thumbnail(url, card.get("title", ""))
        if result.get("status") == "ok":
            card["thumbnail"] = result["url"]
            count_new += 1
        else:
            card["thumbnail"] = ""
            count_failed += 1

    logger.info(
        "Thumbnails: %d new, %d cached, %d failed (of %d total)",
        count_new, count_existing, count_failed, count_total,
    )
    return news_cards
