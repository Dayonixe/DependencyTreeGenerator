"""Small JSON settings store that stays portable in frozen builds."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


THEME_CHOICES = ("system", "light", "dark")


def settings_path() -> Path:
    """Return the settings file without relying on the Windows registry."""
    override = os.environ.get("DEPVIZ_SETTINGS_PATH")
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "depviz-settings.json"
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return root / "Depviz" / "settings.json"
    root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / "depviz" / "settings.json"


def load_theme_preference() -> str:
    """Load the selected theme, falling back safely after invalid files."""
    try:
        data = json.loads(settings_path().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "system"
    value = data.get("theme") if isinstance(data, dict) else None
    return value if value in THEME_CHOICES else "system"


def save_theme_preference(theme: str) -> Path:
    """Atomically persist the selected theme and return the settings path."""
    if theme not in THEME_CHOICES:
        raise ValueError(f"Thème inconnu : {theme}")
    target = settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name("." + target.name + ".tmp")
    try:
        temporary.write_text(
            json.dumps({"theme": theme}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
