#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe system Python 3 + skill requirements (no per-skill .venv)."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = SKILL_ROOT / "requirements.txt"
ENV_ERROR = "ENV_UNSATISFIED"
ENV_MESSAGE = (
    "Python 3 环境不满足：系统无 python3，或缺少 requirements.txt 中的依赖。"
    "请在宿主机执行：pip3 install -r requirements.txt"
)

_IMPORT_ALIASES = {
    "python-docx": "docx",
}


def _system_python3() -> list[str] | None:
    if shutil.which("python3"):
        return ["python3"]
    if sys.platform == "win32" and shutil.which("py"):
        return ["py", "-3"]
    return None


def _packages_from_requirements() -> list[str]:
    if not REQUIREMENTS.is_file():
        return []
    packages: list[str] = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\s]", line, maxsplit=1)[0].strip()
        if name:
            packages.append(name)
    return packages


def _import_name(package: str) -> str:
    return _IMPORT_ALIASES.get(package.lower(), package.replace("-", "_"))


def _missing_imports(python_cmd: list[str]) -> list[str]:
    missing: list[str] = []
    for package in _packages_from_requirements():
        module = _import_name(package)
        code = f"import importlib; importlib.import_module({module!r})"
        proc = subprocess.run(
            python_cmd + ["-c", code],
            cwd=SKILL_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            missing.append(package)
    return missing


def _pip_install(python_cmd: list[str]) -> bool:
    if not REQUIREMENTS.is_file():
        return True
    proc = subprocess.run(
        python_cmd + ["-m", "pip", "install", "-r", str(REQUIREMENTS)],
        cwd=SKILL_ROOT,
        check=False,
    )
    return proc.returncode == 0


def probe(*, ensure: bool = False) -> dict:
    python_cmd = _system_python3()
    if not python_cmd:
        return {"ok": False, "error": ENV_ERROR, "message": ENV_MESSAGE}

    missing = _missing_imports(python_cmd)
    if missing and ensure:
        if not _pip_install(python_cmd):
            return {
                "ok": False,
                "error": ENV_ERROR,
                "message": f"pip install 失败，缺少依赖: {', '.join(missing)}",
                "missing_packages": missing,
            }
        missing = _missing_imports(python_cmd)

    if missing:
        return {
            "ok": False,
            "error": ENV_ERROR,
            "message": f"缺少依赖: {', '.join(missing)}。请执行: pip3 install -r requirements.txt",
            "missing_packages": missing,
        }

    return {
        "ok": True,
        "mode": "system",
        "python": " ".join(python_cmd),
        "runner": "scripts/run_py.cmd" if sys.platform == "win32" else "scripts/run_py.sh",
        "invoke": "python3",
        "venv": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Ensure system Python 3 runtime for skill")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only probe system python3 and imports",
    )
    parser.add_argument(
        "--ensure",
        action="store_true",
        help="If imports missing, run pip install -r requirements.txt on system python",
    )
    args = parser.parse_args()
    result = probe(ensure=args.ensure and not args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
