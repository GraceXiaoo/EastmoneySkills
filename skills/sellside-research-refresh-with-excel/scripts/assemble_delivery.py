#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


HOST_SKILL = "sellside-research-refresh-with-excel20"
FALLBACK_HOST_VERSION = "3.0.4"
REQUIRED_STAGES = tuple(range(5))
STAGE4_GENERATOR_SCRIPT = "prepare_drafting_handoff.py finalize"
LEGAL_DELIVERY_STATES = {
    "COMPLETE",
    "COMPLETE_WITH_OMISSIONS",
    "COMPLETE_WITH_UNVERIFIED_LAYOUT",
}
UNVERIFIED_LAYOUT_LIMITATION = (
    "版式未渲染审计：无浏览器环境，渲染层版式检查未执行；"
    "版式规则按参考 PDF 实测落地但未经渲染确认。"
)
_DATE_PATTERN = re.compile(r"\d{4}[-/.年]\s*\d{1,2}[-/.月]\s*\d{1,2}")


def _skill_md_version() -> str:
    """从 SKILL.md frontmatter 读取版本号，缺失时退回常量。"""
    skill_md = Path(__file__).resolve().parents[1] / "SKILL.md"
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return FALLBACK_HOST_VERSION
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith("version:"):
            value = stripped.split(":", 1)[1].strip().strip("\"'")
            if value:
                return value
    return FALLBACK_HOST_VERSION


HOST_VERSION = _skill_md_version()


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


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def _verify_artifact(artifact: dict[str, Any]) -> Path:
    path = Path(str(artifact.get("path", "")))
    if not path.is_file():
        raise ValueError(f"artifact missing: {path}")
    if path.stat().st_size != artifact.get("size_bytes"):
        raise ValueError(f"artifact size mismatch: {path}")
    if _sha256(path) != artifact.get("sha256"):
        raise ValueError(f"artifact hash mismatch: {path}")
    return path


def _load_handoffs(
    handoff_paths: Iterable[Path],
) -> dict[int, tuple[Path, dict[str, Any]]]:
    handoffs: dict[int, tuple[Path, dict[str, Any]]] = {}
    for path in handoff_paths:
        handoff = _load_json(path)
        stage = handoff.get("stage")
        if not isinstance(stage, int) or stage not in REQUIRED_STAGES:
            raise ValueError(f"handoff stage must be 0 through 4: {path}")
        if stage in handoffs:
            raise ValueError(f"duplicate handoff stage: {stage}")
        handoffs[stage] = (path.resolve(), handoff)
    return handoffs


def assess_resume(
    handoff_paths: Iterable[Path],
    *,
    strict_chain: bool = True,
) -> dict[str, Any]:
    handoffs = _load_handoffs(handoff_paths)
    reusable: list[int] = []
    task_id: str | None = None
    previous_path: Path | None = None
    previous_hash: str | None = None

    for stage in REQUIRED_STAGES:
        item = handoffs.get(stage)
        if item is None:
            return {
                "status": "RESUME_REQUIRED",
                "first_stage": stage,
                "reason": f"stage-{stage} handoff is missing",
                "reusable_stages": reusable,
            }
        path, handoff = item
        if handoff.get("status") != "CONFIRMED":
            return {
                "status": "RESUME_REQUIRED",
                "first_stage": stage,
                "reason": (
                    f"stage-{stage} status is "
                    f"{handoff.get('status', 'missing')}"
                ),
                "reusable_stages": reusable,
            }
        current_task = handoff.get("task_id")
        if not isinstance(current_task, str) or not current_task:
            raise ValueError(f"stage-{stage} task_id is missing")
        if task_id is None:
            task_id = current_task
        elif strict_chain and current_task != task_id:
            return {
                "status": "RESUME_REQUIRED",
                "first_stage": stage,
                "reason": f"stage-{stage} task_id differs from stage-0",
                "reusable_stages": reusable,
            }
        validations = handoff.get("validation", [])
        if not isinstance(validations, list) or any(
            item.get("status") != "PASS" for item in validations
        ):
            return {
                "status": "RESUME_REQUIRED",
                "first_stage": stage,
                "reason": f"stage-{stage} validation is not fully PASS",
                "reusable_stages": reusable,
            }
        try:
            for artifact in [
                *handoff.get("inputs", []),
                *handoff.get("outputs", []),
            ]:
                _verify_artifact(artifact)
        except ValueError as exc:
            return {
                "status": "RESUME_REQUIRED",
                "first_stage": stage,
                "reason": str(exc),
                "reusable_stages": reusable,
            }
        if strict_chain and stage > 0:
            linked = [
                artifact
                for artifact in handoff.get("inputs", [])
                if Path(str(artifact.get("path", ""))).resolve() == previous_path
                and artifact.get("sha256") == previous_hash
            ]
            if len(linked) != 1:
                return {
                    "status": "RESUME_REQUIRED",
                    "first_stage": stage,
                    "reason": (
                        f"stage-{stage} does not bind the confirmed "
                        f"stage-{stage - 1} handoff"
                    ),
                    "reusable_stages": reusable,
                }
        reusable.append(stage)
        previous_path = path
        previous_hash = _sha256(path)

    return {
        "status": "READY",
        "first_stage": None,
        "reason": None,
        "reusable_stages": reusable,
        "task_id": task_id,
    }


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


