"""
Kanban collector for The Daily Llama.

Reads recently completed and blocked tasks from the kanban SQLite
database and formats them as task_report entries for feed.json.

Section reference: 1.1 task_reports schema, 7.6 acceptance criteria.
"""

import os
import sqlite3
import time
from datetime import datetime, timezone


DB_PATH = "/home/shawnz/.hermes/kanban.db"
KANBAN_URL = "http://192.168.1.28:8090"

# Lookback window for recent task activity (seconds).
LOOKBACK_SECONDS = 24 * 3600


def collect_task_reports():
    """Return a list of task_report dicts for recent activity.

    Each dict:
        task_id, title, assignee, profile, status, completed_at (ISO str),
        summary, kanban_url

    Includes tasks completed within the last 24h AND blocked tasks
    with a block event in the last 24h.
    """
    if not os.path.isfile(DB_PATH):
        return []

    now_epoch = int(time.time())
    cutoff = now_epoch - LOOKBACK_SECONDS

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        # Completed tasks (completed_at is epochs in this DB).
        completed = conn.execute(
            """
            SELECT id, title, assignee, status, completed_at, result
            FROM tasks
            WHERE status = 'done' AND completed_at >= ?
            ORDER BY completed_at DESC
            """,
            (cutoff,),
        ).fetchall()

        # Blocked tasks with a recent block event.
        blocked = conn.execute(
            """
            SELECT t.id, t.title, t.assignee, t.status,
                   MAX(e.created_at) AS blocked_at
            FROM tasks t
            JOIN task_events e ON e.task_id = t.id
            WHERE t.status = 'blocked'
              AND e.kind = 'blocked'
              AND e.created_at >= ?
            GROUP BY t.id
            ORDER BY blocked_at DESC
            """,
            (cutoff,),
        ).fetchall()
    finally:
        conn.close()

    completed_reports = []

    for r in completed:
        completed_iso = (
            datetime.fromtimestamp(r["completed_at"], tz=timezone.utc).isoformat()
            if r["completed_at"]
            else None
        )
        completed_reports.append(
            {
                "task_id": r["id"],
                "title": r["title"],
                "assignee": r["assignee"] or "UNASSIGNED",
                "profile": r["assignee"] or "UNASSIGNED",
                "status": r["status"],
                "completed_at": completed_iso,
                "summary": r["result"] or "",
                "kanban_url": KANBAN_URL,
            }
        )

    blocked_reports = []

    for r in blocked:
        blocked_iso = (
            datetime.fromtimestamp(r["blocked_at"], tz=timezone.utc).isoformat()
            if r["blocked_at"]
            else None
        )
        blocked_reports.append(
            {
                "task_id": r["id"],
                "title": r["title"],
                "assignee": r["assignee"] or "UNASSIGNED",
                "profile": r["assignee"] or "UNASSIGNED",
                "status": "blocked",
                "completed_at": blocked_iso,
                "summary": "Task blocked — awaiting input",
                "kanban_url": KANBAN_URL,
            }
        )

    # Sort newest first per list (completed_at / blocked_at descending).
    completed_reports.sort(key=lambda r: r["completed_at"] or "", reverse=True)
    blocked_reports.sort(key=lambda r: r["completed_at"] or "", reverse=True)

    return {
        "completed": completed_reports,
        "blocked": blocked_reports,
        "running": [],
        "kanban_url": KANBAN_URL,
    }
