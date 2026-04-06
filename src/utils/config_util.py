import os
import json
from pathlib import Path

# The project root is the directory containing this 'src' folder
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
CONFIG_FILE = os.path.join(PROJECT_ROOT, "settings.json")

# Default settings
DEFAULT_CONFIG = {
    "auto_captioning_enabled": False
}

def load_config() -> dict:
    """Load configuration from settings.json or default if not exists."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Merge with defaults to ensure all keys exist
            merged = DEFAULT_CONFIG.copy()
            merged.update(data)
            return merged
    except Exception as e:
        import logging
        logging.warning(f"Error loading config: {e}. Using defaults.")
        return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    """Save configuration to settings.json."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        import logging
        logging.error(f"Error saving config: {e}")

def get_setting(key: str, default=None):
    """Get a specific setting value."""
    config = load_config()
    return config.get(key, default)

def set_setting(key: str, value):
    """Set a specific setting value immediately to file."""
    config = load_config()
    config[key] = value
    save_config(config)