def _declares_non_origin_report(markdown_text: str) -> bool:
    first_line = next(
        (line.strip() for line in markdown_text.splitlines() if line.strip()),
        "",
    )
    plain = first_line.replace("*", "").strip()
    return plain.startswith("非原机构正式报告") and bool(
        _DATE_PATTERN.search(first_line)
    )


def _check_stage4_provenance(
    stage4: dict[str, Any],
    *,
    markdown_path: Path,
    html_path: Path,
) -> tuple[list[str], str | None]:
    """校验 stage-4 交付物确由 drafting 引擎产出（P0 来源门禁）。

    返回 (failure_reasons, workflow_status)；workflow_status 在回执缺失
    时为 None。任一失败都会导致交付判定 FAIL（STAGE4_BYPASSED）。
    """
    failures: list[str] = []

    generator = stage4.get("generator")
    if not (
        isinstance(generator, dict)
        and generator.get("script") == STAGE4_GENERATOR_SCRIPT
    ):
        failures.append(
            "stage-4 handoff lacks generator "
            f"'{STAGE4_GENERATOR_SCRIPT}' (STAGE4_BYPASSED)"
        )

    receipt = stage4.get("engine_receipt")
    workflow_status: str | None = None
    if not isinstance(receipt, dict):
        failures.append(
            "stage-4 handoff lacks engine_receipt (STAGE4_BYPASSED)"
        )
    else:
        state_info = receipt.get("workflow_state")
        if isinstance(state_info, dict):
            state_path = Path(str(state_info.get("path", "")))
            state_hash = state_info.get("sha256")
            registered = [
                item
                for item in stage4.get("outputs", [])
                if Path(str(item.get("path", ""))) == state_path
                and item.get("sha256") == state_hash
            ]
            if len(registered) != 1:
                failures.append(
                    "workflow_state.json is not registered in stage-4 "
                    "outputs with matching sha256"
                )
            elif not state_path.is_file() or _sha256(state_path) != state_hash:
                failures.append(
                    f"workflow_state.json hash mismatch: {state_path}"
                )
            workflow_status = state_info.get("status")
            if workflow_status not in LEGAL_DELIVERY_STATES:
                failures.append(
                    "drafting workflow status is not a legal delivery "
                    f"state: {workflow_status!r}"
                )
        else:
            failures.append("engine_receipt.workflow_state is missing")

        markdown_digest = _sha256(markdown_path)
        if receipt.get("markdown_sha256") != markdown_digest:
            failures.append(
                "delivered markdown sha256 differs from "
                "engine_receipt.markdown_sha256"
            )
        if receipt.get("html_sha256") != _sha256(html_path):
            failures.append(
                "delivered HTML sha256 differs from "
                "engine_receipt.html_sha256"
            )

    markdown_text = markdown_path.read_text(encoding="utf-8")
    html_text = html_path.read_text(encoding="utf-8")
    meta_digest = _extract_source_md_meta(html_text)
    if meta_digest is None:
        failures.append("delivered HTML lacks source-md-sha256 meta")
    elif meta_digest != _sha256(markdown_path):
        failures.append(
            "delivered HTML source-md-sha256 meta does not match the "
            "markdown hash"
        )
    if not _declares_non_origin_report(markdown_text):
        failures.append(
            "delivered markdown must open with the non-origin disclaimer "
            "'非原机构正式报告' and a writing date"
        )
    if "[source:" in markdown_text:
        failures.append(
            "delivered markdown contains internal [source:N] markers"
        )
    if "](#reference-" in markdown_text:
        failures.append(
            "delivered markdown contains unresolved reference anchors"
        )
    return failures, workflow_status


def _single_output(
    handoff: dict[str, Any],
    *,
    suffix: str,
    label: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in handoff.get("outputs", [])
        if str(item.get("path", "")).lower().endswith(suffix.lower())
    ]
    if len(matches) != 1:
        raise ValueError(f"{label} requires exactly one {suffix} output")
    _verify_artifact(matches[0])
    return matches[0]


