"""
Health collector for The Daily Llama.

Gathers server health data: hermes doctor, systemd service statuses,
disk usage, OpenRouter spend, and DeepInfra spend (manual-dashboard).

Section reference: 5.1–5.5, 1.1 stack_health schema.
"""

import json
import os
import re
import shutil
import subprocess
import urllib.request
from datetime import datetime, timezone


def collect_health():
    """Return the stack_health dict for feed.json.

    Keys: hermes_doctor, services, disk, openrouter_spend, deepinfra_spend.
    """
    return {
        "hermes_doctor": _collect_hermes_doctor(),
        "services": _collect_service_status(),
        "disk": _collect_disk(),
        "openrouter_spend": _collect_openrouter_spend(),
        "deepinfra_spend": _collect_deepinfra_spend(),
    }


# ---------------------------------------------------------------------------
# 5.1  hermes doctor
# ---------------------------------------------------------------------------

# Items to ignore per architecture plan 5.1 (from 02_hermes_config.md).
IGNORED_DOCTOR_ITEMS = {
    "tinker-atropos", "homeassistant", "image_gen", "rl",
    "discord", "discord_admin",
    "gemini-oauth", "codex-cli", "minimax-oauth", "nous-portal",
    "browser-cdp", "computer_use", "hermes-yuanbao", "spotify",
}


