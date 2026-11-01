"""Сохранение пользовательских настроек между запусками."""

from __future__ import annotations

import json
from typing import Any, Dict

from .config import SETTINGS_FILE


def load_settings() -> Dict[str, Any]:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