def _delivery_item(
    artifact: dict[str, Any],
    *,
    kind: str,
    source_stage: int,
) -> dict[str, Any]:
    return {
        "kind": kind,
        **artifact,
        "source_stage": source_stage,
        "acceptance_status": "PASS",
    }


def _delivery_rows(deliveries: list[dict[str, Any]]) -> list[str]:
    rows = ["| 交付物 | 来源阶段 | 验收 | 路径 |", "|---|---:|---|---|"]
    rows.extend(
        f"| {item['kind']} | {item['source_stage']} | "
        f"{item['acceptance_status']} | `{item['path']}` |"
        for item in deliveries
    )
    return rows


def _stage5_document(
    *,
    task_id: str,
    handoff_paths: list[Path],
    manifest_path: Path,
    list_path: Path,
    manifest: dict[str, Any],
    status: str,
    validation: list[dict[str, Any]],
    limitations: list[str],
    error: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "task_id": task_id,
        "stage": 5,
        "status": status,
        "producer": {
            "skill": HOST_SKILL,
            "version": HOST_VERSION,
            "mode": "评测与交付汇总",
        },
        "inputs": [
            _artifact(path, "application/json")
            for path in handoff_paths
        ],
        "outputs": [
            _artifact(manifest_path, "application/json"),
            _artifact(list_path, "text/markdown"),
        ],
        "started_at": manifest["generated_at"],
        "completed_at": _now(),
        "validation": validation,
        "limitations": limitations,
        "error": error,
        "resume": {
            "next_stage": None,
            "requires_user_confirmation": False,
            "input_hashes": {
                str(path): _sha256(path)
                for path in handoff_paths
            },
        },
    }


