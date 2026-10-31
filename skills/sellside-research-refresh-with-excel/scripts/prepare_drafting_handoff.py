#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


HOST_SKILL = "sellside-research-refresh-with-excel20"
FALLBACK_HOST_VERSION = "3.0.4"
DRAFTING_SKILL = "periodic-report-drafting"


def _skill_md_version() -> str:
    """从 SKILL.md frontmatter 读取版本号（单一真源），缺失时退回常量。"""
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    try:
        for line in skill_md.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("version:"):
                value = stripped.split(":", 1)[1].strip().strip("\"'")
                if value:
                    return value
    except OSError:
        pass
    return FALLBACK_HOST_VERSION


HOST_VERSION = _skill_md_version()
# B 沿用 A 的 5-Sheet 命名：事实在 10_研报快照，预测在 30_预测框架。
# 阶段 4 门禁只要求这两个核心 Sheet 可读；其余 Sheet（如 20_研报底稿、90_执行日志）
# 由仿写 skill 按需消费，不作为硬门禁。
CORE_SHEETS = {"10_研报快照", "30_预测框架"}
CORE_FACT_SHEET = "10_研报快照"
GENERATOR_SCRIPT = "prepare_drafting_handoff.py finalize"
DELIVERY_STATES = {
    "NEEDS_VISUAL_REVIEW",
    "NEEDS_RESEARCH_AND_VISUAL_REVIEW",
    "DRAFT_NEEDS_VISUAL_REVIEW",
    "DRAFT_NEEDS_RESEARCH_AND_VISUAL_REVIEW",
    "COMPLETE",
    "COMPLETE_WITH_OMISSIONS",
    "AUTHORIZED_DRAFT",
    "COMPLETE_WITH_UNVERIFIED_LAYOUT",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact(path: Path, media_type: str) -> dict[str, Any]:
    path = path.resolve()
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "media_type": media_type,
    }


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_source_md_meta(html: str) -> str | None:
    """提取 HTML 内 `<meta name="source-md-sha256" content="...">` 指纹。"""
    for match in re.finditer(r"<meta\b[^>]*>", html, re.IGNORECASE):
        tag = match.group(0)
        if not re.search(
            r"name\s*=\s*[\"']source-md-sha256[\"']", tag, re.IGNORECASE
        ):
            continue
        content = re.search(
            r"content\s*=\s*[\"']([0-9a-fA-F]{64})[\"']", tag, re.IGNORECASE
        )
        if content:
            return content.group(1).lower()
    return None


def _verify_artifact(artifact: dict[str, Any]) -> Path:
    path = Path(str(artifact.get("path", "")))
    if not path.is_file():
        raise ValueError(f"artifact missing: {path}")
    if path.stat().st_size != artifact.get("size_bytes"):
        raise ValueError(f"artifact size mismatch: {path}")
    if _sha256(path) != artifact.get("sha256"):
        raise ValueError(f"artifact hash mismatch: {path}")
    return path


def load_confirmed_stage3(handoff_path: Path) -> tuple[dict[str, Any], Path]:
    handoff = _load_json(handoff_path)
    if handoff.get("stage") != 3 or handoff.get("status") != "CONFIRMED":
        raise ValueError("stage-3 handoff must be CONFIRMED")
    workbook_paths = [
        _verify_artifact(item)
        for item in handoff.get("outputs", [])
        if str(item.get("path", "")).endswith(".xlsx")
    ]
    if len(workbook_paths) != 1:
        raise ValueError("stage-3 handoff must contain exactly one target workbook")
    for validation in handoff.get("validation", []):
        if validation.get("status") != "PASS":
            raise ValueError("stage-3 validation is not fully PASS")
    return handoff, workbook_paths[0]


def _run_json_command(command: list[str], output_path: Path) -> dict[str, Any]:
    process = subprocess.run(command, capture_output=True, text=True)
    receipt = {
        "status": "PASS" if process.returncode == 0 else "FAIL",
        "command": command,
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
    }
    output_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if process.returncode != 0:
        raise ValueError(f"command failed: {process.stdout}{process.stderr}")
    return receipt


