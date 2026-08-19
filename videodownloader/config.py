"""Persisted app settings (theme, last folder, quality, etc.) as JSON."""

import json

from videodownloader.paths import CONFIG_PATH


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def update_config(**kwargs):
    """Load, merge, and rewrite the config file with the given fields."""
    config = load_config()
    config.update(kwargs)
    save_config(config)
