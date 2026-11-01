"""Проверить библиотеки из requirements.txt и установить недостающие.

Строки с пометкой ``# optional`` необязательны: если их не удалось
поставить, программа всё равно запустится (например, без torch озвучка
переключится с Silero на голоса Windows).

Код выхода: 0 — все обязательные библиотеки на месте, 1 — нет.
"""

import re
import subprocess
import sys
from pathlib import Path

try:
    from importlib import metadata
except ImportError:  # Python < 3.8
    print("Нужен Python 3.8 или новее")
    sys.exit(1)

REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:(>=|==)\s*([0-9][0-9A-Za-z.]*))?")


def version_tuple(v):
    return tuple(int(p) for p in re.findall(r"\d+", v)[:4])


def parse(req_file: Path):
    reqs = []
    for raw in req_file.read_text(encoding="utf-8").splitlines():
        line, _, comment = raw.partition("#")
        line = line.split(";", 1)[0].strip()
        if not line:
            continue
        m = REQ_RE.match(line)
        if not m:
            continue
        name, op, wanted = m.groups()
        reqs.append({"spec": line, "name": name, "op": op, "wanted": wanted,
                     "optional": "optional" in comment.lower()})
    return reqs


def is_ok(req) -> str:
    """Пустая строка — всё в порядке, иначе описание проблемы."""
    try:
        installed = metadata.version(req["name"])
    except metadata.PackageNotFoundError:
        return "не установлена"
    if req["op"] and req["wanted"]:
        if req["op"] == ">=":
            ok = version_tuple(installed) >= version_tuple(req["wanted"])
        else:
            ok = installed == req["wanted"]
        if not ok:
            return f"установлена {installed}, нужна {req['op']}{req['wanted']}"
    return ""


def pip_install(spec: str) -> bool:
    base = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", spec]
    if subprocess.call(base) == 0:
        return True
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if not in_venv:
        print("  Пробую установить для текущего пользователя...")
        return subprocess.call(base[:-1] + ["--user", spec]) == 0
    return False


def main() -> int:
    req_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "requirements.txt"
    reqs = parse(req_file)

    missing = []
    for r in reqs:
        problem = is_ok(r)
        if problem:
            print(f"  [--] {r['name']}: {problem}")
            missing.append(r)
        else:
            print(f"  [OK] {r['name']} {metadata.version(r['name'])}")
    if not missing:
        return 0

    print()
    print("Устанавливаю недостающие библиотеки...")
    if any(r["name"].lower() == "torch" for r in missing):
        print("  (torch весит несколько сотен МБ - установка может занять несколько минут)")
    failed_required, failed_optional = [], []
    for r in missing:
        print(f"\n>>> {r['spec']}")
        if not pip_install(r["spec"]) or is_ok(r):
            (failed_optional if r["optional"] else failed_required).append(r["name"])

    print()
    if failed_optional:
        print("[!] Не удалось установить необязательные библиотеки: " + ", ".join(failed_optional))
        print("    Программа запустится, озвучка будет через голоса Windows.")
    if failed_required:
        print("[ОШИБКА] Не удалось установить: " + ", ".join(failed_required))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