def _host_side_probe(workbook_path: Path, index_path: Path) -> dict[str, Any]:
    """仿写 skill 的 workbook_probe.py 缺失时的宿主侧降级扫描。

    只做结构校验（Sheet 存在性 + 数值单元格计数），产出与官方 probe 同形的
    excel-index.json，确保门禁可继续。完整单元格级 probe 由仿写侧补齐后启用。
    """
    import openpyxl  # 延迟导入，避免在未安装环境的 prepare 路径外被强依赖

    wb = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    sheets = []
    try:
        for name in wb.sheetnames:
            ws = wb[name]
            numeric = 0
            for row in ws.iter_rows(values_only=True):
                for value in row:
                    if isinstance(value, bool):
                        continue
                    if isinstance(value, (int, float)):
                        numeric += 1
            sheets.append(
                {
                    "sheet": name,
                    "status": "READABLE",
                    "counts": {"numeric_values": numeric},
                }
            )
    finally:
        wb.close()
    index = {"workbook": str(workbook_path.resolve()), "sheets": sheets}
    index_path.write_text(
        json.dumps(index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return index


def prepare(
    stage3_handoff_path: Path,
    reference_pdf: Path,
    drafting_skill_dir: Path,
    target_name: str,
    security_code: str,
    report_period: str,
    cutoff_date: str,
    run_dir: Path,
) -> dict[str, Any]:
    stage3, workbook_path = load_confirmed_stage3(stage3_handoff_path)
    if not reference_pdf.is_file() or reference_pdf.suffix.lower() != ".pdf":
        raise ValueError("reference PDF is missing or invalid")

    work_dir = run_dir / "work"
    delivery_dir = run_dir / "delivery"
    work_dir.mkdir(parents=True, exist_ok=True)
    delivery_dir.mkdir(parents=True, exist_ok=True)
    environment_receipt = work_dir / "environment-receipt.json"
    probe_receipt = work_dir / "workbook-probe-receipt.json"
    index_path = work_dir / "excel-index.json"

    drafting_scripts = drafting_skill_dir / "scripts"
    check_handoff = drafting_scripts / "check_handoff.py"
    workbook_probe = drafting_scripts / "workbook_probe.py"
    degraded_notes: list[str] = []

    # 环境预检：仿写 check_handoff.py 存在则调用，否则记录降级，不硬阻塞。
    if check_handoff.is_file():
        _run_json_command(
            [sys.executable, str(check_handoff), "--environment"],
            environment_receipt,
        )
    else:
        environment_receipt.write_text(
            json.dumps(
                {
                    "status": "SKIPPED",
                    "reason": "drafting check_handoff.py not found; host-side only",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        degraded_notes.append("环境预检 check_handoff.py 缺失，已跳过（仿写侧待补齐）")

    # 工作簿探测：官方 workbook_probe.py 存在则调用；否则宿主侧降级扫描。
    if workbook_probe.is_file():
        _run_json_command(
            [
                sys.executable,
                str(workbook_probe),
                "scan",
                str(workbook_path),
                "--output",
                str(index_path),
            ],
            probe_receipt,
        )
        index = _load_json(index_path)
    else:
        index = _host_side_probe(workbook_path, index_path)
        probe_receipt.write_text(
            json.dumps(
                {
                    "status": "DEGRADED",
                    "reason": "drafting workbook_probe.py not found; host-side structural scan used",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        degraded_notes.append("工作簿探测 workbook_probe.py 缺失，已用宿主侧结构扫描降级（未做完整单元格级 probe）")

    sheets = {str(item["sheet"]): item for item in index.get("sheets", [])}
    missing = CORE_SHEETS - set(sheets)
    if missing:
        raise ValueError(f"target workbook lacks drafting core sheets: {sorted(missing)!r}")
    blocked = [
        name for name in CORE_SHEETS if sheets[name].get("status") == "CONFIRM_REQUIRED"
    ]
    if blocked:
        raise ValueError(f"drafting core sheets are unreadable: {sorted(blocked)!r}")
    if int(sheets[CORE_FACT_SHEET].get("counts", {}).get("numeric_values", 0)) < 1:
        raise ValueError(f"{CORE_FACT_SHEET} contains no readable numeric facts")
    warnings = [
        f"{item['sheet']}: {item['status']}"
        for item in index.get("sheets", [])
        if item.get("status") != "READABLE"
    ]
    warnings.extend(degraded_notes)

    request = {
        "schema_version": 1,
        "task_id": stage3["task_id"],
        "status": "READY_WITH_WARNINGS" if warnings else "READY",
        "host": {"skill": HOST_SKILL, "version": HOST_VERSION},
        "consumer": {
            "skill": DRAFTING_SKILL,
            "mode": "完整流程",
        },
        "inputs": {
            "stage3_handoff": _artifact(stage3_handoff_path, "application/json"),
            "reference_pdf": _artifact(reference_pdf, "application/pdf"),
            "target_workbook": _artifact(
                workbook_path,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        },
        "target": {
            "name": target_name,
            "security_code": security_code,
            "report_period": report_period,
            "cutoff_date": cutoff_date,
        },
        "output_dir": str(delivery_dir.resolve()),
        "preflight": {
            "excel_index": _artifact(index_path, "application/json"),
            "environment_receipt": _artifact(environment_receipt, "application/json"),
            "probe_receipt": _artifact(probe_receipt, "application/json"),
            "core_sheets": sorted(CORE_SHEETS),
            "warnings": warnings,
        },
    }
    request_path = work_dir / "stage-4-request.json"
    request_path.write_text(
        json.dumps(request, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return request


def finalize(
    request_path: Path,
    markdown_path: Path,
    html_path: Path,
    workflow_state_path: Path,
    delivery_notes_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    request = _load_json(request_path)
    if request.get("status") not in {"READY", "READY_WITH_WARNINGS"}:
        raise ValueError("stage-4 request is not ready")
    for artifact in request.get("inputs", {}).values():
        _verify_artifact(artifact)
    for path in (
        markdown_path,
        html_path,
        workflow_state_path,
        delivery_notes_path,
    ):
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"drafting output missing or empty: {path}")
    state = _load_json(workflow_state_path)
    if state.get("status") not in DELIVERY_STATES:
        raise ValueError("drafting workflow state is not a recognized delivery state")
    notes = _load_json(delivery_notes_path)
    if not isinstance(notes, list):
        raise ValueError("delivery-notes.json must contain a list")
    html = html_path.read_text(encoding="utf-8")
    if "<html" not in html.lower():
        raise ValueError("drafting HTML is not a complete HTML document")
    markdown_digest = _sha256(markdown_path)
    meta_digest = _extract_source_md_meta(html)
    if meta_digest is None:
        raise ValueError(
            "drafting HTML lacks source-md-sha256 meta fingerprint"
        )
    if meta_digest != markdown_digest:
        raise ValueError(
            "drafting HTML source-md-sha256 meta does not match the markdown hash"
        )

    limitations = list(request.get("preflight", {}).get("warnings", []))
    if state["status"] not in {"COMPLETE", "COMPLETE_WITH_OMISSIONS", "AUTHORIZED_DRAFT"}:
        limitations.append(f"drafting workflow state: {state['status']}")
    inputs = [
        request["inputs"]["stage3_handoff"],
        request["inputs"]["reference_pdf"],
        request["inputs"]["target_workbook"],
        _artifact(request_path, "application/json"),
    ]
    outputs = [
        _artifact(markdown_path, "text/markdown"),
        _artifact(html_path, "text/html"),
        _artifact(workflow_state_path, "application/json"),
        _artifact(delivery_notes_path, "application/json"),
        request["preflight"]["excel_index"],
    ]
    handoff = {
        "schema_version": 1,
        "task_id": request["task_id"],
        "stage": 4,
        "status": "CONFIRMED",
        "producer": {
            "skill": DRAFTING_SKILL,
            "mode": "完整流程",
        },
        "generator": {
            "skill": HOST_SKILL,
            "script": GENERATOR_SCRIPT,
            "version": HOST_VERSION,
        },
        "engine_receipt": {
            "workflow_state": {
                "path": str(workflow_state_path.resolve()),
                "sha256": _sha256(workflow_state_path),
                "status": state["status"],
            },
            "markdown_sha256": markdown_digest,
            "html_sha256": _sha256(html_path),
            "source_md_sha256_meta": meta_digest,
        },
        "inputs": inputs,
        "outputs": outputs,
        "started_at": state.get("generated_at", _now()),
        "completed_at": _now(),
        "validation": [
            {
                "name": "workbook_probe core sheets",
                "status": "PASS",
                "receipt_path": request["preflight"]["excel_index"]["path"],
            },
            {
                "name": "drafting MD and HTML generation",
                "status": "PASS",
                "receipt_path": str(workflow_state_path.resolve()),
            },
            {
                "name": "delivery notes",
                "status": "PASS",
                "receipt_path": str(delivery_notes_path.resolve()),
            },
        ],
        "limitations": limitations,
        "error": None,
        "resume": {
            "next_stage": 5,
            "requires_user_confirmation": False,
            "input_hashes": {
                item["path"]: item["sha256"] for item in inputs
            },
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return handoff


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("stage3_handoff", type=Path)
    prepare_parser.add_argument("reference_pdf", type=Path)
    prepare_parser.add_argument("--drafting-skill-dir", type=Path, required=True)
    prepare_parser.add_argument("--target-name", required=True)
    prepare_parser.add_argument("--security-code", required=True)
    prepare_parser.add_argument("--report-period", required=True)
    prepare_parser.add_argument("--cutoff-date", required=True)
    prepare_parser.add_argument("--run-dir", type=Path, required=True)
    finalize_parser = subparsers.add_parser("finalize")
    finalize_parser.add_argument("request", type=Path)
    finalize_parser.add_argument("markdown", type=Path)
    finalize_parser.add_argument("html", type=Path)
    finalize_parser.add_argument("workflow_state", type=Path)
    finalize_parser.add_argument("delivery_notes", type=Path)
    finalize_parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(
            args.stage3_handoff,
            args.reference_pdf,
            args.drafting_skill_dir,
            args.target_name,
            args.security_code,
            args.report_period,
            args.cutoff_date,
            args.run_dir,
        )
    else:
        result = finalize(
            args.request,
            args.markdown,
            args.html,
            args.workflow_state,
            args.delivery_notes,
            args.output,
        )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
