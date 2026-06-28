#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
build_exe.py — сборка CalcNumLockTray в EXE через PyInstaller.

Класть в корень проекта рядом с:
  calc_numlock_tray.pyw
  functions.py
  styles.py
  standard_calc.py
  standard_calc_engine.py
  pro_soft.py
  pro_secure.py

Базовый запуск:
  python build_exe.py

Если PyInstaller не установлен:
  python build_exe.py --install-pyinstaller

Полезные режимы:
  python build_exe.py --onedir
  python build_exe.py --skip-tests
  python build_exe.py --no-zip
"""
from __future__ import annotations

import argparse
import compileall
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path

APP_BASENAME = "NumLockCalc_2026_9.0.1_FREE_CORE_RELEASE"
ENTRY_FILE = "calc_numlock_tray.pyw"
ICON_FILE = "calculator_icon.ico"

CORE_PY_FILES = [
    "calc_numlock_tray.pyw",
    "functions.py",
    "styles.py",
    "standard_calc.py",
    "standard_calc_engine.py",
]
PRO_PY_FILES = []
PY_FILES = CORE_PY_FILES

CORE_DATA_FILES = [
    "Values.txt",
    "settings.json",
]
PRO_DATA_FILES = []
DATA_FILES = CORE_DATA_FILES


def project_py_files(root: Path) -> list[str]:
    return CORE_PY_FILES + [name for name in PRO_PY_FILES if (root / name).exists()]


def project_data_files(root: Path) -> list[str]:
    return CORE_DATA_FILES + [name for name in PRO_DATA_FILES if (root / name).exists()]

OPTIONAL_FILES = [
    ICON_FILE,
]

HIDDEN_IMPORTS = [
    "PyQt5",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    "PyQt5.QtWinExtras",
    "keyboard",
]


def run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    print("\n> " + " ".join(cmd))
    return subprocess.run(cmd, cwd=str(cwd), check=check)


def require_project_root(root: Path) -> None:
    missing = [name for name in CORE_PY_FILES if not (root / name).exists()]
    if missing:
        raise SystemExit(
            "Не найдены обязательные файлы проекта:\n  - "
            + "\n  - ".join(missing)
            + "\n\nЗапускай build_exe.py из корня проекта CalcNumLockTray."
        )


def check_pyinstaller(root: Path, install: bool) -> None:
    probe = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if probe.returncode == 0:
        print(f"PyInstaller: {probe.stdout.strip()}")
        return
    if not install:
        raise SystemExit(
            "PyInstaller не установлен. Выполни:\n"
            "  python -m pip install pyinstaller\n\n"
            "или запусти сборку так:\n"
            "  python build_exe.py --install-pyinstaller"
        )
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"], root)


def compile_sources(root: Path) -> None:
    print("\nПроверка синтаксиса Python-файлов...")
    ok = True
    for file_name in project_py_files(root):
        path = root / file_name
        ok = compileall.compile_file(str(path), quiet=1) and ok
    if not ok:
        raise SystemExit("Синтаксическая проверка не пройдена. EXE не собираю.")


def run_tests(root: Path, skip: bool) -> None:
    if skip:
        print("\nТесты пропущены по --skip-tests.")
        return

    tests_dir = root / "tests"
    single_test = root / "test_standard_calc_engine.py"

    if tests_dir.exists():
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], root)
    elif single_test.exists():
        run([sys.executable, "-m", "unittest", "test_standard_calc_engine.py", "-v"], root)
    else:
        print("\nТесты не найдены: пропускаю. Да, идеальный мир опять не завезли.")


def add_data_arg(root: Path, name: str) -> list[str]:
    path = root / name
    if not path.exists():
        return []
    # PyInstaller: Windows и Unix одинаково принимает os.pathsep.
    return ["--add-data", f"{path}{os.pathsep}."]


def build_exe(root: Path, stamp: str, onefile: bool) -> Path:
    exe_name = f"{stamp}_{APP_BASENAME}"
    dist_dir = root / "dist"
    build_dir = root / "build"
    spec_file = root / f"{exe_name}.spec"

    for p in (dist_dir / exe_name, dist_dir / f"{exe_name}.exe", build_dir / exe_name, spec_file):
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            p.unlink()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        exe_name,
    ]

    cmd.append("--onefile" if onefile else "--onedir")

    icon = root / ICON_FILE
    if icon.exists():
        cmd.extend(["--icon", str(icon)])

    for hidden in HIDDEN_IMPORTS:
        cmd.extend(["--hidden-import", hidden])

    for name in project_data_files(root) + OPTIONAL_FILES:
        cmd.extend(add_data_arg(root, name))

    cmd.append(str(root / ENTRY_FILE))
    run(cmd, root)

    output = dist_dir / (f"{exe_name}.exe" if onefile else exe_name)
    if not output.exists():
        raise SystemExit(f"PyInstaller завершился, но результат не найден: {output}")
    return output


def copy_runtime_files(root: Path, package_dir: Path) -> None:
    """Кладёт рядом с exe стартовые json/txt, если приложение ожидает их рядом.
    Для onefile это не обязательно, но удобно для первого запуска и ручной правки настроек.
    """
    package_dir.mkdir(parents=True, exist_ok=True)
    for name in project_data_files(root):
        src = root / name
        if src.exists():
            shutil.copy2(src, package_dir / name)


def make_release_package(root: Path, built: Path, stamp: str, onefile: bool, make_zip: bool) -> Path:
    release_root = root / "release"
    release_dir = release_root / f"{stamp}_{APP_BASENAME}"
    if release_dir.exists():
        shutil.rmtree(release_dir, ignore_errors=True)
    release_dir.mkdir(parents=True, exist_ok=True)

    if onefile:
        shutil.copy2(built, release_dir / built.name)
        copy_runtime_files(root, release_dir)
    else:
        target = release_dir / built.name
        shutil.copytree(built, target)
        copy_runtime_files(root, target)


    if not make_zip:
        return release_dir

    zip_path = release_root / f"{stamp}_{APP_BASENAME}_full.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in release_dir.rglob("*"):
            zf.write(file, file.relative_to(release_root))
    return zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сборка CalcNumLockTray в exe")
    parser.add_argument("--install-pyinstaller", action="store_true", help="установить PyInstaller, если его нет")
    parser.add_argument("--skip-tests", action="store_true", help="не запускать unittest перед сборкой")
    parser.add_argument("--onedir", action="store_true", help="собрать папку вместо одного exe")
    parser.add_argument("--no-zip", action="store_true", help="не создавать zip-архив релиза")
    parser.add_argument("--stamp", default="", help="ручной штамп имени, например 2026-05-11_12-00")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parent
    stamp = args.stamp.strip() or datetime.now().strftime("%Y-%m-%d_%H-%M")
    onefile = not args.onedir

    require_project_root(root)
    check_pyinstaller(root, args.install_pyinstaller)
    compile_sources(root)
    run_tests(root, args.skip_tests)

    built = build_exe(root, stamp, onefile)
    package = make_release_package(root, built, stamp, onefile, not args.no_zip)

    print("\nГотово.")
    print(f"EXE: {built}")
    print(f"Релиз: {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
