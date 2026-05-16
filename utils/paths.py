import os

HOME = "/home/shawnz"
SITE_DATA = os.path.join(HOME, "site-data")
CONFIG_PATH = os.path.join(SITE_DATA, "config.yaml")
FEED_PATH = os.path.join(SITE_DATA, "feed.json")
SITE_LIVE = os.path.join(HOME, "daily-llama-site")
SITE_DIR = SITE_LIVE
SITE_NEW = os.path.join(HOME, "daily-llama-site.new")
SITE_OLD = os.path.join(HOME, "daily-llama-site.old")
ARCHIVE_DIR = os.path.join(SITE_DATA, "archive")
LOGS_DIR = os.path.join(SITE_DATA, "logs")
BLOGWATCHER_DB = os.path.join(SITE_DATA, "blogwatcher-cli.db")

# Kanban board
KANBAN_URL = "http://192.168.1.28:8090"

# Systemd services
DAILY_LLAMA_SERVICE = "/home/shawnz/.config/systemd/user/daily-llama.service"
DAILY_LLAMA_TIMER = "/home/shawnz/.config/systemd/user/daily-llama.timer"
DAILY_LLAMA_SERVER_SERVICE = "/home/shawnz/.config/systemd/user/daily-llama-server.service"
