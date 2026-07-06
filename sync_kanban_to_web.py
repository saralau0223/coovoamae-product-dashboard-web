#!/usr/bin/env python3
"""Export Hermes Kanban boards to a static GitHub Pages snapshot."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


PROFILE = "coovoamae-chief-of-staff"
HERMES = "/root/.local/bin/hermes"
ROOT = Path(__file__).resolve().parent
OUT = ROOT / "kanban_data.json"
TZ = timezone(timedelta(hours=8))
WEBROOT_DATA_TARGETS = [
    Path("/var/www/product-dashboard/kanban_data.json"),
    Path("/var/www/hermes-agent-board/kanban_data.json"),
]
FALLBACK_BOARDS = [
    {"slug": "default", "name": "Default", "counts": {}},
    {"slug": "coovoamae-design", "name": "COOVOAMAE Design Requests", "counts": {}},
    {"slug": "coovoamae-ads-manager-handoffs", "name": "COOVOAMAE Ads Manager Handoffs", "counts": {}},
    {"slug": "coovoamae-amazon-ops-handoffs", "name": "COOVOAMAE Amazon Ops Handoffs", "counts": {}},
    {"slug": "coovoamae-product-assets", "name": "COOVOAMAE Product Asset Handoffs", "counts": {}},
]


def run(args: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PATH"] = "/usr/local/lib/hermes-agent/venv/bin:/root/.local/bin:/root/.nvm/versions/node/v22.22.2/bin:/usr/local/bin:/usr/bin:/bin:" + env.get("PATH", "")
    proc = subprocess.run(args, cwd=str(cwd or ROOT), env=env, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc


def parse_counts(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for part in text.split(","):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        try:
            counts[key] = int(value)
        except ValueError:
            counts[key] = 0
    return counts


def list_boards() -> list[dict[str, Any]]:
    proc = run([HERMES, "--profile", PROFILE, "kanban", "boards", "list"])
    boards: list[dict[str, Any]] = []
    pattern = re.compile(r"^\s*(?:●\s*)?(?P<slug>\S+)\s+(?P<name>.*?)\s{2,}(?P<counts>[a-z]+=\d+.*)$")
    for line in proc.stdout.splitlines():
        if not line.strip() or "SLUG" in line or line.startswith("Current board") or line.startswith("Switch boards"):
            continue
        match = pattern.match(line.rstrip())
        if not match:
            continue
        boards.append({
            "slug": match.group("slug"),
            "name": match.group("name").strip(),
            "counts": parse_counts(match.group("counts")),
        })
    return boards or FALLBACK_BOARDS


def board_tasks(slug: str) -> list[dict[str, Any]]:
    proc = run([HERMES, "--profile", PROFILE, "kanban", "--board", slug, "list", "--json"])
    return json.loads(proc.stdout or "[]")


def as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def truncate(value: Any, limit: int = 300) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_task(task: dict[str, Any], board: dict[str, Any]) -> dict[str, Any]:
    created_at = as_int(task.get("created_at"))
    started_at = as_int(task.get("started_at"))
    completed_at = as_int(task.get("completed_at"))
    updated_at = max(created_at, started_at, completed_at)
    body = truncate(task.get("body"))
    return {
        "id": task.get("id"),
        "title": task.get("title") or task.get("id"),
        "status": task.get("status") or "unknown",
        "assignee": task.get("assignee") or "",
        "priority": task.get("priority"),
        "board": board["slug"],
        "board_name": board.get("name") or board["slug"],
        "created_by": task.get("created_by") or "",
        "created_at": created_at,
        "started_at": started_at or None,
        "completed_at": completed_at or None,
        "updated_at": updated_at or created_at,
        "body": body,
        "body_preview": body,
        "result": truncate(task.get("result")),
        "workspace_path": task.get("workspace_path") or "",
    }


def add_counts(target: dict[str, int], source: dict[str, int]) -> None:
    for key, value in source.items():
        target[key] = target.get(key, 0) + int(value or 0)


def build_snapshot() -> dict[str, Any]:
    now = datetime.now(TZ)
    boards = list_boards()
    all_tasks: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for board in boards:
        try:
            all_tasks.extend(normalize_task(task, board) for task in board_tasks(board["slug"]))
        except Exception as exc:  # noqa: BLE001 - keep one failed board from blocking the page
            errors.append({"board": board["slug"], "error": str(exc)})

    summary: dict[str, int] = {}
    for board in boards:
        add_counts(summary, board.get("counts") or {})
    for status in ("running", "ready", "todo", "triage", "pending", "blocked", "done", "archived"):
        summary.setdefault(status, 0)
    summary["active"] = sum(1 for task in all_tasks if task["status"] not in {"blocked", "done", "archived"})
    summary["total"] = sum(value for key, value in summary.items() if key not in {"total", "active"})

    by_agent: dict[str, dict[str, int]] = {}
    for task in all_tasks:
        agent = task["assignee"] or "unassigned"
        if agent not in by_agent:
            by_agent[agent] = {"total": 0, "active": 0, "blocked": 0, "done": 0, "running": 0}
        by_agent[agent]["total"] += 1
        by_agent[agent][task["status"]] = by_agent[agent].get(task["status"], 0) + 1
        if task["status"] not in {"blocked", "done", "archived"}:
            by_agent[agent]["active"] += 1

    blocked = sorted((task for task in all_tasks if task["status"] == "blocked"), key=lambda item: (-as_int(item["priority"]), -as_int(item["updated_at"])))
    active = sorted((task for task in all_tasks if task["status"] not in {"blocked", "done", "archived"}), key=lambda item: (-as_int(item["priority"]), -as_int(item["updated_at"])))
    recent_done = sorted((task for task in all_tasks if task["status"] == "done"), key=lambda item: -as_int(item["completed_at"] or item["updated_at"]))[:30]

    return {
        "ok": True,
        "generated_at": int(now.timestamp()),
        "generated_at_iso": now.isoformat(timespec="seconds"),
        "source": "Hermes Kanban static snapshot",
        "current_board": "default",
        "boards": boards,
        "summary": summary,
        "blocked": blocked,
        "active": active,
        "by_agent": by_agent,
        "recent_done": recent_done,
        "tasks": all_tasks,
        "errors": errors,
    }


def write_snapshot(snapshot: dict[str, Any]) -> None:
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(OUT)


def commit_and_push() -> None:
    run(["git", "config", "user.email", "sara@coovoamae.com"], check=False)
    run(["git", "config", "user.name", "Hermes Kanban Sync"], check=False)
    run(["git", "add", "kanban_data.json"])
    status = run(["git", "status", "--short", "--", "kanban_data.json"]).stdout.strip()
    if not status:
        print("kanban_data.json unchanged; no commit")
        return
    stamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M %z")
    run(["git", "commit", "-m", f"Sync kanban snapshot {stamp}"])
    push = run(["git", "push"], check=False)
    if push.returncode != 0:
        print(push.stdout, file=sys.stderr)
        print(push.stderr, file=sys.stderr)
        raise RuntimeError("git push failed")


def publish_snapshot_to_webroots() -> None:
    data = OUT.read_bytes()
    for target in WEBROOT_DATA_TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        target.chmod(0o644)


def main() -> int:
    try:
        snapshot = build_snapshot()
        write_snapshot(snapshot)
        print(
            "snapshot generated:",
            "boards=", len(snapshot["boards"]),
            "tasks=", len(snapshot["tasks"]),
            "blocked=", len(snapshot["blocked"]),
            "active=", len(snapshot["active"]),
            "errors=", len(snapshot["errors"]),
        )
        commit_and_push()
        publish_snapshot_to_webroots()
        return 0
    except Exception as exc:  # noqa: BLE001 - cron should log concise failure
        print(f"kanban sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