def assemble_delivery(
    handoff_paths: Iterable[Path],
    output_dir: Path,
    *,
    controlled_fixture: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    paths = [path.resolve() for path in handoff_paths]
    strict_chain = not controlled_fixture
    resume = assess_resume(paths, strict_chain=strict_chain)
    if resume["status"] != "READY":
        raise ValueError(
            f"stage-{resume['first_stage']} must resume: {resume['reason']}"
        )
    handoffs = _load_handoffs(paths)
    stage0 = handoffs[0][1]
    stage3 = handoffs[3][1]
    stage4 = handoffs[4][1]
    source_workbook = _single_output(
        stage0,
        suffix=".xlsx",
        label="source workbook",
    )
    source_review = _single_output(
        stage0,
        suffix=".md",
        label="source review report",
    )
    target_workbook = _single_output(
        stage3,
        suffix=".xlsx",
        label="target workbook",
    )
    target_report_md = _single_output(
        stage4,
        suffix=".md",
        label="target report markdown",
    )
    target_report_html = _single_output(
        stage4,
        suffix=".html",
        label="target report HTML",
    )
    deliveries = [
        _delivery_item(
            source_workbook,
            kind="source_workbook",
            source_stage=0,
        ),
        _delivery_item(
            source_review,
            kind="source_review_report",
            source_stage=0,
        ),
        _delivery_item(
            target_workbook,
            kind="target_workbook",
            source_stage=3,
        ),
        _delivery_item(
            target_report_md,
            kind="target_report_markdown",
            source_stage=4,
        ),
        _delivery_item(
            target_report_html,
            kind="target_report_html",
            source_stage=4,
        ),
    ]
    limitations = list(
        dict.fromkeys(
            limitation
            for stage in REQUIRED_STAGES
            for limitation in handoffs[stage][1].get("limitations", [])
        )
    )
    if controlled_fixture:
        limitations.append(
            "受控集成样例汇总了不同阶段的已确认夹具；"
            "不代表同一任务的一次真实端到端执行。"
        )
    provenance_failures, workflow_status = _check_stage4_provenance(
        stage4,
        markdown_path=Path(str(target_report_md["path"])),
        html_path=Path(str(target_report_html["path"])),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "delivery-manifest.json"
    list_path = output_dir / "final-delivery-list.md"
    stage5_path = output_dir / "stage-5-handoff.json"
    task_id = (
        "stage-f-controlled-fixture"
        if controlled_fixture
        else str(resume["task_id"])
    )
    stages_section = [
        {
            "stage": stage,
            "handoff": _artifact(
                handoffs[stage][0],
                "application/json",
            ),
            "status": "CONFIRMED",
            "reused": True,
        }
        for stage in REQUIRED_STAGES
    ]
    generated_at = _now()

    if provenance_failures:
        for item in deliveries:
            if item["kind"] in {
                "target_report_markdown",
                "target_report_html",
            }:
                item["acceptance_status"] = "FAIL"
        manifest = {
            "schema_version": 1,
            "task_id": task_id,
            "status": "FAIL",
            "mode": "controlled_fixture" if controlled_fixture else "strict",
            "generated_at": generated_at,
            "stages": stages_section,
            "deliveries": deliveries,
            "validation": [
                {
                    "name": "confirmed stage handoffs",
                    "status": "PASS",
                },
                {
                    "name": "artifact paths, hashes, and sizes",
                    "status": "PASS",
                },
                {
                    "name": "minimum delivery set",
                    "status": "PASS",
                    "required_kinds": [
                        item["kind"] for item in deliveries
                    ],
                },
                {
                    "name": "resume without rerunning confirmed stages",
                    "status": "PASS",
                    "reused_stages": resume["reusable_stages"],
                },
                {
                    "name": "stage-4 drafting provenance",
                    "status": "FAIL",
                    "reasons": provenance_failures,
                },
            ],
            "limitations": limitations,
            "failure_reasons": provenance_failures,
        }
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        rows = [
            "# 最终交付清单",
            "",
            "> **交付判定：FAIL（STAGE4_BYPASSED）** — "
            "机器门禁在 stage-4 来源校验中拒绝本次交付：",
            "",
        ]
        rows.extend(f"- {reason}" for reason in provenance_failures)
        rows.extend(["", "## 交付物", ""])
        rows.extend(_delivery_rows(deliveries))
        if limitations:
            rows.extend(["", "## 限制", ""])
            rows.extend(f"- {item}" for item in limitations)
        list_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        stage5 = _stage5_document(
            task_id=task_id,
            handoff_paths=paths,
            manifest_path=manifest_path,
            list_path=list_path,
            manifest=manifest,
            status="FAILED",
            validation=[
                {
                    "name": "stage-4 drafting provenance",
                    "status": "FAIL",
                    "reasons": provenance_failures,
                },
            ],
            limitations=limitations,
            error={
                "category": "STAGE4_BYPASSED",
                "reasons": provenance_failures,
            },
        )
        stage5_path.write_text(
            json.dumps(stage5, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return manifest, stage5

    if workflow_status == "COMPLETE_WITH_UNVERIFIED_LAYOUT":
        limitations.append(UNVERIFIED_LAYOUT_LIMITATION)
    manifest = {
        "schema_version": 1,
        "task_id": task_id,
        "status": "PASS",
        "mode": "controlled_fixture" if controlled_fixture else "strict",
        "generated_at": generated_at,
        "stages": stages_section,
        "deliveries": deliveries,
        "validation": [
            {
                "name": "confirmed stage handoffs",
                "status": "PASS",
            },
            {
                "name": "artifact paths, hashes, and sizes",
                "status": "PASS",
            },
            {
                "name": "minimum delivery set",
                "status": "PASS",
                "required_kinds": [item["kind"] for item in deliveries],
            },
            {
                "name": "resume without rerunning confirmed stages",
                "status": "PASS",
                "reused_stages": resume["reusable_stages"],
            },
            {
                "name": "stage-4 drafting provenance",
                "status": "PASS",
                "workflow_status": workflow_status,
            },
        ],
        "limitations": limitations,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rows = ["# 最终交付清单", ""]
    rows.extend(_delivery_rows(deliveries))
    if limitations:
        rows.extend(["", "## 限制", ""])
        rows.extend(f"- {item}" for item in limitations)
    list_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    stage5 = _stage5_document(
        task_id=task_id,
        handoff_paths=paths,
        manifest_path=manifest_path,
        list_path=list_path,
        manifest=manifest,
        status="CONFIRMED",
        validation=[
            {
                "name": "delivery manifest completeness",
                "status": "PASS",
                "receipt_path": str(manifest_path.resolve()),
            },
            {
                "name": "minimum delivery set",
                "status": "PASS",
                "receipt_path": str(list_path.resolve()),
            },
        ],
        limitations=limitations,
        error=None,
    )
    stage5_path.write_text(
        json.dumps(stage5, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest, stage5


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "handoffs",
        type=Path,
        nargs=5,
        metavar="HANDOFF",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--controlled-fixture", action="store_true")
    args = parser.parse_args()
    manifest, stage5 = assemble_delivery(
        args.handoffs,
        args.output_dir,
        controlled_fixture=args.controlled_fixture,
    )
    print(
        json.dumps(
            {
                "delivery_status": manifest["status"],
                "stage5_status": stage5["status"],
                "deliveries": len(manifest["deliveries"]),
                "failure_reasons": manifest.get("failure_reasons", []),
            },
            ensure_ascii=False,
        )
    )
    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
