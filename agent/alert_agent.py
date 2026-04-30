"""
alert_agent.py — Tier 1 reactive monitor for the Acknowledge app.

Tails logs/acknowledge.jsonl in a polling loop (no external deps — pure
stdlib). Rule-based, no LLM: fires an email the moment a threshold is
crossed, then enforces per-rule cooldown so your inbox stays clean.

Run at system startup via Windows Task Scheduler (alert_schedule_task.xml).
This process runs indefinitely — it does not exit on its own.

Environment variables (agent/.env or system env):
    SENDGRID_API_KEY      SendGrid API key
    REPORT_TO_EMAIL       Alert recipient address
    REPORT_FROM_EMAIL     Verified SendGrid sender address
    ALERT_POLL_SECONDS    How often to check the log (default: 30)
    ALERT_COOLDOWN_MIN    Min minutes between same-rule firings (default: 60)
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — load agent/.env then fall back to system env
# ---------------------------------------------------------------------------

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
ALERT_TO_EMAIL   = os.environ.get("REPORT_TO_EMAIL", "tran.ce.co@gmail.com")
ALERT_FROM_EMAIL = os.environ.get("REPORT_FROM_EMAIL", "")
POLL_INTERVAL    = int(os.environ.get("ALERT_POLL_SECONDS", "30"))
COOLDOWN_MIN     = int(os.environ.get("ALERT_COOLDOWN_MIN", "60"))

LOG_FILE         = Path(__file__).parent.parent / "logs" / "acknowledge.jsonl"
STATE_FILE       = Path(__file__).parent / ".alert_state.json"


# ---------------------------------------------------------------------------
# Rule helpers
# ---------------------------------------------------------------------------

def _ev(name: str):
    return lambda r: r.get("event") == name

def _lvl(name: str):
    return lambda r: r.get("level") == name

def _msg(text: str):
    return lambda r: text.lower() in r.get("msg", "").lower()

def _all(*fns):
    return lambda r: all(f(r) for f in fns)


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------
# threshold=1, window_min=0  →  fires on the very first match in each poll
# threshold=N, window_min=M  →  fires when N matches accumulate inside M minutes

RULES: list[dict] = [
    {
        "id":        "model_load_error",
        "match":     _ev("MODEL_LOAD_ERROR"),
        "threshold": 1,
        "window_min": 0,
        "subject":   "🔴 Acknowledge: Caption Model Failed to Load",
        "detail": (
            "The Qwen2.5-VL caption model failed to load.\n"
            "Captioning is disabled until the app is restarted.\n\n"
            "Possible causes:\n"
            "  • GPU out of memory (check nvidia-smi)\n"
            "  • Corrupted model files in src/models/\n"
            "  • CUDA / PyTorch version mismatch"
        ),
    },
    {
        "id":        "face_detect_error_spike",
        "match":     _ev("FACE_DETECT_ERROR"),
        "threshold": 3,
        "window_min": 10,
        "subject":   "🟡 Acknowledge: Face Detection Error Spike (3+ in 10 min)",
        "detail": (
            "3 or more face detection errors occurred within 10 minutes.\n\n"
            "Possible causes:\n"
            "  • GPU memory pressure from concurrent captioning\n"
            "  • Corrupt or unsupported image files\n"
            "  • InsightFace buffalo_l model not fully downloaded\n"
            "  • ONNX Runtime provider mismatch"
        ),
    },
    {
        "id":        "error_spike",
        "match":     _lvl("ERROR"),
        "threshold": 5,
        "window_min": 5,
        "subject":   "🔴 Acknowledge: Error Spike (5+ errors in 5 min)",
        "detail": (
            "5 or more ERROR-level log entries appeared within 5 minutes.\n"
            "The application may be in a degraded state.\n\n"
            "Check the full log at:\n"
            f"  {LOG_FILE}"
        ),
    },
    {
        "id":        "critical_any",
        "match":     _lvl("CRITICAL"),
        "threshold": 1,
        "window_min": 0,
        "subject":   "🚨 Acknowledge: CRITICAL Error",
        "detail":    "A CRITICAL-level error occurred. Immediate attention required.",
    },
    {
        "id":        "db_errors",
        "match":     _all(
            _lvl("ERROR"),
            lambda r: any(
                kw in r.get("msg", "").lower()
                for kw in ("veritabanı", "database", "sqlalchemy", "psycopg", "connection refused")
            ),
        ),
        "threshold": 2,
        "window_min": 3,
        "subject":   "🔴 Acknowledge: Database Connection Errors",
        "detail": (
            "2+ database errors detected within 3 minutes.\n\n"
            "Action: verify Docker Desktop is running and the PostgreSQL\n"
            "container is healthy:\n\n"
            "  docker-compose up -d\n"
            "  docker ps\n\n"
            "If the container is running, check its logs:\n"
            "  docker logs acknowledge_db"
        ),
    },
    {
        "id":        "thumbnail_failure_spike",
        "match":     _all(_ev("THUMBNAIL_GEN"), _lvl("WARNING")),
        "threshold": 10,
        "window_min": 5,
        "subject":   "🟡 Acknowledge: Thumbnail Generation Failures",
        "detail": (
            "10+ thumbnail generation warnings in 5 minutes.\n\n"
            "Possible causes:\n"
            "  • Disk full — check free space on vault drive\n"
            "  • Vault directory was moved or is inaccessible\n"
            "  • Image files are corrupt or in an unsupported format"
        ),
    },
    {
        "id":        "caption_json_parse_failures",
        "match":     _msg("json parse failed"),
        "threshold": 5,
        "window_min": 15,
        "subject":   "🟡 Acknowledge: Caption Model Giving Bad Output",
        "detail": (
            "5+ JSON parse failures from the caption model in 15 minutes.\n"
            "The model is returning malformed responses — caption quality\n"
            "is degraded.\n\n"
            "This often happens when GPU memory is constrained and generation\n"
            "is being truncated. Try restarting the app."
        ),
    },
    {
        "id":        "batch_face_errors",
        "match":     _msg("batchfaceworker: error"),
        "threshold": 5,
        "window_min": 10,
        "subject":   "🟡 Acknowledge: Batch Face Detection Errors",
        "detail": (
            "5+ batch face detection errors in 10 minutes.\n"
            "Some images in the current event may not have been processed."
        ),
    },
]


# ---------------------------------------------------------------------------
# Cooldown state  (persisted to disk so restarts don't re-fire old alerts)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[alert] Could not save state: {e}", file=sys.stderr)


def _is_cooling_down(state: dict, rule_id: str) -> bool:
    last = state.get(rule_id)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - last_dt < timedelta(minutes=COOLDOWN_MIN)
    except ValueError:
        return False


def _mark_fired(state: dict, rule_id: str) -> None:
    state[rule_id] = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Email delivery
# ---------------------------------------------------------------------------

def _send_alert(subject: str, body: str) -> bool:
    if not SENDGRID_API_KEY or not ALERT_FROM_EMAIL:
        _ts = datetime.now().strftime("%H:%M:%S")
        print(f"[alert {_ts}] (no email config) {subject}")
        return True  # treat as sent so cooldown still applies
    try:
        payload = json.dumps({
            "personalizations": [{"to": [{"email": ALERT_TO_EMAIL}]}],
            "from": {"email": ALERT_FROM_EMAIL},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        }).encode()
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=payload,
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = resp.status in (200, 202)
            if ok:
                print(f"[alert] ✉ Sent: {subject}")
            else:
                print(f"[alert] SendGrid HTTP {resp.status}", file=sys.stderr)
            return ok
    except Exception as exc:
        print(f"[alert] Email error: {exc}", file=sys.stderr)
        return False


def _build_email_body(rule: dict, matching: list[dict]) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        f"Acknowledge App — Alert",
        f"Time: {ts}",
        f"Rule: {rule['id']}",
        "=" * 60,
        "",
        rule["detail"],
        "",
        f"Triggered by {len(matching)} log record(s):",
        "",
    ]
    for rec in matching[-8:]:
        lines.append(f"  [{rec.get('ts', '?')[:19]}] {rec.get('level','?'):8s} {rec.get('msg','')[:100]}")
    lines += [
        "",
        f"Full log: {LOG_FILE}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Log tail — reads new bytes since last seek position
# ---------------------------------------------------------------------------

def _read_new_records(fh, target: list) -> None:
    while True:
        line = fh.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_str = rec.get("ts", "")
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            ts = datetime.now(timezone.utc)
        rec["_dt"] = ts
        target.append(rec)


# ---------------------------------------------------------------------------
# Rule evaluation against a time window
# ---------------------------------------------------------------------------

def _evaluate_rules(
    new_batch: list[dict],
    rolling: deque,
    state: dict,
) -> list[tuple[dict, list[dict]]]:
    now = datetime.now(timezone.utc)
    fires = []
    for rule in RULES:
        if _is_cooling_down(state, rule["id"]):
            continue
        window_min = rule["window_min"]
        if window_min == 0:
            pool = new_batch
        else:
            cutoff = now - timedelta(minutes=window_min)
            pool = [r for r in rolling if r["_dt"] >= cutoff]
        matching = [r for r in pool if rule["match"](r)]
        if len(matching) >= rule["threshold"]:
            fires.append((rule, matching))
    return fires


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[alert] Started at {ts}")
    print(f"[alert] Log file : {LOG_FILE}")
    print(f"[alert] Poll     : every {POLL_INTERVAL}s")
    print(f"[alert] Cooldown : {COOLDOWN_MIN} min per rule")
    print(f"[alert] Rules    : {len(RULES)} active")
    print(f"[alert] Email    : {'configured' if SENDGRID_API_KEY and ALERT_FROM_EMAIL else 'NOT configured (stdout only)'}")

    state = _load_state()
    rolling: deque[dict] = deque(maxlen=20_000)  # ~60 min of records at high throughput
    new_batch: list[dict] = []

    # Wait for log file (app may not have started yet)
    while not LOG_FILE.exists():
        print(f"[alert] Waiting for log file to appear...")
        time.sleep(POLL_INTERVAL)

    with LOG_FILE.open(encoding="utf-8", errors="replace") as fh:
        # Start from end of file — only react to future events
        fh.seek(0, 2)
        start_pos = fh.tell()
        print(f"[alert] Watching from log position {start_pos}")

        while True:
            time.sleep(POLL_INTERVAL)

            # Re-open check: if file was rotated, reopen
            try:
                current_size = LOG_FILE.stat().st_size
            except FileNotFoundError:
                print("[alert] Log file disappeared — waiting...")
                time.sleep(POLL_INTERVAL)
                continue

            if current_size < fh.tell():
                # File was truncated/rotated
                print("[alert] Log rotated — reopening")
                fh.seek(0)

            new_batch.clear()
            _read_new_records(fh, new_batch)

            if not new_batch:
                continue

            for rec in new_batch:
                rolling.append(rec)

            fires = _evaluate_rules(new_batch, rolling, state)
            for rule, matching in fires:
                body = _build_email_body(rule, matching)
                sent = _send_alert(rule["subject"], body)
                if sent:
                    _mark_fired(state, rule["id"])
                    _save_state(state)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[alert] Stopped by user.")
