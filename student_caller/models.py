"""Модель данных пары: студенты, вызовы, отметки."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from .config import LATE_MINUTES
from .selection import select_students


@dataclass
class Student:
    name: str
    present: bool = False
    marked_at: Optional[datetime] = None  # когда впервые отмечен присутствующим
    times_called: int = 0  # сколько раз выходил к доске на этой паре


@dataclass
class CallRecord:
    number: int
    time: datetime
    students: List[str]
    task: str = ""


class NoStudentsError(Exception):
    """Нет присутствующих студентов для вызова."""


class Lesson:
    """Состояние одной пары."""

    def __init__(
        self,
        names: Sequence[str],
        source: str = "",
        late_minutes: int = LATE_MINUTES,
    ) -> None:
        self.students: List[Student] = [Student(n) for n in names]
        self.calls: List[CallRecord] = []
        self.source = source  # откуда загружен список (имя файла)
        self.created_at = datetime.now()
        self.roll_call_start: Optional[datetime] = None
        self.late_minutes = late_minutes

    # ---------- посещаемость ----------
    def set_present(self, index: int, present: bool, now: Optional[datetime] = None) -> None:
        student = self.students[index]
        now = now or datetime.now()
        if present and not student.present:
            if self.roll_call_start is None:
                self.roll_call_start = now
            if student.marked_at is None:
                student.marked_at = now
        student.present = present

    def toggle_present(self, index: int) -> None:
        self.set_present(index, not self.students[index].present)

    def mark_all_present(self) -> None:
        now = datetime.now()
        for i in range(len(self.students)):
            self.set_present(i, True, now)

    def clear_presence(self) -> None:
        for s in self.students:
            s.present = False
            s.marked_at = None
        self.roll_call_start = None

    def present_students(self) -> List[Student]:
        return [s for s in self.students if s.present]

    def is_late(self, student: Student) -> bool:
        if student.marked_at is None or self.roll_call_start is None:
            return False
        return student.marked_at - self.roll_call_start > timedelta(minutes=self.late_minutes)

    # ---------- вызовы ----------
    @property
    def current_call(self) -> Optional[CallRecord]:
        return self.calls[-1] if self.calls else None

    def current_round(self) -> int:
        """Номер текущего круга (1 — пока не все присутствующие выходили)."""
        present = self.present_students()
        if not present:
            return 1
        return min(s.times_called for s in present) + 1

    def call(self, count: int, rng: Optional[random.Random] = None) -> CallRecord:
        present = self.present_students()
        if not present:
            raise NoStudentsError("Нет присутствующих студентов")
        recent = self.current_call.students if self.current_call else []
        chosen = select_students(present, count, recent=recent, rng=rng)
        for s in chosen:
            s.times_called += 1
        record = CallRecord(
            number=len(self.calls) + 1,
            time=datetime.now(),
            students=[s.name for s in chosen],
        )
        self.calls.append(record)
        return record

    def tasks_for(self, name: str) -> List[str]:
        return [c.task for c in self.calls if name in c.students and c.task]

    @property
    def has_data(self) -> bool:
        """Есть ли что сохранять (отметки или вызовы)."""
        return bool(self.calls) or any(s.present for s in self.students)
