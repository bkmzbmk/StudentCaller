"""Озвучивание ФИО через динамик компьютера.

Основной способ — библиотека pyttsx3 (голоса Windows SAPI5, работает без
интернета). Если pyttsx3 недоступна или сломалась, на Windows используется
запасной способ — System.Speech через PowerShell.

Озвучка идёт в отдельном потоке, чтобы интерфейс не «замирал».
"""

from __future__ import annotations

import base64
import queue
import subprocess
import sys
import threading
from typing import Optional

RU_HINTS = ("ru-ru", "ru_ru", "russian", "irina", "pavel", "русск")


def _co_initialize() -> None:
    """Инициализировать COM в текущем потоке (нужно SAPI5 на Windows)."""
    if sys.platform != "win32":
        return
    try:
        import pythoncom  # из пакета pywin32, ставится вместе с pyttsx3

        pythoncom.CoInitialize()
        return
    except Exception:
        pass
    try:
        import comtypes

        comtypes.CoInitialize()
    except Exception:
        pass


def _pick_russian_voice(engine):
    try:
        voices = engine.getProperty("voices") or []
    except Exception:
        return None
    for v in voices:
        langs = " ".join(str(x) for x in (getattr(v, "languages", None) or []))
        blob = f"{v.id} {getattr(v, 'name', '')} {langs}".lower()
        if any(h in blob for h in RU_HINTS):
            return v
    return None


_PS_TEMPLATE = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$v = $s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'ru*' } | Select-Object -First 1
if ($v) { $s.SelectVoice($v.VoiceInfo.Name) }
$s.Rate = -1
$s.Speak('__TEXT__')
"""


def _speak_powershell(text: str) -> None:
    if sys.platform != "win32":
        raise RuntimeError("запасная озвучка доступна только в Windows")
    script = _PS_TEMPLATE.replace("__TEXT__", text.replace("'", "''"))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=120,
        check=True,
    )


class Speaker:
    """Очередь фраз для озвучки в фоновом потоке.

    Сообщения о состоянии (какой голос выбран, ошибки) кладутся в
    ``messages`` — интерфейс забирает их из главного потока.
    """

    def __init__(self, messages: "Optional[queue.Queue[str]]" = None) -> None:
        self.messages: "queue.Queue[str]" = messages or queue.Queue()
        self._q: "queue.Queue[Optional[str]]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._thread.start()

    def say(self, text: str) -> None:
        """Озвучить текст; ещё не произнесённые фразы отбрасываются."""
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass
        self._q.put(text)

    def stop(self) -> None:
        self._q.put(None)

    # ---------- фоновый поток ----------
    def _msg(self, text: str) -> None:
        self.messages.put(text)

    def _init_engine(self):
        try:
            import pyttsx3

            engine = pyttsx3.init()
        except Exception as e:  # noqa: BLE001
            if sys.platform == "win32":
                self._msg(f"pyttsx3 недоступна ({e}). Используется озвучка Windows через PowerShell.")
            else:
                self._msg(f"Озвучка недоступна: {e}")
            return None
        voice = _pick_russian_voice(engine)
        if voice is not None:
            engine.setProperty("voice", voice.id)
            self._msg(f"Озвучка: {getattr(voice, 'name', voice.id)}")
        else:
            self._msg("Русский голос не найден — ФИО могут читаться неправильно (см. readme.md).")
        try:
            rate = int(engine.getProperty("rate"))
            engine.setProperty("rate", int(rate * 0.85))
        except Exception:
            pass
        return engine

    def _run(self) -> None:
        _co_initialize()
        engine = self._init_engine()
        while True:
            text = self._q.get()
            if text is None:
                break
            try:
                if engine is not None:
                    engine.say(text)
                    engine.runAndWait()
                else:
                    _speak_powershell(text)
            except Exception as e:  # noqa: BLE001
                if engine is not None and sys.platform == "win32":
                    self._msg(f"Ошибка pyttsx3 ({e}). Переключаюсь на озвучку через PowerShell.")
                    engine = None
                    try:
                        _speak_powershell(text)
                    except Exception as e2:  # noqa: BLE001
                        self._msg(f"Ошибка озвучки: {e2}")
                else:
                    self._msg(f"Ошибка озвучки: {e}")
