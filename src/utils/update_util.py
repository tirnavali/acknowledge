"""Utilities for checking and applying updates from the git remote."""

import subprocess
import sys
import os
import logging

logger = logging.getLogger(__name__)

_REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _git(*args, timeout=30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", _REPO_DIR] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )


def check_for_updates() -> tuple[bool, int, str]:
    """Fetch origin and check for new commits on the tracked upstream branch.

    Returns (update_available, commit_count, latest_sha).
    Returns (False, 0, "") on any error.
    """
    try:
        fetch = _git("fetch", "origin", timeout=15)
        if fetch.returncode != 0:
            logger.debug(f"git fetch failed: {fetch.stderr.strip()}")
            return False, 0, ""

        log = _git("log", "HEAD..@{u}", "--oneline")
        if log.returncode != 0:
            return False, 0, ""

        lines = [l for l in log.stdout.strip().splitlines() if l]
        if not lines:
            return False, 0, ""

        latest_sha = lines[0].split()[0]
        return True, len(lines), latest_sha
    except Exception as e:
        logger.debug(f"Update check error: {e}")
        return False, 0, ""


def requirements_changed() -> bool:
    """True if requirements.txt differs between HEAD and upstream."""
    try:
        result = _git("diff", "HEAD..@{u}", "--name-only", "--", "requirements.txt")
        return bool(result.stdout.strip())
    except Exception:
        return False


def apply_update() -> tuple[bool, str]:
    """Pull from upstream. Installs requirements if they changed.

    Returns (success, error_message).
    """
    try:
        needs_pip = requirements_changed()

        pull = _git("pull", "--ff-only", timeout=60)
        if pull.returncode != 0:
            return False, pull.stderr.strip() or pull.stdout.strip()

        if needs_pip:
            req_file = os.path.join(_REPO_DIR, "requirements.txt")
            pip = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", req_file, "-q"],
                capture_output=True, text=True, timeout=120,
            )
            if pip.returncode != 0:
                logger.warning(f"pip install failed after update: {pip.stderr.strip()}")

        return True, ""
    except subprocess.TimeoutExpired:
        return False, "İşlem zaman aşımına uğradı."
    except Exception as e:
        return False, str(e)


def restart_app():
    """Replace the current process with a fresh instance of the app."""
    os.execv(sys.executable, [sys.executable] + sys.argv)
