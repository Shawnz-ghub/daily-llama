#!/usr/bin/env python3
"""The Daily Llama — HTTP server with no-cache headers."""
import http.server
import os

PORT = 8788
DIRECTORY = '/home/shawnz/daily-llama-site'
BIND = '0.0.0.0'

class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        super().end_headers()

if __name__ == '__main__':
    os.chdir(DIRECTORY)
    server = http.server.HTTPServer((BIND, PORT), NoCacheHandler)
    print(f'Serving {DIRECTORY} on {BIND}:{PORT} (no-cache)')
    server.serve_forever()
