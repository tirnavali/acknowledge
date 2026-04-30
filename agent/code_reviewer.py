"""
code_reviewer.py — Agentic code improvement from live performance logs.

Reads the last N hours of acknowledge.jsonl, identifies operations that
exceeded performance baselines, maps them to the exact source files and
methods responsible, then calls `claude --print` with full code context
to generate specific, actionable improvement suggestions.

Output is saved to logs/code_review_YYYYMMDD_HH.md

Usage:
    python agent/code_reviewer.py              # review last 1 hour
    python agent/code_reviewer.py --hours 8    # review last 8 hours
    python agent/code_reviewer.py --apply      # let Claude edit files directly

Environment (agent/.env or system):
    REVIEW_HOURS   Hours of logs to analyse (default: 1)
    CLAUDE_PATH    Path to claude executable (default: claude)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

PROJECT_ROOT = Path(__file__).parent.parent
LOG_FILE     = PROJECT_ROOT / "logs" / "acknowledge.jsonl"
REVIEW_DIR   = PROJECT_ROOT / "logs"
CLAUDE_PATH  = os.environ.get("CLAUDE_PATH", "claude")


# ---------------------------------------------------------------------------
# Performance baselines  (warn_ms = flag in report, crit_ms = priority fix)
# ---------------------------------------------------------------------------

BASELINES: dict[str, dict] = {
    "IMAGE_LOAD":          {"warn_ms": 1500,  "crit_ms": 4000},
    "FACE_DETECT":         {"warn_ms": 3000,  "crit_ms": 7000},
    "GALLERY_LOAD":        {"warn_ms": 800,   "crit_ms": 2000},
    "THUMBNAIL_GEN":       {"warn_ms": 400,   "crit_ms": 1500},
    "GALLERY_FILTER":      {"warn_ms": 150,   "crit_ms": 400},
    "GALLERY_SEARCH_DONE": {"warn_ms": 3000,  "crit_ms": 8000},
    "CAPTION_RESULT":      {"warn_ms": 12000, "crit_ms": 25000},
    "MODEL_LOAD_UI":       {"warn_ms": 75000, "crit_ms": 150000},
    "FACE_BATCH_COMPLETE": {"warn_ms": 30000, "crit_ms": 120000},
}


# ---------------------------------------------------------------------------
# Event → source file mapping
# Each entry: (relative_path, description_of_relevant_code)
# ---------------------------------------------------------------------------

EVENT_CODE_MAP: dict[str, list[tuple[str, str]]] = {
    "IMAGE_LOAD": [
        ("single_view_widget.py",
         "ImageLoaderWorker.run() reads file bytes, set_image() starts the loader, "
         "_on_image_loaded() converts QImage→QPixmap on the UI thread"),
    ],
    "FACE_DETECT": [
        ("src/services/face_analysis_service.py",
         "FaceAnalysisService.detect() — the insightface inference call inside the threading.Lock"),
        ("single_view_widget.py",
         "_start_detection() spawns the worker, _on_detection_finished() processes results "
         "including per-face similarity search loop"),
    ],
    "FACE_DB_HIT": [
        ("single_view_widget.py",
         "_on_image_loaded() DB-first branch: get_faces_for_media() + _show_db_faces()"),
        ("src/services/face_service.py",
         "get_faces_for_media() — the DB query that loads face records"),
    ],
    "GALLERY_LOAD": [
        ("app.py",
         "on_event_card_clicked() — get_gallery_items() call + GalleryItemModel init + start_loading()"),
        ("src/services/media_service.py",
         "get_gallery_items() — DB query that fetches all media rows for an event"),
    ],
    "THUMBNAIL_GEN": [
        ("gallery_item_model.py",
         "GalleryItemRunnable.run() — load_from_file() + generate_pixmap(); "
         "generate_pixmap() checks .thumbnails/ cache then falls back to Pillow resize"),
    ],
    "GALLERY_FILTER": [
        ("gallery_item_model.py",
         "filterAcceptsRow() called for every row on every keystroke; "
         "_calculate_score() computes relevance per keyword per item"),
    ],
    "GALLERY_SEARCH_DONE": [
        ("app.py",
         "on_gallery_search() all-events branch — SearchWorker, _on_search_finished()"),
        ("src/services/media_service.py",
         "search_across_events() and raw_search() — the SQL full-text search queries"),
    ],
    "CAPTION_RESULT": [
        ("src/services/caption_service.py",
         "_run_prompt() — the torch.no_grad generate() call; "
         "_prepare_image() resizes before inference"),
    ],
    "MODEL_LOAD_UI": [
        ("caption_tab_widget.py",
         "_start_model_load() → ModelLoadWorker → CaptionService._load_model()"),
        ("src/services/caption_service.py",
         "_load_model() — from_pretrained() + .to('cuda') — the cold-start cost"),
    ],
    "CAPTION_BATCH_UI": [
        ("caption_tab_widget.py",
         "BatchCaptionWorker.run() — sequential loop, no parallelism"),
        ("app.py",
         "BackgroundCaptionWorker.run() — the main-window caption batch worker"),
    ],
    "FACE_BATCH_COMPLETE": [
        ("app.py",
         "BatchFaceWorker.run() — face detection loop, IPTC extraction, similarity search per face"),
    ],
}


# ---------------------------------------------------------------------------
# Log reader (reused from report_agent pattern)
# ---------------------------------------------------------------------------

def read_recent_records(hours: int) -> list[dict]:
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
# Analysis — find which events are outside baselines
# ---------------------------------------------------------------------------

def _pct(values: list[int], p: int) -> int:
    if not values:
        return 0
    s = sorted(values)
    return s[max(0, int(len(s) * p / 100) - 1)]


def analyse(records: list[dict]) -> dict:
    durations: defaultdict[str, list[int]] = defaultdict(list)
    errors: defaultdict[str, list[str]] = defaultdict(list)
    event_counts: Counter = Counter()
    level_counts: Counter = Counter()

    for rec in records:
        event = rec.get("event")
        level = rec.get("level", "UNKNOWN")
        level_counts[level] += 1
        if event:
            event_counts[event] += 1
        dur = rec.get("duration_ms")
        if dur is not None and event:
            durations[event].append(int(dur))
        if level in ("ERROR", "CRITICAL"):
            errors[event or "general"].append(rec.get("msg", "")[:300])

    # Find events that breach baselines
    performance_findings: list[dict] = []
    for event, baseline in BASELINES.items():
        vals = durations.get(event, [])
        if not vals:
            continue
        avg = round(sum(vals) / len(vals))
        p95 = _pct(vals, 95)
        mx  = max(vals)
        severity = None
        if p95 >= baseline["crit_ms"]:
            severity = "CRITICAL"
        elif p95 >= baseline["warn_ms"]:
            severity = "WARNING"
        if severity:
            performance_findings.append({
                "event":    event,
                "severity": severity,
                "count":    len(vals),
                "avg_ms":   avg,
                "p95_ms":   p95,
                "max_ms":   mx,
                "warn_ms":  baseline["warn_ms"],
                "crit_ms":  baseline["crit_ms"],
                "files":    EVENT_CODE_MAP.get(event, []),
            })

    performance_findings.sort(key=lambda x: (x["severity"] != "CRITICAL", x["p95_ms"] * -1))

    return {
        "period_hours": hours,
        "total_records": len(records),
        "level_counts": dict(level_counts),
        "event_counts": dict(event_counts),
        "performance_findings": performance_findings,
        "errors": {k: v[:5] for k, v in errors.items() if v},
    }


# ---------------------------------------------------------------------------
# Code reader — read relevant source sections
# ---------------------------------------------------------------------------

def read_source_section(rel_path: str, max_lines: int = 200) -> str:
    full = PROJECT_ROOT / rel_path
    if not full.exists():
        return f"[file not found: {rel_path}]"
    text = full.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        # Include first 20 lines (imports/class def) + last (max_lines-20) lines
        head = lines[:20]
        tail = lines[-(max_lines - 20):]
        return "\n".join(head) + f"\n\n... ({len(lines) - max_lines} lines omitted) ...\n\n" + "\n".join(tail)
    return text


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(analysis: dict, hours: int, apply_mode: bool) -> str:
    findings = analysis["performance_findings"]
    errors   = analysis["errors"]

    if not findings and not errors:
        return ""  # nothing to review

    lines = [
        "You are a senior Python/PySide6 engineer reviewing the Acknowledge app.",
        f"The following performance and error data comes from {hours} hour(s) of live usage logs.",
        "",
        "## Performance findings (p95 latency vs baseline)",
        "",
    ]

    # List all findings
    for f in findings:
        lines.append(
            f"### [{f['severity']}] {f['event']}"
            f"  —  p95={f['p95_ms']}ms  avg={f['avg_ms']}ms  max={f['max_ms']}ms"
            f"  (baseline warn={f['warn_ms']}ms  crit={f['crit_ms']}ms)"
            f"  n={f['count']}"
        )
        for rel_path, desc in f["files"]:
            lines.append(f"  Relevant code: `{rel_path}` — {desc}")
        lines.append("")

    # Error summary
    if errors:
        lines += ["## Error summary", ""]
        for etype, msgs in errors.items():
            lines.append(f"**{etype}** ({len(msgs)} occurrences):")
            for m in msgs[:3]:
                lines.append(f"  - {m}")
        lines.append("")

    # Attach source code for every file mentioned in findings
    seen_files: set[str] = set()
    for f in findings:
        for rel_path, _ in f["files"]:
            if rel_path not in seen_files:
                seen_files.add(rel_path)

    if seen_files:
        lines += ["## Source code of relevant files", ""]
        for rel_path in sorted(seen_files):
            lines.append(f"### {rel_path}")
            lines.append("```python")
            lines.append(read_source_section(rel_path))
            lines.append("```")
            lines.append("")

    # Task
    if apply_mode:
        lines += [
            "## Your task",
            "",
            "For each CRITICAL finding, and the highest-severity WARNING finding:",
            "1. Identify the exact bottleneck in the source code shown above.",
            "2. Edit the file directly to fix it.",
            "3. Keep changes minimal — fix the specific performance issue only.",
            "4. After editing, briefly explain what you changed and why it helps.",
            "",
            "Start with the most critical issue first.",
        ]
    else:
        lines += [
            "## Your task",
            "",
            "For each finding (CRITICAL first, then WARNING):",
            "1. Identify the exact bottleneck in the source code shown above.",
            "2. Write the improved code as a diff or complete replacement.",
            "3. Explain in one sentence why your change fixes the specific metric.",
            "",
            "Be concrete — reference line numbers and function names. No generic advice.",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Call claude CLI
# ---------------------------------------------------------------------------

def call_claude(prompt: str, apply_mode: bool) -> str | None:
    cmd = [CLAUDE_PATH, "--print"]
    if apply_mode:
        # apply mode: allow file edits but run in the project directory
        cmd = [CLAUDE_PATH, "--print", "--dangerously-skip-permissions"]

    try:
        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=300,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0 and result.stderr:
            print(f"[reviewer] claude stderr: {result.stderr[:500]}", file=sys.stderr)
        return result.stdout.strip() if result.stdout.strip() else None
    except FileNotFoundError:
        print(
            f"[reviewer] '{CLAUDE_PATH}' not found. "
            "Make sure Claude Code CLI is installed and in PATH.\n"
            "Install: https://claude.ai/download",
            file=sys.stderr,
        )
        return None
    except subprocess.TimeoutExpired:
        print("[reviewer] Claude timed out after 5 minutes.", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Save output
# ---------------------------------------------------------------------------

def save_review(content: str, analysis: dict) -> Path:
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    path = REVIEW_DIR / f"code_review_{ts}.md"

    findings = analysis["performance_findings"]
    severity_tag = "OK"
    if any(f["severity"] == "CRITICAL" for f in findings):
        severity_tag = "CRITICAL"
    elif findings:
        severity_tag = "WARNING"

    header = "\n".join([
        f"# Code Review — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Period**: last {analysis['period_hours']}h  "
        f"**Records**: {analysis['total_records']}  "
        f"**Status**: {severity_tag}",
        "",
        "## Performance findings",
        "",
    ])
    for f in findings:
        header += (
            f"- [{f['severity']}] **{f['event']}** — "
            f"p95={f['p95_ms']}ms avg={f['avg_ms']}ms (baseline {f['warn_ms']}ms)\n"
        )

    if analysis["errors"]:
        header += "\n## Errors\n\n"
        for etype, msgs in analysis["errors"].items():
            header += f"- **{etype}**: {len(msgs)} occurrence(s)\n"

    header += "\n---\n\n## Claude Code Suggestions\n\n"
    path.write_text(header + content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Force UTF-8 on Windows console so Unicode in Claude's response prints cleanly
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Agentic code reviewer for Acknowledge app")
    parser.add_argument("--hours", type=int, default=int(os.environ.get("REVIEW_HOURS", "1")),
                        help="Hours of logs to analyse (default: 1)")
    parser.add_argument("--apply", action="store_true",
                        help="Let Claude edit source files directly (use with caution)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the prompt that would be sent to Claude, then exit")
    args = parser.parse_args()

    global hours
    hours = args.hours

    print(f"[reviewer] Reading last {hours}h of logs from {LOG_FILE}")
    records = read_recent_records(hours)
    print(f"[reviewer] {len(records)} records found")

    if not records:
        print("[reviewer] No log data yet — run the Acknowledge app first to generate logs.")
        return

    analysis = analyse(records)
    findings = analysis["performance_findings"]

    if not findings and not analysis["errors"]:
        print("[reviewer] All operations within baselines. No suggestions needed.")
        # Still write a clean report
        out = REVIEW_DIR / f"code_review_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        out.write_text(
            f"# Code Review — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"All {len(records)} operations within performance baselines. ✅\n",
            encoding="utf-8",
        )
        print(f"[reviewer] Clean report saved to {out}")
        return

    print(f"[reviewer] Found {len(findings)} performance finding(s):")
    for f in findings:
        print(f"  [{f['severity']:8s}] {f['event']} — p95={f['p95_ms']}ms (baseline {f['warn_ms']}ms)")

    prompt = build_prompt(analysis, hours, args.apply)

    if args.dry_run:
        print("\n" + "=" * 60 + " PROMPT " + "=" * 60)
        print(prompt[:3000] + ("\n... (truncated)" if len(prompt) > 3000 else ""))
        return

    mode_label = "apply (will edit files)" if args.apply else "suggest (analysis only)"
    print(f"[reviewer] Calling claude --print [{mode_label}] ...")

    response = call_claude(prompt, args.apply)

    if response:
        out_path = save_review(response, analysis)
        print(f"[reviewer] Review saved to {out_path}")
        # Print summary to stdout
        print("\n" + "=" * 70)
        print(response[:1500])
        if len(response) > 1500:
            print(f"\n... (full review in {out_path})")
    else:
        print("[reviewer] No response from Claude. Check that Claude Code CLI is installed.")
        print(f"  Try running manually:  claude --print < agent/last_prompt.txt")
        # Save the prompt for manual use
        prompt_path = PROJECT_ROOT / "agent" / "last_prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        print(f"  Prompt saved to: {prompt_path}")


if __name__ == "__main__":
    main()