def _collect_hermes_doctor():
    """Run 'hermes doctor --json' and parse results.

    Falls back to plain-text regex parsing if --json is not supported.
    Returns {status, red_count, yellow_count, green_count, notable_items}.
    """
    try:
        result = subprocess.run(
            ["hermes", "doctor", "--json"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "HOME": os.path.expanduser("~")},
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_doctor_json(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: try plain-text output.
    try:
        result = subprocess.run(
            ["hermes", "doctor"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "HOME": os.path.expanduser("~")},
        )
        if result.returncode == 0 and result.stdout.strip():
            return _parse_doctor_text(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return {
        "status": "unknown",
        "red_count": 0,
        "yellow_count": 0,
        "green_count": 0,
        "notable_items": ["hermes doctor unavailable"],
    }


def _parse_doctor_json(raw):
    """Parse hermes doctor --json output."""
    red, yellow, green = 0, 0, 0
    notable = []
    try:
        data = json.loads(raw)
        checks = data.get("checks", []) if isinstance(data, dict) else []
        for check in checks:
            name = check.get("name", "").lower()
            status = check.get("status", "unknown")
            # Filter ignored items.
            skip = False
            for ign in IGNORED_DOCTOR_ITEMS:
                if ign in name:
                    skip = True
                    break
            if skip:
                continue
            if status == "red":
                red += 1
            elif status == "yellow":
                yellow += 1
            elif status == "green":
                green += 1
    except (json.JSONDecodeError, TypeError):
        pass

    overall = "red" if red > 0 else ("yellow" if yellow > 0 else "green")
    return {
        "status": overall,
        "red_count": red,
        "yellow_count": yellow,
        "green_count": green,
        "notable_items": notable,
    }


def _parse_doctor_text(raw):
    """Fallback: parse plain-text hermes doctor output with regex."""
    red = len(re.findall(r"❌|FAIL|red", raw, re.IGNORECASE))
    yellow = len(re.findall(r"⚠️|WARN|yellow", raw, re.IGNORECASE))
    green = len(re.findall(r"✅|PASS|green", raw, re.IGNORECASE))
    overall = "red" if red > 0 else ("yellow" if yellow > 0 else "green")
    return {
        "status": overall,
        "red_count": red,
        "yellow_count": yellow,
        "green_count": green,
        "notable_items": [],
    }


# ---------------------------------------------------------------------------
# 5.2  systemd service statuses
# ---------------------------------------------------------------------------

SERVICES = ["hermes-gateway", "hermes-webui", "llama-compression"]


def _collect_service_status():
    results = []
    for svc in SERVICES:
        status, detail = _check_service(svc)
        results.append({"name": svc, "status": status, "detail": detail})
    return results


def _check_service(name):
    """Check whether a systemd service is active.

    Tries --user first for hermes-* services, then system scope.
    llama-compression is a system service and may require sudo.
    """
    # Try user scope first.
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", name],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout.strip()
        if out == "active":
            return ("green", "active (running)")
        if out == "inactive":
            return ("red", "inactive")
        if out:
            return ("yellow", out)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Try system scope.
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=5,
        )
        out = r.stdout.strip()
        if out == "active":
            return ("green", "active (running)")
        if out in ("inactive", "unknown"):
            return ("red", out if out else "unknown")
        return ("yellow", out)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return ("unknown", "could not check")


# ---------------------------------------------------------------------------
# 5.3  disk usage
# ---------------------------------------------------------------------------


def _collect_disk():
    results = []
    for path in ["/", "/home/shawnz/models"]:
        try:
            usage = shutil.disk_usage(path)
            total_gb = round(usage.total / (1024**3))
            used_gb = round(usage.used / (1024**3))
            free_gb = round(usage.free / (1024**3))
            pct = round((usage.used / usage.total) * 100)
            status = "red" if pct > 90 else ("yellow" if pct > 75 else "green")
            results.append(
                {
                    "mount": path,
                    "total_gb": total_gb,
                    "used_gb": used_gb,
                    "free_gb": free_gb,
                    "pct_used": pct,
                    "status": status,
                }
            )
        except OSError:
            results.append(
                {
                    "mount": path,
                    "total_gb": 0,
                    "used_gb": 0,
                    "free_gb": 0,
                    "pct_used": 0,
                    "status": "unknown",
                }
            )
    return results


# ---------------------------------------------------------------------------
# 5.4  OpenRouter spend
# ---------------------------------------------------------------------------

OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
SPEND_LOG_PATH = "/home/shawnz/site-data/logs/openrouter_spend.jsonl"


def _collect_openrouter_spend():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "status": "no_key",
            "spend_24h": None,
            "spend_7d": None,
            "currency": "USD",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "message": "OPENROUTER_API_KEY not set",
        }

    now = datetime.now(timezone.utc)
    try:
        req = urllib.request.Request(
            OPENROUTER_CREDITS_URL,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        return {
            "status": "error",
            "spend_24h": None,
            "spend_7d": None,
            "currency": "USD",
            "fetched_at": now.isoformat(),
            "message": str(e),
        }

    usage_24h = data.get("data", {}).get("usage_last_24h", 0)
    total_usage = data.get("data", {}).get("total_usage", 0)

    # Append today's snapshot.
    os.makedirs(os.path.dirname(SPEND_LOG_PATH), exist_ok=True)
    snapshot = json.dumps(
        {
            "date": now.strftime("%Y-%m-%d"),
            "total_usage": total_usage,
            "fetched_at": now.isoformat(),
        }
    )
    try:
        with open(SPEND_LOG_PATH, "a") as f:
            f.write(snapshot + "\n")
    except OSError:
        pass

    # Compute rolling 7d from local snapshots.
    spend_7d = _compute_rolling_7d()

    return {
        "status": "ok",
        "spend_24h": usage_24h,
        "spend_7d": spend_7d,
        "currency": "USD",
        "fetched_at": now.isoformat(),
    }


def _compute_rolling_7d():
    """Compute 7-day spend from daily snapshots in SPEND_LOG_PATH."""
    if not os.path.isfile(SPEND_LOG_PATH):
        return None
    snapshots = []
    try:
        with open(SPEND_LOG_PATH, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    snapshots.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return None

    if len(snapshots) < 2:
        return None
    # Take earliest vs latest within last 7 entries.
    recent = snapshots[-7:]
    if len(recent) < 2:
        return None
    return round(recent[-1]["total_usage"] - recent[0]["total_usage"], 2)


# ---------------------------------------------------------------------------
# 5.5  DeepInfra spend
# ---------------------------------------------------------------------------


def _collect_deepinfra_spend():
    return {
        "status": "see_dashboard",
        "message": "DeepInfra spend must be checked manually.",
        "dashboard_url": "https://deepinfra.ai/dashboard",
    }
