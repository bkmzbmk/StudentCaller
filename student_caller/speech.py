"""Озвучивание ФИО через динамик компьютера.

Движки (по приоритету):

1. **Silero TTS** — нейросетевой русский синтез, работает без интернета
   (интернет нужен один раз, чтобы скачать модель ~100 МБ в папку ``models``).
   Нужны библиотеки torch и numpy.
2. **pyttsx3** — голоса Windows (SAPI5).
3. **PowerShell / System.Speech** — запасной вариант, встроен в Windows.

Пока Silero загружается (или если он недоступен), фразы произносятся
запасным движком. Silero заранее, в фоне, озвучивает все ФИО из списка,
поэтому при нажатии «Вызвать» звук начинается сразу.

Ударение можно подсказать знаком «+» перед ударной гласной: «Кузнец+ов».
"""

from __future__ import annotations

import base64
import collections
import io
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
import wave
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

SILERO_MODEL_IDS = ("v5_5_ru", "v5_4_ru", "v5_ru")
SILERO_URL = "https://models.silero.ai/models/tts/ru/{}.pt"
SILERO_VOICES = ["xenia", "kseniya", "baya", "aidar", "eugene"]
SILERO_VOICE_TITLES = {
    "xenia": "xenia (жен.)",
    "kseniya": "kseniya (жен.)",
    "baya": "baya (жен.)",
    "aidar": "aidar (муж.)",
    "eugene": "eugene (муж.)",
}
SAMPLE_RATE = 48000
PAUSE_SEC = 0.35

RU_HINTS = ("ru-ru", "ru_ru", "russian", "irina", "pavel", "русск")


