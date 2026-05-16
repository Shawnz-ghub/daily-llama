"""HTML generator for The Daily Llama.

Produces 4 static pages (index, tasks, health, archive) from feed.json data.
No nested f-strings or backslashes inside f-string expressions.
"""
import os
import shutil
import random
from datetime import datetime, timezone


def _esc(s):
    if s is None:
        return ''
    return (str(s)
        .replace('&', '&amp;')
        .replace('<', '&lt;')
        .replace('>', '&gt;')
        .replace('"', '&quot;')
        .replace("'", '&#x27;'))


def _fmt_date(iso_str):
    if not iso_str:
        return ''
    try:
        d = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
        return d.strftime('%b %d, %Y %H:%M UTC')
    except (ValueError, TypeError):
        return iso_str[:10] if iso_str else ''


def _badges(items):
    """Return HTML for badge spans from a list of category names."""
    if not items:
        return ''
    return ''.join('<span class="badge badge-featured">' + _esc(c) + '</span>' for c in items)


def _extract_yt_id(url):
    """Extract YouTube video ID from a URL."""
    if not url:
        return ''
    import re
    m = re.search(r'(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})', url)
    return m.group(1) if m else ''


def _thumb_html(item):
    """Return thumbnail img tag if item has a thumbnail URL."""
    thumb = item.get('thumbnail')
    if not thumb:
        return ''
    return '<img class="thumb" src="' + _esc(thumb) + '" alt="" loading="lazy">'


def _runner_thumb(item):
    """Return thumbnail img tag for runner-up cards."""
    thumb = item.get('thumbnail')
    if not thumb:
        return ''
    return '<img src="' + _esc(thumb) + '" alt="" loading="lazy" style="width:100%;aspect-ratio:16/9;object-fit:cover;border-radius:6px;margin-bottom:10px;">'


def _maybe_why(item):
    """Return 'why picked' div if present."""
    why = item.get('why_picked')
    if not why:
        return ''
    return '<div class="why">' + _esc(why) + '</div>'


def _maybe_excerpt(item, key='summary'):
    """Return excerpt paragraph if item has the key."""
    val = item.get(key)
    if not val:
        return ''
    return '<p class="card-excerpt">' + _esc(val) + '</p>'


def _maybe_excerpt_inline(item, key='summary', extra_style=''):
    """Return excerpt paragraph with optional inline style."""
    val = item.get(key)
    if not val:
        return ''
    style_attr = ' style="' + _esc(extra_style) + '"' if extra_style else ''
    return '<p class="card-excerpt"' + style_attr + '>' + _esc(val) + '</p>'


def _relative_time(iso_str, now=None):
    if not iso_str:
        return 'unknown'
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        d = datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return iso_str[:10]
    delta = now - d
    hours = delta.total_seconds() / 3600
    if hours < 1:
        mins = int(delta.total_seconds() / 60)
        if mins <= 0:
            return 'just now'
        return str(mins) + ' minute' + ('s' if mins != 1 else '') + ' ago'
    if hours < 24:
        h = int(hours)
        return str(h) + ' hour' + ('s' if h != 1 else '') + ' ago'
    days = int(hours / 24)
    return str(days) + ' day' + ('s' if days != 1 else '') + ' ago'


def _last_updated_label(feed_data, now=None):
    """Return a compact inline label like '🟢 just now' for the nav brand."""
    if now is None:
        now = datetime.now(timezone.utc)
    gen_status = feed_data.get('generation_status', 'ok')
    generated_at = feed_data.get('generated_at', '')

    if gen_status == 'error':
        return '\u26A0\uFE0F failed'

    if gen_status == 'partial':
        return '\u26A0\uFE0F partial'

    rel = _relative_time(generated_at, now)

    try:
        gen_dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
        hours_since = (now - gen_dt).total_seconds() / 3600
    except (ValueError, TypeError):
        hours_since = 0

    if hours_since > 48:
        return '\U0001F534 ' + rel
    elif hours_since > 24:
        return '\u26A0\uFE0F ' + rel
    else:
        return '\U0001F7E2 ' + rel


