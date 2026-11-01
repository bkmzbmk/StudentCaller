"""Проверка озвучки Silero без запуска программы.

Запуск: TestVoice.bat (или python tools/test_voice.py [голос] [текст]).
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from student_caller.config import MODELS_DIR  # noqa: E402
from student_caller.speech import SileroEngine, play_wav  # noqa: E402


def main() -> int:
    voice = sys.argv[1] if len(sys.argv) > 1 else "xenia"
    text = " ".join(sys.argv[2:]) or "К доске выходят: Кузнецов Дмитрий Игоревич. Соловьёва Арина Евгеньевна."
    print(f"Python {sys.version.split()[0]}")
    try:
        import torch

        print(f"torch {torch.__version__}, потоков: {torch.get_num_threads()}")
    except ImportError as e:
        print(f"[ОШИБКА] torch не установлен: {e}")
        return 1

    engine = SileroEngine(MODELS_DIR, lambda m: print("  " + m))
    t = time.perf_counter()
    engine.load()
    print(f"Модель {engine.model_id} загружена за {time.perf_counter() - t:.1f} с")
    print(f"Голоса: {', '.join(engine.speakers)}")

    t = time.perf_counter()
    audio = engine.synth(text, voice)
    dur = audio.numel() / 48000
    print(f"Синтез «{text}» голосом {voice}: {time.perf_counter() - t:.2f} с, длительность {dur:.1f} с")
    print("Воспроизведение...")
    play_wav(engine.to_wav([audio]))
    print("[OK] Silero работает")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print(f"[ОШИБКА] {e}")
        code = 1
    sys.exit(code)
