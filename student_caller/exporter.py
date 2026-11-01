"""Сохранение результатов пары в Excel (.xlsx)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import List, Sequence

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .models import Lesson

HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
HEADER_FONT = Font(bold=True)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
WRAP = Alignment(vertical="top", wrap_text=True)


def default_filename(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"Пара_{now:%Y-%m-%d_%H-%M}.xlsx"


def _write_table(ws, headers: Sequence[str], rows: List[list], widths: Sequence[int]) -> None:
    ws.append(list(headers))
    for row in rows:
        ws.append(row)
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for row in ws.iter_rows():
        for cell in row:
            cell.border = BORDER
            if cell.row > 1:
                cell.alignment = WRAP
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = ws.dimensions


def export_lesson(lesson: Lesson, path) -> Path:
    path = Path(path)
    wb = Workbook()

    # --- Лист 1: студенты ---
    ws = wb.active
    ws.title = "Студенты"
    rows = []
    for i, s in enumerate(lesson.students, start=1):
        rows.append([
            i,
            s.name,
            "Да" if s.present else "Нет",
            s.marked_at if (s.present and s.marked_at) else None,
            "Да" if (s.present and lesson.is_late(s)) else "",
            s.times_called,
            "; ".join(lesson.tasks_for(s.name)),
        ])
    _write_table(
        ws,
        ["№", "ФИО", "Присутствовал", "Время отметки", "Опоздал", "Выходил к доске, раз", "Задания"],
        rows,
        [5, 36, 14, 14, 10, 12, 50],
    )
    for cell in ws["D"][1:]:
        cell.number_format = "HH:MM"

    # --- Лист 2: вызовы ---
    ws2 = wb.create_sheet("Вызовы")
    rows2 = []
    for c in lesson.calls:
        for name in c.students:
            rows2.append([c.number, c.time, name, c.task])
    _write_table(ws2, ["№ вызова", "Время", "ФИО", "Задание"], rows2, [10, 10, 36, 60])
    for cell in ws2["B"][1:]:
        cell.number_format = "HH:MM"

    # --- Лист 3: итоги ---
    ws3 = wb.create_sheet("Итоги")
    present = lesson.present_students()
    late = [s for s in present if lesson.is_late(s)]
    called = [s for s in lesson.students if s.times_called > 0]
    summary = [
        ["Дата", lesson.created_at.date()],
        ["Начало переклички", lesson.roll_call_start],
        ["Сохранено", datetime.now()],
        ["Файл списка", lesson.source],
        ["Всего в списке", len(lesson.students)],
        ["Присутствовало", len(present)],
        ["Отсутствовало", len(lesson.students) - len(present)],
        ["Опоздало", len(late)],
        ["Вызовов к доске", len(lesson.calls)],
        ["Вышло к доске (разных студентов)", len(called)],
    ]
    _write_table(ws3, ["Показатель", "Значение"], summary, [36, 24])
    ws3.auto_filter.ref = None
    ws3["B2"].number_format = "DD.MM.YYYY"
    ws3["B3"].number_format = "HH:MM"
    ws3["B4"].number_format = "DD.MM.YYYY HH:MM"
    for cell in ws3["B"][1:]:
        cell.alignment = Alignment(horizontal="left", vertical="top")

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
