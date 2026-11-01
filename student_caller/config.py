"""Константы и пути приложения."""

from pathlib import Path

APP_TITLE = "Вызов к доске"

# Сколько студентов вызывать за один раз по умолчанию
DEFAULT_CALL_COUNT = 4
MAX_CALL_COUNT = 50

# Студент считается опоздавшим, если его отметили позже, чем через
# столько минут после первой отметки на паре (начала переклички).
LATE_MINUTES = 10

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ROSTER = BASE_DIR / "students.txt"
RESULTS_DIR = BASE_DIR / "results"
MODELS_DIR = BASE_DIR / "models"  # сюда скачивается модель Silero
SETTINGS_FILE = BASE_DIR / "settings.json"
LOG_FILE = BASE_DIR / "error.log"
