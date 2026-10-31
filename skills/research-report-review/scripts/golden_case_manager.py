#!/usr/bin/env python3
"""Index, verify, match, and export user-accepted golden cases."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
CASES_REL = Path("examples/golden-cases")
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
# 文本类清单文件先按 LF 归一化再算指纹：清单登记在 LF 检出下产生，Windows 的
# `core.autocrlf=true` 会把文本转成 CRLF，按二进制读取会让指纹无端失配。
# 二进制文件（pdf / xlsx）保持原始字节，归一化其内容会误判。
TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".yaml", ".yml", ".mql"}


def _normalise_line_endings(payload: bytes) -> bytes:
    return payload.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def file_digest(path: Path) -> tuple[str, int]:
    """Return ``(sha256, size)`` of a case file, normalising text line endings first."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        payload = _normalise_line_endings(path.read_bytes())
        return hashlib.sha256(payload).hexdigest(), len(payload)
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def sha256(path: Path) -> str:
    return file_digest(path)[0]


def load_cases(skill_root: Path) -> list[tuple[Path, dict]]:
    result = []
    base = skill_root / CASES_REL
    if not base.exists():
        return result
    for manifest_path in sorted(base.glob("*/manifest.json")):
        result.append((manifest_path.parent, json.loads(manifest_path.read_text("utf-8"))))
    return result


def inspect_xlsx(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        sheets = [node.attrib["name"] for node in workbook.findall(".//m:sheets/m:sheet", NS)]
        mql_count = 0
        for name in archive.namelist():
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml"):
                root = ET.fromstring(archive.read(name))
                for formula in root.findall(".//m:f", NS):
                    if "mql(" in (formula.text or "").lower():
                        mql_count += 1
        media_count = len(
            [name for name in archive.namelist() if name.startswith("xl/media/") and not name.endswith("/")]
        )
    return {"sheets": sheets, "mql_formula_count": mql_count, "media_count": media_count}


def verify_case(case_dir: Path, manifest: dict) -> dict:
    errors: list[str] = []
    for name, spec in manifest.get("files", {}).items():
        path = case_dir / name
        if not path.is_file():
            errors.append(f"missing file: {name}")
            continue
        actual_hash, actual_size = file_digest(path)
        if actual_hash != spec.get("sha256"):
            errors.append(f"sha256 mismatch: {name}")
        expected_size = spec.get("size_bytes")
        if expected_size is not None and actual_size != expected_size:
            errors.append(f"size mismatch: {name}")
    workbook_path = case_dir / "expected.xlsx"
    workbook_actual = None
    if workbook_path.is_file():
        try:
            workbook_actual = inspect_xlsx(workbook_path)
            expected = manifest.get("expected_workbook", {})
            for key in ("sheets", "mql_formula_count", "media_count"):
                if key in expected and workbook_actual.get(key) != expected[key]:
                    errors.append(f"workbook {key} mismatch")
        except Exception as exc:  # surface deterministic evidence without hiding it
            errors.append(f"workbook inspection failed: {type(exc).__name__}: {exc}")
    return {
        "case_id": manifest.get("case_id"),
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "workbook": workbook_actual,
    }


def command_list(args: argparse.Namespace) -> int:
    cases = []
    for case_dir, manifest in load_cases(args.skill_root):
        cases.append(
            {
                "case_id": manifest.get("case_id"),
                "title": manifest.get("title"),
                "status": manifest.get("case_status"),
                "path": str(case_dir),
            }
        )
    print(json.dumps({"cases": cases}, ensure_ascii=False, indent=2))
    return 0


def command_verify(args: argparse.Namespace) -> int:
    for case_dir, manifest in load_cases(args.skill_root):
        if manifest.get("case_id") == args.case_id:
            result = verify_case(case_dir, manifest)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["status"] == "PASS" else 2
    print(json.dumps({"status": "NOT_FOUND", "case_id": args.case_id}, ensure_ascii=False, indent=2))
    return 3


def command_match(args: argparse.Namespace) -> int:
    source_hash = sha256(args.pdf)
    for case_dir, manifest in load_cases(args.skill_root):
        if manifest.get("files", {}).get("source.pdf", {}).get("sha256") == source_hash:
            verification = verify_case(case_dir, manifest)
            print(
                json.dumps(
                    {
                        "match_type": "EXACT_SHA256",
                        "case_id": manifest.get("case_id"),
                        "title": manifest.get("title"),
                        "verify_status": verification["status"],
                        "can_export_golden": verification["status"] == "PASS",
                        "disclosure": "已验收金标准复现，不代表本轮重新执行或实时取数",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0 if verification["status"] == "PASS" else 2
    print(
        json.dumps(
            {
                "match_type": "NONE",
                "source_sha256": source_hash,
                "can_export_golden": False,
                "action": "run normal pipeline; golden cases may be used only as templates",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 1


def command_export(args: argparse.Namespace) -> int:
    for case_dir, manifest in load_cases(args.skill_root):
        if manifest.get("case_id") != args.case_id:
            continue
        verification = verify_case(case_dir, manifest)
        if verification["status"] != "PASS":
            print(json.dumps(verification, ensure_ascii=False, indent=2))
            return 2
        args.output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(case_dir / "expected.xlsx", args.output)
        print(
            json.dumps(
                {
                    "status": "EXPORTED",
                    "case_id": args.case_id,
                    "output": str(args.output.resolve()),
                    "sha256": sha256(args.output),
                    "disclosure": "已验收金标准复现，不代表本轮重新执行或实时取数",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(json.dumps({"status": "NOT_FOUND", "case_id": args.case_id}, ensure_ascii=False, indent=2))
    return 3


def command_feedback_template(args: argparse.Namespace) -> int:
    case = next(
        ((case_dir, manifest) for case_dir, manifest in load_cases(args.skill_root) if manifest.get("case_id") == args.case_id),
        None,
    )
    if case is None:
        print(json.dumps({"status": "NOT_FOUND", "case_id": args.case_id}, ensure_ascii=False, indent=2))
        return 3
    _, manifest = case
    payload = {
        "schema_version": "1.0.0",
        "case_id": args.case_id,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_pdf_sha256": manifest["files"]["source.pdf"]["sha256"],
        "original_artifact": "",
        "corrected_artifact": "",
        "feedback_items": [
            {
                "object_id": "",
                "sheet": "",
                "range": "",
                "category": "",
                "observed": "",
                "expected": "",
                "evidence": "",
                "ai_correction": "",
                "scope": "CASE_SPECIFIC",
                "validation": "",
                "accepted": False,
            }
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"status": "CREATED", "output": str(args.output.resolve())}, ensure_ascii=False, indent=2))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--skill-root", type=Path, default=ROOT)
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("list").set_defaults(func=command_list)

    verify = commands.add_parser("verify")
    verify.add_argument("--case-id", required=True)
    verify.set_defaults(func=command_verify)

    match = commands.add_parser("match")
    match.add_argument("--pdf", required=True, type=Path)
    match.set_defaults(func=command_match)

    export = commands.add_parser("export")
    export.add_argument("--case-id", required=True)
    export.add_argument("--output", required=True, type=Path)
    export.set_defaults(func=command_export)

    feedback = commands.add_parser("feedback-template")
    feedback.add_argument("--case-id", required=True)
    feedback.add_argument("--output", required=True, type=Path)
    feedback.set_defaults(func=command_feedback_template)
    return result


def main() -> int:
    args = parser().parse_args()
    args.skill_root = args.skill_root.resolve()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
