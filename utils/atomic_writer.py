"""
Atomic writer for The Daily Llama.

Implements the atomic-swap protocol described in Section 4.5 of the
architecture plan: generate into a .new/ directory, validate, then
rename the live directory out of the way and move .new/ into place.
"""

import json
import os
import shutil

from utils.paths import SITE_DIR, SITE_NEW, SITE_OLD, FEED_PATH

REQUIRED_HTML_FILES = ["index.html", "tasks.html", "health.html", "archive.html"]


def atomic_swap(new_content_dir=None):
    """Atomically swap the generated site into place.

    Steps:
      1. Clean up stale .new/ and .old/ from previous crashed runs.
      2. Validate that all required HTML files exist in new_content_dir.
      3. Validate feed.json parses.
      4. Rename current site → .old/, move .new/ → site.
      5. Symlink feed.json into site root.
      6. Remove .old/.

    Parameters
    ----------
    new_content_dir : str or None
        Directory containing the freshly generated site.  When None
        (the common case) the caller is expected to have written
        everything into SITE_NEW before calling this function, so we
        treat SITE_NEW as the source.
    """
    source = new_content_dir if new_content_dir is not None else SITE_NEW

    # 1. Clean up stale leftovers.
    _rmtree_if_exists(SITE_OLD)
    if source != SITE_NEW:
        _rmtree_if_exists(SITE_NEW)

    # 2. Validate required HTML files exist.
    for fname in REQUIRED_HTML_FILES:
        path = os.path.join(source, fname)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Required HTML file missing: {path}")

    # 3. Validate feed.json parses.
    if os.path.isfile(FEED_PATH):
        with open(FEED_PATH, "r") as f:
            json.load(f)

    # 4. Swap.
    if os.path.isdir(SITE_DIR):
        os.rename(SITE_DIR, SITE_OLD)
    os.rename(source, SITE_DIR)

    # 5. Symlink feed.json into site root.
    feed_link = os.path.join(SITE_DIR, "feed.json")
    if os.path.islink(feed_link) or os.path.isfile(feed_link):
        os.unlink(feed_link)
    os.symlink(FEED_PATH, feed_link)

    # 6. Clean up old.
    _rmtree_if_exists(SITE_OLD)
    # If the source was an external directory, remove it too.
    if new_content_dir is not None and os.path.isdir(new_content_dir):
        _rmtree_if_exists(new_content_dir)


def _rmtree_if_exists(path):
    """Remove a directory tree if it exists, ignoring errors."""
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
