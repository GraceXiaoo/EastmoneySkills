#!/usr/bin/env python3
"""research-report-review 单一入口（DLL 表面）：PDF → 确定性底稿前缀工件。

本入口封装 review 的确定性预处理链：
    layoutV2 → prepare_workbook_phases(from-layout) → normalize-evidence
并输出一份 task manifest，供 review skill 的 agent 继续完成 MQL 取数（03/04 阶段）后，
由 research_report_pipeline.py 生成 A_原始底稿.xlsx。

设计原则（与宿主 sellside-research-refresh-with-excel20 的 DLL 契约一致）：
  - 本入口只暴露"成功/失败"两种结果与固定产物；调用方不得解析本 skill 的内部错误串。
  - 遇 LAYOUT_SCHEMA_BLOCKED 即停止摄取、保留原始响应并以非 0 退出码上报，不自动降级、不隐瞒。
  - 任何无法恢复的硬失败以非 0 退出码返回，并把原始 stderr 原样写入 manifest.error，不吞异常。
  - 本入口不生成 Excel；Excel 由 research_report_pipeline.py 在 MQL 取数完成后生成。

用法：
    python review_build_workbook.py <pdf> --out-dir <dir> [--report-title T] [--report-date D] [--verification-date V]
退出码：0 = 确定性前缀成功（layout/census/evidence/manifest 已落盘）；非 0 = 硬失败。
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(cmd: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def _find_raw_layout(layout_dir: Path) -> Path | None:
    """call_pdf_layout 输出的原始响应文件命名为 *-版面解析原始响应.json。"""
    candidates = sorted(glob.glob(str(layout_dir / "*-版面解析原始响应.json")))
    return Path(candidates[0]) if candidates else None


def _write_manifest(out_dir: Path, payload: dict) -> None:
    (out_dir / "review_task_manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--report-title", default="研报底稿")
    ap.add_argument("--report-date", default="")
    ap.add_argument("--verification-date", default=datetime.now(timezone.utc).date().isoformat())
    args = ap.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    layout_dir = out_dir / "layout"

    started = datetime.now(timezone.utc).isoformat()
    manifest: dict = {
        "schema_version": 1,
        "pdf": str(args.pdf.resolve()),
        "out_dir": str(out_dir),
        "started_at": started,
        "status": "PENDING",
        "artifacts": {},
        "next_step": "",
        "error": None,
    }

    try:
        # ---- 1. layoutV2 解析 ----
        rc, so, se = _run([
            sys.executable, str(SCRIPTS / "call_pdf_layout.py"),
            "--pdf", str(args.pdf), "--out-dir", str(layout_dir), "--timeout", "180",
        ])
        if rc != 0:
            manifest["status"] = "FAILED"
            manifest["error"] = {"stage": "layoutV2", "exit_code": rc, "stderr": se, "stdout": so}
            manifest["next_step"] = "检查 EM_BASE_URL/EM_API_KEY 凭据与 layoutV2 服务可用性"
            _write_manifest(out_dir, manifest)
            print(f"[review_build_workbook] FAILED at layoutV2: {se.strip()[:300]}", file=sys.stderr)
            return rc

        raw_layout = _find_raw_layout(layout_dir)
        if raw_layout is None:
            manifest["status"] = "FAILED"
            manifest["error"] = {"stage": "layoutV2", "message": "未找到原始响应 JSON", "stdout": so}
            manifest["next_step"] = "检查 call_pdf_layout 输出目录"
            _write_manifest(out_dir, manifest)
            print("[review_build_workbook] FAILED: raw layout json not found", file=sys.stderr)
            return 2

        # ---- 2. prepare_workbook_phases（遇 LAYOUT_SCHEMA_BLOCKED 即停止摄取并上报）----
        census = out_dir / "01_census.json"
        evidence = out_dir / "02_source_evidence.json"
        base_cmd = [
            sys.executable, str(SCRIPTS / "prepare_workbook_phases.py"), "from-layout",
            "--layout-json", str(raw_layout),
            "--census-output", str(census), "--evidence-output", str(evidence),
            "--report-title", args.report_title,
        ]
        if args.report_date:
            base_cmd += ["--report-date", args.report_date]
        base_cmd += ["--verification-date", args.verification_date]

        rc, so, se = _run(base_cmd)
        if rc != 0:
            blocked = "LAYOUT_SCHEMA_BLOCKED" in (so + se)
            manifest["status"] = "BLOCKED" if blocked else "FAILED"
            manifest["error"] = {"stage": "prepare_workbook_phases", "exit_code": rc,
                                 "stderr": se, "stdout": so}
            if blocked:
                manifest["error"]["raw_layout"] = str(raw_layout)
                manifest["next_step"] = (
                    "LAYOUT_SCHEMA_BLOCKED：输入结构无法识别，已停止摄取并保留原始响应 "
                    f"({raw_layout})；需人工复核后请求用户授权，不得自动降级重跑。"
                )
            else:
                manifest["next_step"] = "审查 prepare_workbook_phases 报错"
            _write_manifest(out_dir, manifest)
            print(f"[review_build_workbook] {manifest['status']} at prepare: {se.strip()[:300]}", file=sys.stderr)
            return rc

        # ---- 3. normalize-evidence ----
        norm = out_dir / "02_evidence_normalized.json"
        rc, so, se = _run([
            sys.executable, str(SCRIPTS / "prepare_workbook_phases.py"), "normalize-evidence",
            "--input", str(evidence), "--output", str(norm),
        ])
        if rc != 0:
            manifest["status"] = "FAILED"
            manifest["error"] = {"stage": "normalize-evidence", "exit_code": rc, "stderr": se, "stdout": so}
            manifest["next_step"] = "审查 normalize-evidence 报错"
            _write_manifest(out_dir, manifest)
            return rc

        manifest["status"] = "SUCCESS"
        manifest["artifacts"] = {
            "raw_layout": str(raw_layout),
            "census": str(census),
            "source_evidence": str(evidence),
            "normalized_evidence": str(norm),
        }
        manifest["next_step"] = (
            "确定性前缀完成。由 review skill agent 继续：基于 normalized_evidence 做 MQL 映射(03)与取数(04)，"
            "经 merge_workbook_phases 生成 05_workbook_input.json，再运行 "
            "research_report_pipeline.py 05_workbook_input.json --output A_原始底稿.xlsx，"
            "并产出 A_底稿评测报告.md。"
        )
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_manifest(out_dir, manifest)
        print(f"[review_build_workbook] SUCCESS; manifest -> {out_dir / 'review_task_manifest.json'}")
        return 0

    except Exception as exc:  # 不吞异常：原样落 manifest 并非 0 退出
        manifest["status"] = "FAILED"
        manifest["error"] = {"stage": "unexpected", "exception": repr(exc),
                             "traceback": traceback.format_exc()}
        manifest["next_step"] = "排查未预期异常"
        _write_manifest(out_dir, manifest)
        print(f"[review_build_workbook] UNEXPECTED: {exc!r}", file=sys.stderr)
        return 99


if __name__ == "__main__":
    raise SystemExit(main())
