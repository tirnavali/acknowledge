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
            logger.warning(f"git fetch failed: {fetch.stderr.strip()}")
            return False, 0, ""

        # Get current branch name (e.g. master)
        branch_res = _git("rev-parse", "--abbrev-ref", "HEAD")
        if branch_res.returncode != 0:
            logger.warning(f"git rev-parse failed: {branch_res.stderr.strip()}")
            return False, 0, ""
        branch_name = branch_res.stdout.strip()

        # Try origin/<branch> comparison first, fallback to @{u} if it fails
        log = _git("log", f"HEAD..origin/{branch_name}", "--oneline")
        if log.returncode != 0:
            log = _git("log", "HEAD..@{u}", "--oneline")

        if log.returncode != 0:
            logger.warning(f"git log upstream check failed: {log.stderr.strip()}")
            return False, 0, ""

        lines = [l for l in log.stdout.strip().splitlines() if l]
        if not lines:
            return False, 0, ""

        latest_sha = lines[0].split()[0]
        return True, len(lines), latest_sha
    except Exception as e:
        logger.warning(f"Update check error: {e}")
        return False, 0, ""


def requirements_changed() -> bool:
    """True if requirements.txt differs between HEAD and upstream."""
    try:
        branch_res = _git("rev-parse", "--abbrev-ref", "HEAD")
        if branch_res.returncode == 0:
            branch_name = branch_res.stdout.strip()
            result = _git("diff", f"HEAD..origin/{branch_name}", "--name-only", "--", "requirements.txt")
            if result.returncode == 0:
                return bool(result.stdout.strip())
        # Fallback to @{u}
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


def ensure_master_branch() -> tuple[bool, str, str]:
    """Switch to master if on another branch.

    Returns (success, previous_branch, error_message).
    - Already on master  → (True, "master", "")
    - Switched OK        → (True, "<prev>", "")
    - Checkout failed    → (False, "<prev>", stderr)
    """
    try:
        head = _git("rev-parse", "--abbrev-ref", "HEAD")
        if head.returncode != 0:
            return False, "", (head.stderr or "").strip()
        current = head.stdout.strip()
        if current == "master":
            return True, "master", ""

        checkout = _git("checkout", "master", timeout=15)
        if checkout.returncode != 0:
            err = (checkout.stderr or checkout.stdout or "").strip()
            return False, current, err
        return True, current, ""
    except subprocess.TimeoutExpired:
        return False, "", "İşlem zaman aşımına uğradı."
    except Exception as e:
        logger.warning("ensure_master_branch failed: %s", e)
        return False, "", str(e)


def restart_app():
    """Restart the application.

    On POSIX systems uses os.execv to replace the current process.
    On Windows uses subprocess.Popen (os.execv does not work reliably
    on Windows) and then exits the current process.
    """
    if sys.platform == "win32":
        import subprocess as _sp
        _sp.Popen([sys.executable] + sys.argv)
        os._exit(0)
    else:
        os.execv(sys.executable, [sys.executable] + sys.argv)
