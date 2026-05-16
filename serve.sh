#!/bin/bash
# The Daily Llama - HTTP Server
exec /usr/bin/python3 -m http.server 8788 --bind 0.0.0.0 --directory /home/shawnz/daily-llama-site
