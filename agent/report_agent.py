"""
Hourly monitoring agent for the Acknowledge app.

Reads logs/acknowledge.jsonl, aggregates the last hour of events,
asks Ollama (qwen2.5:7b) to generate a plain-English status report,
then emails it via SendGrid.

Falls back to writing a .txt file if Ollama or SendGrid is unavailable.

Usage:
    python agent/report_agent.py

Environment variables (in agent/.env or system env):
    SENDGRID_API_KEY   - SendGrid API key (SG.xxx)
    REPORT_TO_EMAIL    - recipient address
    REPORT_FROM_EMAIL  - verified sender address in SendGrid
    OLLAMA_MODEL       - model name (default: qwen2.5:7b)
    OLLAMA_URL         - Ollama base URL (default: http://localhost:11434)
    LOG_HOURS          - how many hours of logs to read (default: 1)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Load .env from agent directory if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "")
REPORT_TO_EMAIL = os.environ.get("REPORT_TO_EMAIL", "tran.ce.co@gmail.com")
REPORT_FROM_EMAIL = os.environ.get("REPORT_FROM_EMAIL", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
LOG_HOURS = int(os.environ.get("LOG_HOURS", "1"))

LOG_FILE = Path(__file__).parent.parent / "logs" / "acknowledge.jsonl"
REPORT_DIR = Path(__file__).parent.parent / "logs"


# ---------------------------------------------------------------------------
# Log ingestion
# ---------------------------------------------------------------------------

def read_recent_records(hours: int) -> list[dict]:
    """Read log records from the last `hours` hours."""
    if not LOG_FILE.exists():
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    records = []
    with LOG_FILE.open(encoding="utf-8") as fh:
        for line in fh:
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
                continue
            if ts >= cutoff:
                records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate(records: list[dict]) -> dict:
    level_counts: Counter = Counter()
    event_counts: Counter = Counter()
    errors: list[str] = []
    durations: defaultdict[str, list[int]] = defaultdict(list)

    for rec in records:
        level_counts[rec.get("level", "UNKNOWN")] += 1
        event = rec.get("event")
        if event:
            event_counts[event] += 1
        if rec.get("level") in ("ERROR", "CRITICAL"):
            errors.append(rec.get("msg", "")[:200])
        dur = rec.get("duration_ms")
        if dur is not None and event:
            durations[event].append(int(dur))

    avg_durations = {
        evt: round(sum(vals) / len(vals))
        for evt, vals in durations.items()
    }

    return {
        "period_hours": LOG_HOURS,
        "total_records": len(records),
        "level_counts": dict(level_counts),
        "event_counts": dict(event_counts),
        "avg_duration_ms": avg_durations,
        "recent_errors": errors[:10],
    }


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

PROMPT_TEMPLATE = """\
You are a monitoring agent for a photo archiving desktop app called Acknowledge.
The app does: media import, face detection (InsightFace), AI captioning (Qwen2.5-VL).

Here is a structured log summary from the last {hours} hour(s):
{summary}

Write a concise status report (under 200 words) covering:
- What the app did (face detection batches, captioning batches, events imported)
- Any errors or unusually slow operations worth noting
- Overall health verdict: OK / WARNING / CRITICAL

Be direct and specific. No padding."""


def call_ollama(summary: dict) -> str | None:
    try:
        import urllib.request
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": PROMPT_TEMPLATE.format(
                hours=LOG_HOURS,
                summary=json.dumps(summary, ensure_ascii=False, indent=2),
            ),
            "stream": False,
        }).encode()
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except Exception as exc:
        print(f"[agent] Ollama unavailable: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# SendGrid email
# ---------------------------------------------------------------------------

def send_email(subject: str, body: str) -> bool:
    if not SENDGRID_API_KEY or not REPORT_FROM_EMAIL:
        print("[agent] SendGrid not configured — skipping email.", file=sys.stderr)
        return False
    try:
        import urllib.request
        payload = json.dumps({
            "personalizations": [{"to": [{"email": REPORT_TO_EMAIL}]}],
            "from": {"email": REPORT_FROM_EMAIL},
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
            if resp.status in (200, 202):
                print(f"[agent] Email sent to {REPORT_TO_EMAIL}")
                return True
            print(f"[agent] SendGrid returned {resp.status}", file=sys.stderr)
            return False
    except Exception as exc:
        print(f"[agent] Email send failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Fallback: write to file
# ---------------------------------------------------------------------------

def save_report_to_file(body: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = REPORT_DIR / f"report_{ts}.txt"
    path.write_text(body, encoding="utf-8")
    print(f"[agent] Report saved to {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"[agent] Running hourly report for period ending {now}")

    records = read_recent_records(LOG_HOURS)
    print(f"[agent] {len(records)} log records in the last {LOG_HOURS}h")

    summary = aggregate(records)

    if not records:
        report_text = (
            f"Acknowledge App — Hourly Report ({now})\n"
            "No log records found for this period. "
            "The app may not have been running, or logging is not yet active."
        )
    else:
        llm_text = call_ollama(summary)
        if llm_text:
            report_text = (
                f"Acknowledge App — Hourly Report ({now})\n"
                f"Period: last {LOG_HOURS}h | Records: {summary['total_records']}\n\n"
                f"{llm_text}\n\n"
                f"--- Raw stats ---\n{json.dumps(summary, indent=2, ensure_ascii=False)}"
            )
        else:
            # Ollama unavailable — format a plain stats report
            lines = [
                f"Acknowledge App — Hourly Report ({now})",
                f"Period: last {LOG_HOURS}h | Records: {summary['total_records']}",
                "",
                "Log levels:",
            ]
            for lvl, cnt in sorted(summary["level_counts"].items()):
                lines.append(f"  {lvl}: {cnt}")
            lines.append("")
            lines.append("Events:")
            for evt, cnt in sorted(summary["event_counts"].items(), key=lambda x: -x[1]):
                avg = summary["avg_duration_ms"].get(evt)
                suffix = f"  (avg {avg}ms)" if avg else ""
                lines.append(f"  {evt}: {cnt}{suffix}")
            if summary["recent_errors"]:
                lines.append("")
                lines.append("Recent errors:")
                for err in summary["recent_errors"]:
                    lines.append(f"  - {err}")
            lines.append("\n[Ollama was unavailable — narrative summary skipped]")
            report_text = "\n".join(lines)

    print("\n" + report_text + "\n")

    subject = f"Acknowledge Report {now}"
    sent = send_email(subject, report_text)
    if not sent:
        save_report_to_file(report_text)


if __name__ == "__main__":
    main()