# ====================================================================
# Silero
# ====================================================================
class SileroEngine:
    def __init__(self, models_dir: Path, status) -> None:
        self.models_dir = Path(models_dir)
        self.status = status  # функция для сообщений в строку состояния
        self.model = None
        self.model_id = ""
        self.speakers: List[str] = list(SILERO_VOICES)
        self._torch = None
        self._kwargs_ok: Optional[bool] = None

    # ---------- загрузка ----------
    def _download(self, model_id: str, target: Path) -> None:
        url = SILERO_URL.format(model_id)
        tmp = target.with_suffix(".part")
        req = urllib.request.Request(url, headers={"User-Agent": "StudentCaller"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done, last = 0, 0.0
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if time.monotonic() - last > 1.0:
                    last = time.monotonic()
                    if total:
                        self.status(f"Скачиваю голосовую модель Silero: {done * 100 // total}% "
                                    f"из {total // (1 << 20)} МБ…")
                    else:
                        self.status(f"Скачиваю голосовую модель Silero: {done // (1 << 20)} МБ…")
        if total and done < total:
            raise IOError("загрузка прервалась")
        tmp.replace(target)

    def _find_or_download(self) -> Tuple[str, Path]:
        self.models_dir.mkdir(parents=True, exist_ok=True)
        for mid in SILERO_MODEL_IDS:
            path = self.models_dir / f"{mid}.pt"
            if path.is_file() and path.stat().st_size > 1_000_000:
                return mid, path
        errors = []
        for mid in SILERO_MODEL_IDS:
            path = self.models_dir / f"{mid}.pt"
            try:
                self.status(f"Скачиваю голосовую модель Silero ({mid})…")
                self._download(mid, path)
                return mid, path
            except Exception as e:  # noqa: BLE001
                errors.append(f"{mid}: {e}")
        raise RuntimeError("не удалось скачать модель — " + "; ".join(errors))

    def load(self) -> None:
        import torch  # тяжёлый импорт, поэтому здесь, в фоновом потоке
        import torch.package  # noqa: F401

        self._torch = torch
        torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
        self.model_id, path = self._find_or_download()
        self.status(f"Загружаю модель Silero {self.model_id}…")
        model = torch.package.PackageImporter(str(path)).load_pickle("tts_models", "model")
        model.to(torch.device("cpu"))
        speakers = [s for s in (getattr(model, "speakers", None) or []) if s != "random"]
        if speakers:
            # наш порядок, но только реально существующие + новые голоса модели
            ordered = [v for v in SILERO_VOICES if v in speakers]
            self.speakers = ordered + [s for s in speakers if s not in ordered]
        self.model = model

    # ---------- синтез ----------
    def _apply(self, text: str, speaker: str):
        if self._kwargs_ok is not False:
            try:
                audio = self.model.apply_tts(text=text, speaker=speaker, sample_rate=SAMPLE_RATE,
                                             put_accent=True, put_yo=True)
                self._kwargs_ok = True
                return audio
            except TypeError:
                self._kwargs_ok = False
        return self.model.apply_tts(text=text, speaker=speaker, sample_rate=SAMPLE_RATE)

    def synth(self, text: str, speaker: str):
        """Вернуть 1-мерный тензор float32 в диапазоне [-1, 1]."""
        try:
            audio = self._apply(text, speaker)
        except Exception:
            if "+" not in text:
                raise
            audio = self._apply(text.replace("+", ""), speaker)  # вдруг модель не поняла «+»
        return audio.flatten().float()

    def silence(self, seconds: float):
        return self._torch.zeros(int(SAMPLE_RATE * seconds))

    def to_wav(self, chunks: Sequence) -> bytes:
        torch = self._torch
        audio = torch.cat(list(chunks)) if len(chunks) > 1 else chunks[0]
        pcm = (audio.clamp(-1.0, 1.0) * 32767).to(torch.int16).numpy().tobytes()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(pcm)
        return buf.getvalue()


def play_wav(data: bytes) -> None:
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(data, winsound.SND_MEMORY)
    # на других ОС воспроизведение не нужно (программа рассчитана на Windows)


def stop_playback() -> None:
    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(None, 0)
        except Exception:
            pass


# ====================================================================
# Запасные движки: pyttsx3 и PowerShell
# ====================================================================
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


class FallbackEngine:
    """pyttsx3, а если он не работает — PowerShell."""

    def __init__(self, status) -> None:
        self.status = status
        self.engine = None
        self.ready = False
        self.description = ""

    def init(self) -> None:
        try:
            import pyttsx3

            engine = pyttsx3.init()
            voice = _pick_russian_voice(engine)
            if voice is not None:
                engine.setProperty("voice", voice.id)
                self.description = f"голос Windows {getattr(voice, 'name', voice.id)}"
            else:
                self.description = "голос Windows (русский голос не найден)"
            try:
                engine.setProperty("rate", int(int(engine.getProperty("rate")) * 0.85))
            except Exception:
                pass
            self.engine = engine
        except Exception as e:  # noqa: BLE001
            self.engine = None
            self.description = f"PowerShell (pyttsx3 недоступна: {e})"
        self.ready = True

    def speak(self, text: str) -> None:
        text = text.replace("+", "")
        if self.engine is not None:
            try:
                self.engine.say(text)
                self.engine.runAndWait()
                return
            except Exception as e:  # noqa: BLE001
                self.status(f"Ошибка pyttsx3 ({e}), переключаюсь на PowerShell.")
                self.engine = None
        _speak_powershell(text)


# ====================================================================
# Speaker — то, с чем работает интерфейс
# ====================================================================
class Speaker:
    """Фоновая озвучка.

    Сообщения для интерфейса кладутся в ``messages``:
    строка — текст для строки состояния; кортеж ``("voices", [...])`` —
    список голосов Silero после загрузки модели.
    """

    def __init__(self, messages: "queue.Queue", models_dir: Path, voice: str = "xenia",
                 use_silero: bool = True) -> None:
        self.messages = messages
        self.voice = voice if voice in SILERO_VOICES else SILERO_VOICES[0]
        self._q: "queue.Queue" = queue.Queue()
        self._prefetch: "collections.deque[str]" = collections.deque()
        self._prefetch_all: List[str] = []
        self._cache: Dict[Tuple[str, str], object] = {}
        self._fallback = FallbackEngine(self._msg)
        self._silero = SileroEngine(models_dir, self._msg)
        self._silero_ready = False
        self.silero_error: Optional[str] = None

        self._worker = threading.Thread(target=self._run, name="speaker", daemon=True)
        self._worker.start()
        if use_silero:
            threading.Thread(target=self._load_silero, name="silero-loader", daemon=True).start()
        else:
            self.silero_error = "отключён"

    # ---------- публичные методы (вызываются из потока интерфейса) ----------
    @property
    def engine_name(self) -> str:
        if self._silero_ready:
            return f"Silero {self._silero.model_id}, голос {self.voice}"
        return self._fallback.description or "запуск…"

    @property
    def silero_ready(self) -> bool:
        return self._silero_ready

    def say(self, lead: str, items: Sequence[str] = ()) -> None:
        """Произнести фразу: вступление и затем список (ФИО) с паузами.

        Ещё не произнесённые фразы отбрасываются, текущая прерывается.
        """
        self._drop_pending("say")
        stop_playback()
        self._q.put(("say", (lead, list(items))))

    def prefetch(self, items: Sequence[str]) -> None:
        """Заранее озвучить (в фоне) — например, все ФИО из списка."""
        self._q.put(("prefetch", list(items)))

    def set_voice(self, voice: str) -> None:
        self._q.put(("voice", voice))

    def stop(self) -> None:
        stop_playback()
        self._q.put(None)

    # ---------- внутреннее ----------
    def _msg(self, item) -> None:
        self.messages.put(item)

    def _drop_pending(self, kind: str) -> None:
        kept = []
        try:
            while True:
                item = self._q.get_nowait()
                if item is None or item[0] != kind:
                    kept.append(item)
        except queue.Empty:
            pass
        for item in kept:
            self._q.put(item)

    def _load_silero(self) -> None:
        try:
            self._silero.load()
        except ImportError as e:
            self.silero_error = f"не установлен torch ({e})"
            self._msg(f"Silero недоступен: {self.silero_error}. Озвучка: {self._fallback.description}.")
            return
        except Exception as e:  # noqa: BLE001
            self.silero_error = str(e)
            self._msg(f"Silero недоступен: {e}. Озвучка: {self._fallback.description}.")
            return
        if self.voice not in self._silero.speakers:
            self.voice = self._silero.speakers[0]
        self._silero_ready = True
        self._msg(("voices", list(self._silero.speakers)))
        self._msg(f"Озвучка: Silero {self._silero.model_id}, голос {self.voice}")

    def _chunk(self, text: str):
        key = (self.voice, text)
        audio = self._cache.get(key)
        if audio is None:
            audio = self._silero.synth(text, self.voice)
            self._cache[key] = audio
        return audio

    def _speak_silero(self, lead: str, items: List[str]) -> None:
        chunks = []
        pause = self._silero.silence(PAUSE_SEC)
        for part in ([lead] if lead else []) + items:
            if chunks:
                chunks.append(pause)
            chunks.append(self._chunk(part))
        if chunks:
            play_wav(self._silero.to_wav(chunks))

    def _speak(self, lead: str, items: List[str]) -> None:
        if self._silero_ready:
            try:
                self._speak_silero(lead, items)
                return
            except Exception as e:  # noqa: BLE001
                self._msg(f"Ошибка Silero ({e}), использую {self._fallback.description}.")
        text = lead
        if items:
            text = (f"{lead}: " if lead else "") + ". ".join(items) + "."
        self._fallback.speak(text)

    def _prefetch_one(self) -> None:
        text = self._prefetch.popleft()
        try:
            self._chunk(text)
        except Exception as e:  # noqa: BLE001
            self._msg(f"Silero не смог озвучить «{text}»: {e}")

    def _run(self) -> None:
        _co_initialize()
        self._fallback.init()
        if not self._silero_ready and self.silero_error is None:
            self._msg(f"Готовлю голос Silero… пока работает {self._fallback.description}.")
        while True:
            busy = self._silero_ready and self._prefetch
            try:
                item = self._q.get(timeout=0.05 if busy else 0.5)
            except queue.Empty:
                if busy:
                    self._prefetch_one()
                continue
            if item is None:
                break
            kind, payload = item
            try:
                if kind == "say":
                    self._speak(*payload)
                elif kind == "prefetch":
                    self._prefetch_all = list(dict.fromkeys(payload))
                    self._prefetch = collections.deque(self._prefetch_all)
                elif kind == "voice":
                    if payload != self.voice:
                        self.voice = payload
                        # кэш другого голоса не нужен — освобождаем память
                        self._cache = {k: v for k, v in self._cache.items() if k[0] == payload}
                        self._prefetch = collections.deque(self._prefetch_all)
                        if self._silero_ready:
                            self._msg(f"Озвучка: Silero {self._silero.model_id}, голос {self.voice}")
            except Exception as e:  # noqa: BLE001
                self._msg(f"Ошибка озвучки: {e}")
