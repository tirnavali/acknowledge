import os
from pathlib import Path

# The project root is the directory containing this 'src' folder
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()

def to_db_path(absolute_path: str) -> str:
    """
    Converts an absolute path to a path relative to the project root.
    Uses forward slashes for database consistency.
    """
    if not absolute_path:
        return ""
    
    try:
        # Convert to Path object for easier manipulation
        p = Path(absolute_path).absolute()
        
        # If it's already inside PROJECT_ROOT, make it relative
        if p.is_relative_to(PROJECT_ROOT):
            rel_path = p.relative_to(PROJECT_ROOT)
            return str(rel_path).replace("\\", "/")
        
        # Fallback: if it's not relative to root, return normalized absolute path
        return str(p).replace("\\", "/")
    except Exception:
        # Fallback for weird paths or different drive letters on Windows
        return absolute_path.replace("\\", "/")

def from_db_path(db_path: str) -> str:
    """
    Converts a relative path from the DB back to an absolute path for the current OS.
    """
    if not db_path:
        return ""
    
    # If it's already an absolute path (legacy or external), just normalize it
    if os.path.isabs(db_path) or (len(db_path) > 1 and db_path[1] == ':'):
        return os.path.normpath(db_path)
    
    # Otherwise, it's relative to PROJECT_ROOT
    return os.path.normpath(os.path.join(PROJECT_ROOT, db_path))

def normalize_path(path: str) -> str:
    """Standard OS-specific path normalization."""
    if not path:
        return ""
    return os.path.normpath(path)

def reveal_in_explorer(path: str):
    """
    Opens the OS file explorer and selects the file at the given path.
    Cross-platform support for macOS, Windows, and Linux.
    """
    import platform
    import subprocess
    import os
    
    path = os.path.normpath(path)
    if not os.path.exists(path):
        return

    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            subprocess.run(["open", "-R", path], check=True)
        elif system == "Windows":
            # Use explorer /select,"<path>" to highlight the file.
            # We must pass this as a single string (often with shell=True or using os.system)
            # because Python's list-based subprocess quoting will quote the entire argument
            # (e.g. "/select,C:\My Path") which confuses explorer.exe into opening Documents instead.
            os.system(f'explorer /select,"{path}"')
        else:  # Linux (Assume xdg-open or similar)
            # Many Linux file managers don't have a standard 'select' flag,
            # so we open the parent directory at least.
            parent = os.path.dirname(path)
            subprocess.run(["xdg-open", parent], check=True)
    except Exception as e:
        import logging
        logging.error(f"Error revealing file in explorer: {e}")
