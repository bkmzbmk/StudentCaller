"""Загрузка списка студентов из .txt, .csv или .xlsx."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import List, Tuple

HEADER_WORDS = {"фио", "студент", "студенты", "имя", "name", "student", "students"}


def _normalize(value) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "cp1251"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _from_txt(path: Path) -> List[str]:
    return [_normalize(line) for line in _read_text(path).splitlines()]


def _from_csv(path: Path) -> List[str]:
    text = _read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    return [_normalize(row[0]) if row else "" for row in csv.reader(io.StringIO(text), dialect)]


def _from_xlsx(path: Path) -> List[str]:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.worksheets[0]
        return [_normalize(row[0]) if row else "" for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def load_roster(path) -> Tuple[List[str], List[str]]:
    """Вернуть (список ФИО, список повторяющихся ФИО).

    Пустые строки, строки-комментарии (#...) и заголовок «ФИО» пропускаются.
    Повторы удаляются (остаётся первое вхождение).
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm"):
        raw = _from_xlsx(path)
    elif ext == ".csv":
        raw = _from_csv(path)
    else:
        raw = _from_txt(path)

    names: List[str] = []
    seen = set()
    duplicates: List[str] = []
    for i, name in enumerate(raw):
        if not name or name.startswith("#"):
            continue
        if i == 0 and name.lower() in HEADER_WORDS:
            continue
        key = name.lower()
        if key in seen:
            duplicates.append(name)
            continue
        seen.add(key)
        names.append(name)
    return names, duplicates
