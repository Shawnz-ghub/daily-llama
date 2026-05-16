#!/usr/bin/env python3
"""The Daily Llama — HTTP server with no-cache headers and article proxy."""
import http.server
import json
import os
import re
import urllib.parse
import requests

PORT = 8788
DIRECTORY = '/home/shawnz/daily-llama-site'
BIND = '0.0.0.0'
USER_AGENT = 'Mozilla/5.0 (DailyLlama/1.0)'

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def _clean_article_html(html, source_url):
    """Extract and clean main article content from raw HTML."""
    if not HAS_BS4:
        return '<p>Article extraction not available.</p>'

    soup = BeautifulSoup(html, 'html.parser')

    # Remove unwanted elements
    for tag in soup.find_all(['script', 'style', 'nav', 'header', 'footer',
                              'aside', 'noscript', 'iframe', 'form', 'svg']):
        tag.decompose()

    for cls in ['sidebar', 'ad', 'advertisement', 'social', 'share',
                'comments', 'comment', 'related', 'recommended',
                'newsletter', 'subscribe', 'popup', 'overlay',
                'menu', 'footer', 'header', 'nav', 'cookie', 'banner']:
        for el in soup.find_all(class_=re.compile(cls, re.I)):
            el.decompose()
        for el in soup.find_all(id=re.compile(cls, re.I)):
            el.decompose()

    # Try to find main content container
    content = None
    for selector in ['article', 'main', '[role="main"]', '.post-content',
                     '.entry-content', '.article-content', '.story-body',
                     '.content-body', '#article', '#content']:
        candidates = soup.select(selector)
        if candidates:
            content = candidates[0]
            break

    if not content:
        # Fallback: find the largest text block
        body = soup.find('body')
        if body:
            candidates = body.find_all(['div', 'section'], recursive=False)
            if candidates:
                content = max(candidates, key=lambda x: len(x.get_text()))
            else:
                content = body
        else:
            content = soup

    # Clean the extracted content
    for tag in content.find_all(['script', 'style', 'noscript', 'iframe', 'form']):
        tag.decompose()

    for img in content.find_all('img'):
        src = img.get('src') or img.get('data-src') or ''
        if src and not src.startswith('data:'):
            if not src.startswith('http'):
                src = urllib.parse.urljoin(source_url, src)
            img['src'] = src
            img['loading'] = 'lazy'
            img['style'] = 'max-width:100%;height:auto;border-radius:8px;margin:16px 0;'
        else:
            img.decompose()
    for a in content.find_all('a'):
        href = a.get('href', '')
        if href and not href.startswith('http') and not href.startswith('#'):
            a['href'] = urllib.parse.urljoin(source_url, href)
        a['target'] = '_blank'
        a['rel'] = 'noopener'
        a['style'] = 'color:var(--accent);text-decoration:underline;'

    # Clean excessive whitespace
    for tag in content.find_all(['p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                                  'blockquote', 'li', 'figcaption']):
        if tag.string:
            tag.string = re.sub(r'\s+', ' ', tag.string).strip()

    return str(content)


class DailyLlamaHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == '/article-content':
            self._handle_article(params)
        else:
            super().do_GET()

    def _handle_article(self, params):
        url = params.get('url', [None])[0]
        if not url:
            self.send_error(400, 'Missing url parameter')
            return

        try:
            resp = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=20)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'status': 'error',
                'error': str(e),
            }).encode())
            return

        cleaned = _clean_article_html(html, url)

        # Also extract title and image from the page
        soup = BeautifulSoup(html, 'html.parser') if HAS_BS4 else None
        title = ''
        image = ''
        if soup:
            t = soup.find('title')
            if t: title = t.get_text().strip()
            for meta in soup.find_all('meta', attrs={'property': 'og:image'}):
                image = meta.get('content', '') or image

        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({
            'status': 'ok',
            'title': title,
            'image': image,
            'content': '<div class="article-body">' + cleaned + '</div>',
        }).encode())


if __name__ == '__main__':
    os.chdir(DIRECTORY)
    server = http.server.HTTPServer((BIND, PORT), DailyLlamaHandler)
    print(f'Serving {DIRECTORY} on {BIND}:{PORT} with article proxy')
    server.serve_forever()
