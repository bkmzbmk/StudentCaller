"""Проверка, что все библиотеки из requirements.txt установлены.

Код выхода: 0 — всё на месте, 1 — чего-то не хватает.
"""

import re
import sys
from pathlib import Path

try:
    from importlib import metadata
except ImportError:  # Python < 3.8
    print("Нужен Python 3.8 или новее")
    sys.exit(1)

REQ_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*(?:(>=|==)\s*([0-9][0-9A-Za-z.]*))?")


def version_tuple(v):
    return tuple(int(p) if p.isdigit() else 0 for p in re.findall(r"\d+", v)[:4])


def main() -> int:
    req_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "requirements.txt"
    missing = []
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        # маркеры окружения вида ; sys_platform == "win32" — не проверяем
        line = line.split(";", 1)[0].strip()
        m = REQ_RE.match(line)
        if not m:
            continue
        name, op, wanted = m.groups()
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            missing.append(f"{name} (не установлена)")
            continue
        if op and wanted:
            ok = version_tuple(installed) >= version_tuple(wanted) if op == ">=" else installed == wanted
            if not ok:
                missing.append(f"{name} (установлена {installed}, нужна {op}{wanted})")
                continue
        print(f"  [OK] {name} {installed}")
    if missing:
        for item in missing:
            print(f"  [--] {item}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
