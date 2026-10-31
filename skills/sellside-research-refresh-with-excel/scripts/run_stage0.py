#!/usr/bin/env python3
"""阶段 0 产物校验闸门：校验内置 review 交付的最终产物，写 stage-0-handoff.json。

本 skill（sellside-research-refresh-with-excel20）为自包含单体，review 完整逻辑已
vendor 内置在 bundle/review/，运行时不再用 Skill 工具加载外部子 skill。阶段 0 的驱动
按产物 SKILL.md §2 直接调用 bundle/review/scripts/*；本脚本只在其完成后做最终产物的
存在性 + SHA-256 校验，并据此落 CONFIRMED 或 BLOCKED。

本脚本**只做最终产物校验**，不引用 review 的任何内部入口（如 review_build_workbook.py），
也不在此驱动 review 流水线——驱动逻辑见产物 SKILL.md §2。

用法：
  # 在阶段 0 完成「生成研报底稿」后，校验双产物并落 CONFIRMED/BLOCKED handoff
  python run_stage0.py --final --out-dir <dir> --task-id <id>
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1
SOURCE_WORKBOOK_EXACT = "A_原始底稿.xlsx"
SOURCE_WORKBOOK_PATTERNS = ("*_研报底稿抽取.xlsx",)
REPORT_EXACT = "A_底稿评测报告.md"
REPORT_PATTERNS = ("*_底稿评测报告.md", "*_研报底稿核验报告.md")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_artifact(path: Path) -> dict:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
        "media_type": "application/octet-stream",
    }


def _resolve_artifact(out_dir: Path, exact: str, patterns: tuple[str, ...]) -> tuple[Path | None, str | None]:
    exact_path = out_dir / exact
    if exact_path.exists():
        return exact_path, None
    found: dict[str, Path] = {}
    for pattern in patterns:
        for p in out_dir.glob(pattern):
            if p.is_file():
                found.setdefault(p.name, p)
    expected = f"{exact} 或 {'/'.join(patterns)}"
    if len(found) == 1:
        return next(iter(found.values())), None
    if len(found) > 1:
        names = ", ".join(sorted(found))
        return None, f"{expected} 匹配到多个文件: {names}"
    return None, expected


def _write_handoff(out_dir: Path, task_id: str, status: str, **kw) -> Path:
    handoff = {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "stage": 0,
        "status": status,
        "producer": {"skill": "research-report-review", "mode": "orchestration-boundary"},
        "started_at": kw.get("started_at", _now()),
        "completed_at": _now(),
        "inputs": kw.get("inputs", []),
        "outputs": kw.get("outputs", []),
        "validation": kw.get("validation", []),
        "limitations": kw.get("limitations", []),
        "error": kw.get("error"),
        "resume": kw.get("resume"),
    }
    p = out_dir / "stage-0-handoff.json"
    p.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def run_final(args) -> int:
    """校验最终双产物存在+哈希，落 CONFIRMED/BLOCKED。"""
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    started = _now()
    workbook, workbook_error = _resolve_artifact(out_dir, SOURCE_WORKBOOK_EXACT, SOURCE_WORKBOOK_PATTERNS)
    report, report_error = _resolve_artifact(out_dir, REPORT_EXACT, REPORT_PATTERNS)
    validation = [
        {"check": "source_workbook:" + "|".join((SOURCE_WORKBOOK_EXACT, *SOURCE_WORKBOOK_PATTERNS)),
         "status": "PASS" if workbook else "FAIL", "resolved": str(workbook) if workbook else None},
        {"check": "review_report:" + "|".join((REPORT_EXACT, *REPORT_PATTERNS)),
         "status": "PASS" if report else "FAIL", "resolved": str(report) if report else None},
    ]
    missing = [err for err in (workbook_error, report_error) if err]
    if missing:
        hp = _write_handoff(out_dir, args.task_id, "BLOCKED", started_at=started,
                            validation=validation,
                            error={"category": "MISSING_FINAL_ARTIFACTS",
                                   "message": f"缺失最终产物: {missing}",
                                   "suggested_next": "确认 review 已完整执行「生成研报底稿」并产出 *_研报底稿抽取.xlsx（或 A_原始底稿.xlsx）与底稿评测/核验报告 md（或 A_底稿评测报告.md）"},
                            resume={"blocked_at_stage": 0, "missing": missing})
        print(f"[stage0] BLOCKED missing {missing} -> {hp}")
        return 3
    out_arts = [_file_artifact(workbook), _file_artifact(report)]
    manifest = out_dir / "review_task_manifest.json"
    if manifest.exists():
        out_arts.append(_file_artifact(manifest))
    hp = _write_handoff(out_dir, args.task_id, "CONFIRMED", started_at=started,
                        outputs=out_arts,
                        validation=validation + [{"check": "sha256_recorded", "status": "PASS"}])
    print(f"[stage0] CONFIRMED -> {hp}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--final", action="store_true", required=True,
                    help="校验 review 交付的最终产物并落 CONFIRMED/BLOCKED handoff")
    args = ap.parse_args()
    return run_final(args)


if __name__ == "__main__":
    raise SystemExit(main())