def _last_updated_banner(feed_data, now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    gen_status = feed_data.get('generation_status', 'ok')
    generated_at = feed_data.get('generated_at', '')
    last_successful = feed_data.get('last_successful_run', '')
    failed_steps = feed_data.get('failed_steps', [])

    if gen_status == 'error':
        steps = ', '.join(failed_steps) if failed_steps else 'unknown'
        last_ok = _fmt_date(last_successful) if last_successful else 'N/A'
        body = ('<div class="error-banner">'
                '<h3>&#9888; Generation Failed</h3>'
                '<ul><li>Failed step(s): ' + _esc(steps) + '</li>'
                '<li>Last successful: ' + _esc(last_ok) + '</li></ul>'
                '</div>')
        return body

    if gen_status == 'partial':
        steps = ', '.join(failed_steps) if failed_steps else 'unknown'
        last_ok = _fmt_date(last_successful) if last_successful else ''
        body = '<div class="empty-banner"><h2>&#9888; Partial Generation</h2><p>Step(s) failed: ' + _esc(steps) + '</p>'
        if last_ok:
            body += '<p>Last successful: ' + _esc(last_ok) + '</p>'
        body += '</div>'
        return body

    try:
        gen_dt = datetime.fromisoformat(generated_at.replace('Z', '+00:00'))
        hours_since = (now - gen_dt).total_seconds() / 3600
    except (ValueError, TypeError):
        hours_since = 0

    rel = _relative_time(generated_at, now)

    if hours_since > 48:
        css_class = 'error-banner'
        prefix = '&#128308;'
        text = 'Site stale -- last updated ' + rel + ' (over 48 hours)'
        extra = 'border:1px solid var(--danger);background:rgba(239,68,68,0.1);'
    elif hours_since > 24:
        css_class = 'empty-banner'
        prefix = '&#9888;'
        text = 'Warning -- last updated ' + rel + ' (over 24 hours ago)'
        extra = 'border:1px dashed var(--warning);background:rgba(234,179,8,0.08);'
    else:
        css_class = 'last-updated-banner'
        prefix = '&#128994;'
        text = 'Last updated ' + rel
        extra = 'border:1px solid var(--accent);background:rgba(20,184,166,0.06);color:var(--accent);'

    style = 'padding:10px 20px;border-radius:var(--radius-sm);margin-bottom:24px;font-size:0.85rem;' + extra
    return '<div class="' + css_class + '" style="' + style + '">' + prefix + ' ' + _esc(text) + '</div>'


def _nav_html(current_page, last_updated_label=''):
    pages = [('index.html', 'Feed'), ('tasks.html', 'Tasks'), ('health.html', 'Health'), ('archive.html', 'Archive')]
    links = ''
    for href, label in pages:
        cls = ' class="active"' if href == current_page else ''
        links += '            <a href="' + href + '"' + cls + '>' + _esc(label) + '</a>\n'
    brand = ('<span class="nav-brand">'
             'Updated ' + last_updated_label + '</span>\n')
    nav = ('<nav class="site-nav">\n'
           '  <div class="nav-inner">\n'
           '    ' + brand +
           '    <div class="nav-links">\n'
           + links +
           '    </div>\n'
           '  </div>\n'
           '</nav>\n')
    return nav


def _footer_html():
    return '<footer class="site-footer">\n  <p>The Daily Llama &mdash; Automagically generated.</p>\n</footer>\n'


def _page_wrapper(title, current_page, feed_data, body_content, extra_scripts='', now=None):
    compact_label = _last_updated_label(feed_data, now)
    nav = _nav_html(current_page, compact_label)
    footer = _footer_html()
    overlay = ''
    if current_page == 'index.html':
        overlay = ('<div id="video-overlay" class="video-overlay hidden">\n'
                   '  <div class="video-controls">\n'
                   '    <button class="video-popout-btn" onclick="popOutVideo()" title="Open in YouTube">'
                   '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
                   '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'
                   '<polyline points="15 3 21 3 21 9"/>'
                   '<line x1="10" y1="14" x2="21" y2="3"/>'
                   '</svg></button>\n'
                   '    <button class="video-close-btn" onclick="closeVideo()" title="Close (Esc)">&times;</button>\n'
                   '  </div>\n'
                   '  <div class="video-modal">\n'
                   '    <div id="video-player"></div>\n'
                   '  </div>\n'
                   '</div>\n')
    return ('<!DOCTYPE html>\n'
            '<html lang="en" class="dark">\n'
            '<head>\n'
            '  <meta charset="UTF-8">\n'
            '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            '  <title>The Daily Llama &mdash; ' + _esc(title) + '</title>\n'
            '  <link rel="icon" type="image/png" href="../llama-logo.png?v=8">\n'
            '  <link rel="stylesheet" href="../style.css?v=8">\n'
            '</head>\n'
            '<body>\n'
            + nav
            + '<div class="container">\n'
            + body_content
            + '</div>\n'
            + footer
            + overlay
            + extra_scripts
            + '</body>\n'
            '</html>\n')


def _render_index(feed_data):
    news_cards = feed_data.get('news_cards', [])
    novel_findings = feed_data.get('novel_findings', [])
    video_carousel = feed_data.get('video_carousel', [])
    carryover = feed_data.get('carryover_runner_ups', [])
    empty_day = feed_data.get('empty_day', False)

    # Show all videos in the carousel (no age filter)
    recent_videos = list(video_carousel)

    body = ('<div class="site-header" style="display:flex;align-items:center;justify-content:center;gap:14px;padding-bottom:20px;">\n'
            '  <img src="../llama-logo.png" alt="" width="48" height="48" style="border-radius:8px;flex-shrink:0;">\n'
            '  <h1 style="font-family:\'Georgia\',\'Times New Roman\',\'Palatino Linotype\',serif;font-size:2.2rem;font-weight:800;letter-spacing:-0.5px;margin:0;">The Daily Llama</h1>\n'
            '</div>\n')

    if empty_day:
        body += ('<div class="empty-banner">\n'
                 '  <h2>&#128233; Quiet Day</h2>\n'
                 '  <p>No new articles found today. Showing carryover from yesterday.</p>\n'
                 '</div>\n')
        if carryover:
            # Use carryover for carousel if empty
            recent_videos = list(carryover)

    body += ('<div id="error-banner" class="error-banner hidden">\n'
             '  <h3>&#9888; Data Error</h3>\n'
             '  <p class="error-msg">An error occurred loading feed data.</p>\n'
             '</div>\n')

    body += '<div id="empty-banner" class="empty-banner hidden">\n  <h2>&#128233; Quiet Day</h2>\n  <p id="empty-msg"></p>\n</div>\n'

    # ── Video Carousel ────────────────────────
    body += '<section class="video-carousel-section">\n'
    if recent_videos:
        body += '  <div id="video-carousel" class="video-carousel">\n'
        # Randomize order for the carousel
        random.shuffle(recent_videos)
        for i, v in enumerate(recent_videos):
            yt_id = _extract_yt_id(v.get('url', ''))
            thumb_url = _esc(v.get('thumbnail', ''))
            title = _esc(v.get('title', ''))
            channel = _esc(v.get('channel', v.get('blog_name', '')))
            score = _esc(str(v.get('score', '')))

            card = ('    <div class="video-carousel-card">\n'
                    '      <div class="vcc-thumb">\n')
            if yt_id:
                card += '        <a href="#" onclick="openVideo(this,\'' + _esc(yt_id) + '\');return false;" style="cursor:pointer;">\n'
                card += '          <img src="' + thumb_url + '" alt="" loading="lazy">\n'
                card += '        </a>\n'
            else:
                card += '        <img src="' + thumb_url + '" alt="" loading="lazy">\n'
            card += '      </div>\n'
            card += '      <div class="vcc-body">\n'
            card += '        <a href="' + _esc(v.get('url', '')) + '" target="_blank" rel="noopener" class="vcc-title">' + title + '</a>\n'
            card += '        <div class="vcc-meta">\n'
            card += '          <span class="vcc-channel">' + channel + '</span>\n'
            card += '        </div>\n'
            card += '      </div>\n'
            card += '    </div>\n'
            body += card
        body += '  </div>\n'
    else:
        body += '  <p class="text-center" style="padding:40px 0;color:var(--text-muted);">No videos today.</p>\n'
    body += '</section>\n'

    # ── News grid ─────────────────────────────
    body += '<div id="news-grid" class="news-grid">\n'
    if news_cards:
        # Sort: cards with thumbnails first
        sorted_cards = sorted(news_cards, key=lambda c: 0 if c.get('thumbnail') else 1)
        for nc in sorted_cards:
            nsum = _maybe_excerpt(nc, 'summary')
            thumb = nc.get('thumbnail', '')
            thumb_html = ''
            if thumb:
                thumb_html = '    <div class="news-thumb"><img src="' + _esc(thumb) + '" alt="" loading="lazy"></div>\n'
            body += ('  <div class="card news-card">\n'
                     + thumb_html +
                     '    <a href="' + _esc(nc.get('url', '')) + '" target="_blank" rel="noopener" class="card-title">\n'
                     '      ' + _esc(nc.get('title', '')) + '\n'
                     '    </a>\n'
                     '    <div class="card-meta">\n'
                     '      <span>' + _fmt_date(nc.get('published_date', '')) + '</span>\n'
                     '    </div>\n'
                     '    ' + nsum + '\n'
                     '  </div>\n')
    else:
        body += '  <p class="text-muted" style="grid-column:1/-1;">No news articles today.</p>\n'
    body += '</div>\n'

    # ── Novel findings ─────────────────────────
    if novel_findings:
        body += '<div id="novel-container" class="novel-section">\n'
        body += '  <h2 class="section-title">&#128270; Novel Findings</h2>\n'
        body += '  <div id="novel-list">\n'
        for nf in novel_findings:
            body += ('    <div class="novel-item">\n'
                     '      <div class="novel-source">' + _esc(nf.get('source', '')) + '</div>\n'
                     '      <a href="' + _esc(nf.get('url', '')) + '" target="_blank" rel="noopener">'
                     + _esc(nf.get('title', '')) + '</a>\n'
                     '      <div class="novel-note">' + _esc(nf.get('prospecting_note', '')) + '</div>\n'
                     '    </div>\n')
        body += '  </div>\n'
        body += '</div>\n'

    scripts = ('<script src="../feed-loader.js?v=8"></script>\n'
               '<script>\n'
               '(function(){\n'
               '  var overlay = document.getElementById(\'video-overlay\');\n'
               '  var player = document.getElementById(\'video-player\');\n'
               '  var currentVideoId = null;\n'
               '  window.openVideo = function(el, videoId) {\n'
               '    currentVideoId = videoId;\n'
               '    overlay.classList.remove(\'hidden\');\n'
               '    player.innerHTML = \'<iframe width="100%" height="100%" src="https://www.youtube.com/embed/\' + videoId + \'?autoplay=1" frameborder="0" allow="autoplay; encrypted-media" allowfullscreen></iframe>\';\n'
               '    document.body.style.overflow = \'hidden\';\n'
               '  };\n'
               '  window.closeVideo = function() {\n'
               '    overlay.classList.add(\'hidden\');\n'
               '    player.innerHTML = \'\';\n'
               '    currentVideoId = null;\n'
               '    document.body.style.overflow = \'\';\n'
               '  };\n'
               '  window.popOutVideo = function() {\n'
               '    if (currentVideoId) window.open(\'https://www.youtube.com/watch?v=\' + currentVideoId, \'_blank\');\n'
               '  };\n'
               '  overlay.addEventListener(\'click\', function(e) { if (e.target === overlay) closeVideo(); });\n'
               '  document.addEventListener(\'keydown\', function(e) { if (e.key === \'Escape\') closeVideo(); });\n'
               '})();\n'
               '</script>\n')
    return body, scripts


def _render_tasks(feed_data):
    tr = feed_data.get('task_reports', {})
    completed = tr.get('completed', [])
    blocked = tr.get('blocked', [])
    running = tr.get('running', [])
    kanban_url = tr.get('kanban_url', 'http://192.168.1.28:8090')

    body = ('<div class="site-header">\n'
            '  <h1>Task Reports</h1>\n'
            '  <p class="subtitle">Kanban activity from the last 24 hours.</p>\n'
            '</div>\n')

    body += '<div class="task-section">\n  <div class="task-status-grid">\n'

    # Completed
    body += '    <div class="task-col completed">\n      <h3>&#9989; Completed</h3>\n'
    if completed:
        for t in completed:
            assignee = _esc(t.get('assignee', 'UNASSIGNED') or 'UNASSIGNED')
            profile = _esc(t.get('profile', assignee))
            completed_at = _fmt_date(t.get('completed_at', ''))
            summary = _esc(t.get('summary', '') or '')
            body += ('      <div class="task-item">\n'
                     '        <div class="task-id">' + _esc(t['task_id']) + '</div>\n'
                     '        <div><strong>' + _esc(t.get('title', '')) + '</strong></div>\n'
                     '        <div><span class="badge badge-featured">' + profile + '</span>'
                     ' <span class="text-muted">&rarr; ' + assignee + '</span></div>\n'
                     '        <div class="task-id">' + completed_at + '</div>\n')
            if summary:
                body += '        <p class="card-excerpt" style="margin-top:4px;">' + summary + '</p>\n'
            body += '      </div>\n'
    else:
        body += '      <p class="text-muted" style="padding:8px 12px;font-size:0.8rem;">No tasks completed in the last 24h.</p>\n'
    body += '    </div>\n'

    # Blocked
    body += '    <div class="task-col blocked">\n      <h3>&#128308; Blocked</h3>\n'
    if blocked:
        for t in blocked:
            assignee = _esc(t.get('assignee', 'UNASSIGNED') or 'UNASSIGNED')
            profile = _esc(t.get('profile', assignee))
            blocked_at = _fmt_date(t.get('completed_at', ''))
            summary = _esc(t.get('summary', 'Task blocked -- awaiting input'))
            body += ('      <div class="task-item">\n'
                     '        <div><strong>' + _esc(t.get('title', '')) + '</strong></div>\n'
                     '        <div><span class="badge badge-danger">' + profile + '</span>'
                     ' <span class="text-muted">&rarr; ' + assignee + '</span></div>\n'
                     '        <div class="task-id">Blocked: ' + blocked_at + '</div>\n'
                     '        <p class="card-excerpt" style="margin-top:4px;color:var(--danger);">' + summary + '</p>\n'
                     '      </div>\n')
    else:
        body += '      <p class="text-muted" style="padding:8px 12px;font-size:0.8rem;">No blocked tasks.</p>\n'
    body += '    </div>\n'

    # Running
    body += '    <div class="task-col running">\n      <h3>&#128260; Running</h3>\n'
    if running:
        for t in running:
            body += ('      <div class="task-item">\n'
                     '        <div><strong>' + _esc(t.get('title', '')) + '</strong></div>\n'
                     '        <div class="task-id">' + _esc(t.get('task_id', '')) + '</div>\n'
                     '      </div>\n')
    else:
        body += '      <p class="text-muted" style="padding:8px 12px;font-size:0.8rem;">No tasks in progress.</p>\n'
    body += '    </div>\n'

    body += '  </div>\n'
    body += ('  <a href="' + _esc(kanban_url) + '" target="_blank" rel="noopener" class="kanban-link">'
             'View Full Kanban Board &rarr;</a>\n')
    body += '</div>\n'

    return body, ''


def _render_health(feed_data):
    health = feed_data.get('stack_health', {})
    body = ('<div class="site-header">\n'
            '  <h1>Stack Health</h1>\n'
            '  <p class="subtitle">Server status, services, disk, and API spend.</p>\n'
            '</div>\n')
    body += '<div class="health-section">\n  <table class="health-table">\n'
    body += '    <thead><tr><th>Check</th><th>Status</th><th>Detail</th></tr></thead>\n    <tbody>\n'

    def status_cell(s):
        if s == 'green':
            return 'class="status-ok">green'
        if s == 'yellow':
            return 'class="status-warn">yellow'
        if s in ('red', 'no_key', 'see_dashboard', 'error'):
            return 'class="status-error">' + _esc(s)
        return 'class="status-error">' + _esc(s)

    # Hermes Doctor
    doctor = health.get('hermes_doctor', {})
    doc_status = doctor.get('status', 'unknown')
    d_detail = (str(doctor.get('red_count', 0)) + ' red, ' + str(doctor.get('yellow_count', 0))
                + ' yellow, ' + str(doctor.get('green_count', 0)) + ' green')
    body += '<tr><td>Hermes Doctor</td><td ' + status_cell(doc_status) + '</td><td>' + d_detail + '</td></tr>\n'

    # Services
    for svc in health.get('services', []):
        s = svc.get('status', 'unknown')
        body += '<tr><td>' + _esc(svc.get('name', '')) + '</td>'
        body += '<td ' + status_cell(s) + '</td>'
        body += '<td>' + _esc(svc.get('detail', '')) + '</td></tr>\n'

    # Disk
    for d in health.get('disk', []):
        s = d.get('status', 'unknown')
        detail = (str(d.get('used_gb', 0)) + ' GB used of ' + str(d.get('total_gb', 0))
                  + ' GB (' + str(d.get('pct_used', 0)) + '%)')
        body += '<tr><td>' + _esc(d.get('mount', '')) + '</td>'
        body += '<td ' + status_cell(s) + '</td>'
        body += '<td>' + detail + '</td></tr>\n'

    # OpenRouter Spend
    or_spend = health.get('openrouter_spend', {})
    spend_24h = or_spend.get('spend_24h')
    if spend_24h is not None:
        s24 = '${:.2f}'.format(spend_24h)
        s7d = '${:.2f}'.format(or_spend.get('spend_7d', 0))
        detail = s24 + ' (24h) / ' + s7d + ' (7d)'
        body += '<tr><td>OpenRouter Spend</td><td class="status-ok">ok</td><td>' + detail + '</td></tr>\n'
    elif spend_24h is None and or_spend.get('status') == 'no_key':
        body += '<tr><td>OpenRouter Spend</td><td class="status-warn">no_key</td>'
        body += '<td>OPENROUTER_API_KEY not set. See dashboard to configure.</td></tr>\n'
    else:
        body += '<tr><td>OpenRouter Spend</td><td class="status-error">' + _esc(or_spend.get('status', '')) + '</td>'
        body += '<td>' + _esc(or_spend.get('message', '')) + '</td></tr>\n'

    # DeepInfra Spend
    di_spend = health.get('deepinfra_spend', {})
    if di_spend.get('status') == 'see_dashboard':
        body += '<tr><td>DeepInfra Spend</td><td class="status-warn">manual</td>'
        body += '<td>' + _esc(di_spend.get('message', '')) + ' <a href="' + _esc(di_spend.get('dashboard_url', '')) + '" target="_blank" rel="noopener">View dashboard &rarr;</a></td></tr>\n'
    else:
        body += '<tr><td>DeepInfra Spend</td><td class="status-ok">ok</td>'
        body += '<td>' + _esc(di_spend.get('message', '')) + '</td></tr>\n'

    body += '    </tbody>\n  </table>\n</div>\n'
    return body, ''


def _render_archive(feed_data):
    body = ('<div class="site-header">\n'
            '  <h1>Archive</h1>\n'
            '  <p class="subtitle">Browse past Daily Llama editions by month.</p>\n'
            '</div>\n')
    body += ('<div id="archive-container">\n'
             '  <div id="archive-loading" class="text-center" style="padding:40px 0;color:var(--text-muted);">\n'
             '    Loading archives...\n  </div>\n</div>\n')
    body += '<div id="archive-error" class="error-banner hidden">\n  <h3>&#9888; Archive Error</h3>\n  <p id="archive-error-msg"></p>\n</div>\n'
    scripts = '<script src="../archive-loader.js?v=8"></script>\n'
    return body, scripts


def generate_html(feed_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    now = datetime.now(timezone.utc)

    # Copy static assets into output directory
    project_root = '/home/shawnz/daily-llama'
    for asset in ['style.css', 'feed-loader.js', 'archive-loader.js', 'llama-logo.png']:
        src = os.path.join(project_root, asset)
        dst = os.path.join(output_dir, asset)
        if os.path.isfile(src):
            shutil.copy2(src, dst)

    pages = [
        ('index.html', 'Feed', 'index.html', _render_index),
        ('tasks.html', 'Task Reports', 'tasks.html', _render_tasks),
        ('health.html', 'Stack Health', 'health.html', _render_health),
        ('archive.html', 'Archive', 'archive.html', _render_archive),
    ]

    for filename, title, current_page, render_fn in pages:
        body_content, extra_scripts = render_fn(feed_data)
        html = _page_wrapper(title, current_page, feed_data, body_content, extra_scripts, now)
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html)
