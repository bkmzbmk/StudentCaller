"""Точка входа: python main.py"""

import sys
import traceback
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    try:
        from student_caller.gui import run

        run()
    except Exception:  # noqa: BLE001
        text = traceback.format_exc()
        log = Path(__file__).resolve().parent / "error.log"
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}")
        except OSError:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox

            r = tk.Tk()
            r.withdraw()
            messagebox.showerror("Вызов к доске — ошибка запуска", f"{text}\n\nПодробности: {log}")
            r.destroy()
        except Exception:  # noqa: BLE001
            print(text, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
