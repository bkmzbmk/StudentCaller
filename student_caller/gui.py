"""Графический интерфейс (tkinter)."""

from __future__ import annotations

import queue
import sys
import traceback
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk
from typing import Optional

from .config import (
    APP_TITLE,
    DEFAULT_CALL_COUNT,
    DEFAULT_ROSTER,
    LOG_FILE,
    MAX_CALL_COUNT,
    MODELS_DIR,
    RESULTS_DIR,
)
from .exporter import default_filename, export_lesson
from .models import Lesson, NoStudentsError
from .roster import load_roster
from .settings import load_settings, save_settings
from .speech import SILERO_VOICE_TITLES, SILERO_VOICES, Speaker

CHECK_ON = "Да"
CHECK_OFF = "—"
LEAD_ONE = "К доске выходит"
LEAD_MANY = "К доске выходят"
UI_FONT = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = load_settings()
        self.messages: "queue.Queue" = queue.Queue()
        self.speaker = Speaker(
            self.messages,
            MODELS_DIR,
            voice=self.settings.get("voice", SILERO_VOICES[0]),
            use_silero=bool(self.settings.get("use_silero", True)),
        )
        self.lesson = Lesson([])
        self.spoken: dict = {}  # ФИО -> текст для озвучки (с ударениями «+»)
        self.dirty = False
        self._suppress_task_trace = False

        root.title(APP_TITLE)
        root.geometry(self.settings.get("geometry", "1200x720"))
        root.minsize(900, 560)
        root.report_callback_exception = self._on_tk_error

        self._setup_style()
        self._build_ui()
        self._load_initial_roster()
        self._refresh_all()

        root.protocol("WM_DELETE_WINDOW", self.on_close)
        root.bind("<F5>", lambda e: self.on_call())
        self._poll_messages()

    # ------------------------------------------------------------------ UI
    def _setup_style(self) -> None:
        style = ttk.Style(self.root)
        if sys.platform == "win32" and "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        self.root.option_add("*Font", (UI_FONT, 10))
        style.configure("Treeview", rowheight=26, font=(UI_FONT, 11))
        style.configure("Treeview.Heading", font=(UI_FONT, 10, "bold"))
        style.configure("Call.TButton", font=(UI_FONT, 15, "bold"), padding=(10, 12))
        style.configure("Info.TLabel", foreground="#555555")
        style.configure("Big.TLabel", font=(UI_FONT, 11, "bold"))

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        paned.add(self._build_students_panel(paned), weight=3)
        paned.add(self._build_right_panel(paned), weight=2)

        bottom = ttk.Frame(self.root, padding=(8, 6))
        bottom.pack(fill=tk.X)
        ttk.Button(bottom, text="Сохранить результат пары в Excel…", command=self.on_save).pack(side=tk.RIGHT)
        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(bottom, textvariable=self.status_var, style="Info.TLabel").pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_students_panel(self, parent) -> ttk.Frame:
        frame = ttk.LabelFrame(parent, text="Студенты", padding=8)

        bar = ttk.Frame(frame)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Загрузить список…", command=self.on_load_roster).pack(side=tk.LEFT)
        ttk.Button(bar, text="Новая пара", command=self.on_new_lesson).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(bar, text="Снять все отметки", command=self.on_clear_presence).pack(side=tk.RIGHT)
        ttk.Button(bar, text="Все присутствуют", command=self.on_all_present).pack(side=tk.RIGHT, padx=(0, 6))

        self.roster_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.roster_var, style="Info.TLabel").pack(fill=tk.X, pady=(6, 0))
        self.counts_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.counts_var, style="Big.TLabel").pack(fill=tk.X, pady=(2, 6))

        table = ttk.Frame(frame)
        table.pack(fill=tk.BOTH, expand=True)
        cols = ("num", "name", "present", "marked", "calls")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse")
        for col, text, width, anchor, stretch in (
            ("num", "№", 40, tk.CENTER, False),
            ("name", "ФИО", 300, tk.W, True),
            ("present", "Присутствует", 110, tk.CENTER, False),
            ("marked", "Отметка", 80, tk.CENTER, False),
            ("calls", "Выходил", 80, tk.CENTER, False),
        ):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor=anchor, stretch=stretch)
        sb = ttk.Scrollbar(table, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.tag_configure("absent", foreground="#9a9a9a")
        self.tree.tag_configure("called", background="#e6f4e6")
        self.tree.tag_configure("atboard", background="#fff1a8")
        self.tree.tag_configure("late", foreground="#b25b00")

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<space>", self._on_tree_space)

        ttk.Label(
            frame,
            text="Щёлкните по «Присутствует» (или дважды по строке, или Пробел), чтобы отметить студента. "
            "Жёлтым — у доски сейчас, зелёным — уже выходили.",
            style="Info.TLabel",
            wraplength=560,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(6, 0))
        return frame

    def _build_right_panel(self, parent) -> ttk.Frame:
        right = ttk.Frame(parent)

        # --- вызов ---
        call = ttk.LabelFrame(right, text="Вызов к доске", padding=8)
        call.pack(fill=tk.X)
        row = ttk.Frame(call)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Сколько вызвать:").pack(side=tk.LEFT)
        self.count_var = tk.StringVar(value=str(self.settings.get("call_count", DEFAULT_CALL_COUNT)))
        ttk.Spinbox(row, from_=1, to=MAX_CALL_COUNT, width=5, textvariable=self.count_var,
                    font=(UI_FONT, 12)).pack(side=tk.LEFT, padx=6)
        self.speak_var = tk.BooleanVar(value=bool(self.settings.get("speak", True)))
        ttk.Checkbutton(row, text="Озвучивать ФИО", variable=self.speak_var).pack(side=tk.LEFT, padx=(12, 0))

        vrow = ttk.Frame(call)
        vrow.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(vrow, text="Голос Silero:").pack(side=tk.LEFT)
        self.voice_var = tk.StringVar()
        self.voice_box = ttk.Combobox(vrow, textvariable=self.voice_var, state="disabled", width=16)
        self.voice_box.pack(side=tk.LEFT, padx=6)
        self.voice_box.bind("<<ComboboxSelected>>", self._on_voice_selected)
        self.engine_var = tk.StringVar(value="загрузка…")
        ttk.Label(vrow, textvariable=self.engine_var, style="Info.TLabel").pack(side=tk.LEFT, padx=(6, 0))
        self._voice_ids: list = []
        self._set_voices(list(SILERO_VOICES), enabled=False)

        ttk.Button(call, text="Вызвать  (F5)", style="Call.TButton", command=self.on_call).pack(fill=tk.X, pady=(8, 4))
        ttk.Button(call, text="Повторить озвучку", command=self.on_repeat).pack(anchor=tk.E)

        # --- у доски ---
        board = ttk.LabelFrame(right, text="Сейчас у доски", padding=8)
        board.pack(fill=tk.X, pady=(8, 0))
        self.call_info_var = tk.StringVar(value="Пока никто не вызван")
        ttk.Label(board, textvariable=self.call_info_var, style="Info.TLabel").pack(anchor=tk.W)
        self.board_list = tk.Listbox(board, height=5, font=(UI_FONT, 14), activestyle="none",
                                     highlightthickness=0, background="#fffbe6")
        self.board_list.pack(fill=tk.X, pady=(4, 6))
        ttk.Label(board, text="Задание:").pack(anchor=tk.W)
        self.task_var = tk.StringVar()
        self.task_entry = ttk.Entry(board, textvariable=self.task_var, font=(UI_FONT, 12))
        self.task_entry.pack(fill=tk.X)
        self.task_var.trace_add("write", self._on_task_changed)

        # --- история ---
        hist = ttk.LabelFrame(right, text="История вызовов", padding=8)
        hist.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        cols = ("num", "time", "students", "task")
        self.history = ttk.Treeview(hist, columns=cols, show="headings", height=6)
        for col, text, width, stretch in (
            ("num", "№", 36, False),
            ("time", "Время", 60, False),
            ("students", "Студенты", 240, True),
            ("task", "Задание", 160, True),
        ):
            self.history.heading(col, text=text)
            self.history.column(col, width=width, stretch=stretch,
                                anchor=tk.CENTER if col in ("num", "time") else tk.W)
        hsb = ttk.Scrollbar(hist, orient=tk.VERTICAL, command=self.history.yview)
        self.history.configure(yscrollcommand=hsb.set)
        self.history.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        hsb.pack(side=tk.RIGHT, fill=tk.Y)
        return right

    # ------------------------------------------------------------ обновление
    def _refresh_all(self) -> None:
        self._refresh_students()
        self._refresh_board()
        self._refresh_history()

    def _refresh_students(self) -> None:
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        at_board = set(self.lesson.current_call.students) if self.lesson.current_call else set()
        for i, s in enumerate(self.lesson.students):
            tags = []
            if not s.present:
                tags.append("absent")
            elif s.name in at_board:
                tags.append("atboard")
            elif s.times_called:
                tags.append("called")
            if s.present and self.lesson.is_late(s):
                tags.append("late")
            marked = s.marked_at.strftime("%H:%M") if (s.present and s.marked_at) else ""
            self.tree.insert(
                "", tk.END, iid=str(i), tags=tags,
                values=(i + 1, s.name, CHECK_ON if s.present else CHECK_OFF, marked, s.times_called or ""),
            )
        for iid in selected:
            if self.tree.exists(iid):
                self.tree.selection_set(iid)
                self.tree.focus(iid)

        total = len(self.lesson.students)
        present = self.lesson.present_students()
        went = sum(1 for s in present if s.times_called)
        late = sum(1 for s in present if self.lesson.is_late(s))
        text = f"Присутствуют: {len(present)} из {total}   ·   Выходили: {went}"
        if present:
            text += f"   ·   Круг №{self.lesson.current_round()}"
        if late:
            text += f"   ·   Опоздали: {late}"
        self.counts_var.set(text)

    def _refresh_board(self) -> None:
        self.board_list.delete(0, tk.END)
        rec = self.lesson.current_call
        self._suppress_task_trace = True
        try:
            if rec is None:
                self.call_info_var.set("Пока никто не вызван")
                self.task_var.set("")
                self.task_entry.state(["disabled"])
            else:
                self.call_info_var.set(f"Вызов №{rec.number} в {rec.time:%H:%M}")
                for name in rec.students:
                    self.board_list.insert(tk.END, name)
                self.task_var.set(rec.task)
                self.task_entry.state(["!disabled"])
        finally:
            self._suppress_task_trace = False

    def _refresh_history(self) -> None:
        self.history.delete(*self.history.get_children())
        for c in reversed(self.lesson.calls):
            self.history.insert("", tk.END, iid=str(c.number),
                                values=(c.number, f"{c.time:%H:%M}", ", ".join(c.students), c.task))

    def _set_status(self, text: str) -> None:
        self.status_var.set(f"{datetime.now():%H:%M}  {text}")

    def _poll_messages(self) -> None:
        try:
            while True:
                item = self.messages.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "voices":
                    self._set_voices(item[1], enabled=True)
                else:
                    self._set_status(str(item))
        except queue.Empty:
            pass
        if self.speaker.silero_ready:
            engine = "Silero готов"
        elif self.speaker.silero_error is None:
            engine = "Silero загружается…"
        else:
            engine = "Silero недоступен — голос Windows"
        self.engine_var.set(engine)
        self.root.after(250, self._poll_messages)

    # ------------------------------------------------------------ голос
    def _set_voices(self, voices, enabled: bool) -> None:
        self._voice_ids = list(voices)
        self.voice_box["values"] = [SILERO_VOICE_TITLES.get(v, v) for v in voices]
        current = self.speaker.voice if self.speaker.voice in voices else voices[0]
        self.voice_var.set(SILERO_VOICE_TITLES.get(current, current))
        self.voice_box.configure(state="readonly" if enabled else "disabled")

    def _on_voice_selected(self, _event=None) -> None:
        idx = self.voice_box.current()
        if idx < 0:
            return
        voice = self._voice_ids[idx]
        self.speaker.set_voice(voice)
        self.settings["voice"] = voice
        if self.speak_var.get():
            self.speaker.say("Проверка голоса")

    # ------------------------------------------------------------ список
    def _load_initial_roster(self) -> None:
        last = self.settings.get("last_roster")
        if last and _is_results_file(Path(last)):
            last = None
        for candidate in (last, str(DEFAULT_ROSTER)):
            if candidate and Path(candidate).is_file():
                self._load_roster_file(Path(candidate), quiet=True)
                return
        self.roster_var.set("Список не загружен — нажмите «Загрузить список…»")

    def _load_roster_file(self, path: Path, quiet: bool = False) -> bool:
        try:
            names, duplicates, spoken = load_roster(path)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Ошибка", f"Не удалось прочитать список:\n{path}\n\n{e}", parent=self.root)
            return False
        if not names:
            messagebox.showwarning("Пустой список", f"В файле нет ни одного ФИО:\n{path}", parent=self.root)
            return False
        self.lesson = Lesson(names, source=path.name)
        self.spoken = spoken
        self.dirty = False
        if not _is_results_file(path):
            # файл сохранённой пары не запоминаем — при следующем запуске
            # откроется обычный список студентов
            self.settings["last_roster"] = str(path)
        # Silero заранее озвучивает фразы и все ФИО, чтобы вызов звучал сразу
        self.speaker.prefetch([LEAD_MANY, LEAD_ONE] + [spoken.get(n, n) for n in names])
        self.roster_var.set(f"Список: {path.name}  ({len(names)} чел.)")
        self._refresh_all()
        self._set_status(f"Загружен список: {path.name}, {len(names)} студентов")
        if duplicates and not quiet:
            messagebox.showinfo("Повторы", "Повторяющиеся ФИО пропущены:\n" + "\n".join(duplicates), parent=self.root)
        return True

    def _confirm_discard(self) -> bool:
        """Спросить про несохранённую пару. True — можно продолжать."""
        if not (self.dirty and self.lesson.has_data):
            return True
        answer = messagebox.askyesnocancel(
            "Несохранённая пара",
            "Результаты текущей пары не сохранены.\nСохранить их в Excel?",
            parent=self.root,
        )
        if answer is None:
            return False
        if answer:
            return self.on_save()
        return True

    def on_load_roster(self) -> None:
        if not self._confirm_discard():
            return
        last = self.settings.get("last_roster")
        initial_dir = str(Path(last).parent) if last else str(DEFAULT_ROSTER.parent)
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Список студентов",
            initialdir=initial_dir,
            filetypes=[
                ("Списки студентов", "*.txt *.csv *.xlsx"),
                ("Текстовые файлы", "*.txt"),
                ("Excel", "*.xlsx"),
                ("CSV", "*.csv"),
                ("Все файлы", "*.*"),
            ],
        )
        if path:
            self._load_roster_file(Path(path))

    def on_new_lesson(self) -> None:
        if not self._confirm_discard():
            return
        last = self.settings.get("last_roster")
        if last and Path(last).is_file():
            self._load_roster_file(Path(last))  # перечитываем файл — список мог измениться
        else:
            self.lesson = Lesson([s.name for s in self.lesson.students], source=self.lesson.source)
            self.dirty = False
            self._refresh_all()
        self._set_status("Начата новая пара")

    # ------------------------------------------------------------ отметки
    def _toggle(self, iid: str) -> None:
        if not iid:
            return
        self.lesson.toggle_present(int(iid))
        self.dirty = True
        self._refresh_students()

    def _on_tree_click(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) == "#3":
            self._toggle(self.tree.identify_row(event.y))

    def _on_tree_double(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) == "#3":
            return  # первый щелчок уже переключил отметку
        self._toggle(self.tree.identify_row(event.y))

    def _on_tree_space(self, event) -> str:
        self._toggle(self.tree.focus())
        return "break"

    def on_all_present(self) -> None:
        self.lesson.mark_all_present()
        self.dirty = True
        self._refresh_students()

    def on_clear_presence(self) -> None:
        if not any(s.present for s in self.lesson.students):
            return
        if not messagebox.askyesno("Снять отметки", "Снять отметки присутствия у всех студентов?", parent=self.root):
            return
        self.lesson.clear_presence()
        self._refresh_students()

    # ------------------------------------------------------------ вызов
    def _get_count(self) -> Optional[int]:
        try:
            n = int(self.count_var.get())
        except ValueError:
            return None
        return n if 1 <= n <= MAX_CALL_COUNT else None

    def on_call(self) -> None:
        n = self._get_count()
        if n is None:
            messagebox.showwarning("Количество", f"Укажите число от 1 до {MAX_CALL_COUNT}.", parent=self.root)
            return
        try:
            rec = self.lesson.call(n)
        except NoStudentsError:
            messagebox.showwarning("Никто не отмечен", "Сначала отметьте присутствующих студентов.", parent=self.root)
            return
        self.dirty = True
        self._refresh_all()
        if len(rec.students) < n:
            self._set_status(f"Присутствует только {len(rec.students)} — вызваны все.")
        else:
            self._set_status(f"Вызов №{rec.number}: {', '.join(rec.students)}")
        self._speak_current()
        self.task_entry.focus_set()

    def _speak_current(self) -> None:
        rec = self.lesson.current_call
        if rec is None or not self.speak_var.get():
            return
        lead = LEAD_ONE if len(rec.students) == 1 else LEAD_MANY
        self.speaker.say(lead, [self.spoken.get(n, n) for n in rec.students])

    def on_repeat(self) -> None:
        if self.lesson.current_call is None:
            return
        if not self.speak_var.get():
            self._set_status("Озвучка выключена — включите «Озвучивать ФИО».")
            return
        self._speak_current()

    def _on_task_changed(self, *_args) -> None:
        if self._suppress_task_trace:
            return
        rec = self.lesson.current_call
        if rec is None:
            return
        rec.task = self.task_var.get().strip()
        self.dirty = True
        iid = str(rec.number)
        if self.history.exists(iid):
            self.history.set(iid, "task", rec.task)

    # ------------------------------------------------------------ сохранение
    def on_save(self) -> bool:
        if not self.lesson.students:
            messagebox.showinfo("Нечего сохранять", "Список студентов пуст.", parent=self.root)
            return False
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Сохранить результат пары",
            initialdir=str(RESULTS_DIR),
            initialfile=default_filename(),
            defaultextension=".xlsx",
            filetypes=[("Книга Excel", "*.xlsx")],
        )
        if not path:
            return False
        try:
            export_lesson(self.lesson, path)
        except PermissionError:
            messagebox.showerror("Не удалось сохранить",
                                 "Файл занят — возможно, он открыт в Excel. Закройте его и попробуйте снова.",
                                 parent=self.root)
            return False
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("Не удалось сохранить", str(e), parent=self.root)
            return False
        self.dirty = False
        self._set_status(f"Сохранено: {path}")
        return True

    # ------------------------------------------------------------ выход
    def on_close(self) -> None:
        if not self._confirm_discard():
            return
        self.settings["call_count"] = self._get_count() or DEFAULT_CALL_COUNT
        self.settings["speak"] = bool(self.speak_var.get())
        self.settings["voice"] = self.speaker.voice
        if self.root.state() == "normal":
            self.settings["geometry"] = self.root.geometry()
        save_settings(self.settings)
        self.speaker.stop()
        self.root.destroy()

    def _on_tk_error(self, exc, val, tb) -> None:
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}")
        except OSError:
            pass
        messagebox.showerror("Ошибка", f"{val}\n\nПодробности записаны в {LOG_FILE.name}", parent=self.root)


def _is_results_file(path: Path) -> bool:
    """Файл лежит в папке results (это сохранённая пара, а не список)."""
    try:
        return Path(path).resolve().parent == RESULTS_DIR.resolve()
    except OSError:
        return False


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass


def run() -> None:
    _enable_dpi_awareness()
    root = tk.Tk()
    App(root)
    root.mainloop()
