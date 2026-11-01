"""Алгоритм случайного выбора студентов «по кругам»."""

from __future__ import annotations

import random
from typing import Iterable, List, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .models import Student


def select_students(
    candidates: Sequence["Student"],
    count: int,
    recent: Iterable[str] = (),
    rng: Optional[random.Random] = None,
) -> List["Student"]:
    """Выбрать ``count`` случайных студентов из ``candidates``.

    Правила:
    * сначала берутся те, кто выходил меньше всех (ни разу -> 1 раз -> ...),
      то есть студенты вызываются «по кругам»;
    * внутри одного круга порядок случайный;
    * при равенстве предпочтение тем, кто НЕ стоял у доски в прошлый раз,
      чтобы на стыке кругов один и тот же человек не вышел дважды подряд.
    """
    if count <= 0 or not candidates:
        return []
    rng = rng or random.Random()
    recent_set = set(recent)
    pool = list(candidates)
    rng.shuffle(pool)  # случайный порядок внутри групп
    # Сортировка устойчивая, поэтому перемешивание внутри групп сохраняется
    pool.sort(key=lambda s: (s.times_called, s.name in recent_set))
    return pool[:count]
