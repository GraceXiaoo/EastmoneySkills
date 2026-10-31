#!/usr/bin/env python3
"""ETF一页纸6.0：分类规划、逐接口审计、公开溯源与交付脱敏。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ETF_TYPES = {
    "320001": "股票ETF",
    "320002": "债券ETF",
    "320003": "商品ETF",
    "320004": "跨境ETF",
    "320005": "货币ETF",
}

COMMON = ["核心投资逻辑", "基金概况", "规模、持有人结构与流动性分析", "业绩与运作特质"]
TAIL = ["同类型ETF比较", "投资价值与市场展望"]
CHAPTERS = {
    "股票ETF": COMMON + ["风险收益特征", "投资组合分析"] + TAIL,
    "债券ETF": COMMON + ["风险收益特征", "投资组合分析"] + TAIL,
    "商品ETF": COMMON + ["风险收益特征"] + TAIL,
    "跨境ETF": COMMON + ["风险收益特征", "投资组合分析"] + TAIL,
    "货币ETF": COMMON + TAIL,
}

MODULES = {
    "基金概况": [
        "RPT_F9_POFD_INFO", "RPT_F9_FM_BASICINFO",
        "RPT_FUND_F9_COMPANY", "RPT_FUND_F9_COMPHOLDER",
        "RPT_FUND_ORGMANGER_SCALE_TITLE", "RPT_F9_FUND_ORGPRODUCT",
        "RPT_INDEXPROFILE_BASIC", "RPT_INDEX_TRACKSCALE",
    ],
    "规模、持有人结构与流动性分析": [
        "RPT_F9_FUND_DALIYSCALE_SHARE", "RPT_FUND_SHARE_NAV",
        "RPT_FUND_HOLDER_STRUCTURE_REPORT", "RPT_CUSTOM_ETF_FUND_TURNOVER_DETAILS_ABOVE",
        "RPT_FUND_ETF_AMOUNTCHG", "RPT_ETF_ARINFO_SCALEDEL", "RPT_CUSTOM_ETF_ARINFO_SCALE",
    ],
    "业绩与运作特质": [
        "RPT_CUSTOM_FUND_DAILYNAV_DAILYFRE", "RPT_FUND_PERTREND_PERNAV",
        "RPT_FUND_DAILYNAV_YEARLY", "RPT_ETF_INDEXTRACKDEV",
        "RPT_ETF_RISK_ANNUTRACKERROR", "RPT_ETF_IPOV_PREMDISCRATEM",
    ],
    "风险收益特征": ["RPT_ETF_PAPER_RISKRATING"],
    "同类型ETF比较": ["RPT_CUSTOM_ETF_SP_SIMILARCOMPARE"],
}

PORTFOLIO = {
    "股票ETF": ["RPT_CUSTOM_ETF_ARSTOCK", "RPT_FUND_F9_KEYSTOCK", "RPT_FUND_HYFBDSF_DETAILS"],
    "债券ETF": ["RPT_CUSTOM_ETF_ARSTOCK", "RPT_FUND_F9_TOPTENBOND", "RPT_CUSTOM_FUND_F9_ALLOCATE_JOIN_FUND_F9_TLJJ", "RPT_ETF_FUND_DURATION"],
    "跨境ETF": ["RPT_CUSTOM_ETF_ARSTOCK", "RPT_FUND_F9_KEYSTOCKQDII", "RPT_POFD_F9_INDUSYYQDII", "RPT_POFD_PF_STOCKAREA"],
}

FAILURE_TEXT = "数据查询失败，本轮已停止。未改写查询、未更换标的，也未在后台继续执行。请稍后使用同一请求重新发起。"
MAX_CALLS_PER_QUERY = 2
TIMEOUT_SECONDS = 1200
BACKOFF_SECONDS = (30, 90)
CATALOG_PATH = Path(__file__).resolve().parent.parent / "references" / "interface_catalog.json"
DISCOVERY_BATCH_SIZE = 3
VERSION = "6.0"

FORBIDDEN_PUBLIC_KEYS = {
    "interface", "interface_name", "report_path", "report_code", "mql", "query",
    "script", "execution_id", "process_id", "error", "error_code", "reason",
    "org_code", "manager_code", "secu_inner_code", "security_inner_code",
}
FORBIDDEN_PUBLIC_PATTERNS = (
    r"RPT_[A-Z0-9_]+", r"ReportBlock\s*\(", r"SetCodes\s*\(",
    r"SetReportFilter\s*\(", r"REPORT_FIELD\s*\(", r"Choice报表[\\/]",
    r"(?:execution|process)[_-]?id", r"机构代码", r"基金经理代码", r"证券内码",
    r"通过\s*MQL", r"通过资讯搜索", r"接口返回", r"取数失败", r"元数据未发现",
    r"取数来源", r"数据来源",
)

INTERFACE_STATES = (
    "待发现", "元数据未发现", "入参缺失", "前置条件不满足", "待执行",
    "执行成功且有数据", "执行成功但为空", "执行失败",
)
EXECUTED_STATES = ("执行成功且有数据", "执行成功但为空", "执行失败")
EXEMPT_STATES = ("元数据未发现", "入参缺失", "前置条件不满足")
FORBIDDEN_SKIP_REASONS = ("其他接口已覆盖", "数据已够用", "数据已经够用", "节省调用", "报告可以完成")


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_audit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") not in ("5.0", VERSION) or not isinstance(payload.get("interfaces"), list):
        raise ValueError("不是有效的ETF一页纸执行审计文件。")
    return payload


def init_audit(condition_result: dict[str, Any]) -> dict[str, Any]:
    """由分类调用计划创建唯一接口矩阵；条件接口视为已经成功执行。"""
    plan = build_plan(condition_result)
    created = _now()
    rows = []
    for call in plan["calls"]:
        is_condition = call["interface"] == "RPT_ETF_FUND_SHEETPAPER"
        state = "执行成功且有数据" if is_condition else "待发现"
        rows.append({
            "order": call["order"],
            "interface": call["interface"],
            "chapter": call.get("chapter") or "条件接口",
            "state": state,
            "metadata_found": True if is_condition else False,
            "report_path": None,
            "inputs_ready": True if is_condition else None,
            "prerequisite_met": True if is_condition else None,
            "attempt_count": 1 if is_condition else 0,
            "row_count": 1 if is_condition else None,
            "execution_id": None,
            "error_code": None,
            "reason": "条件接口已先行执行并返回分类结果" if is_condition else None,
            "history": [{"at": created, "state": state, "reason": "初始化"}],
        })
    return {
        "version": VERSION,
        "etf_type_code": plan["etf_type_code"],
        "etf_type": plan["etf_type"],
        "created_at": created,
        "updated_at": created,
        "interfaces": rows,
    }


def _find_interface(audit: dict[str, Any], interface: str) -> dict[str, Any]:
    matches = [row for row in audit["interfaces"] if row.get("interface") == interface]
    if len(matches) != 1:
        raise ValueError(f"审计矩阵中接口 {interface} 必须有且只有一条记录。")
    return matches[0]


def update_audit(
    audit: dict[str, Any], interface: str, state: str, *, report_path: str | None = None,
    metadata_found: bool = False, inputs_ready: bool | None = None,
    prerequisite_met: bool | None = None, attempts: int = 0, row_count: int | None = None,
    execution_id: str | None = None, error_code: str | None = None, reason: str | None = None,
) -> dict[str, Any]:
    if state not in INTERFACE_STATES:
        raise ValueError(f"非法状态：{state}")
    if attempts < 0:
        raise ValueError("调用次数增量不得为负数。")
    if reason and any(word in reason for word in FORBIDDEN_SKIP_REASONS):
        raise ValueError("禁止以数据覆盖、数据已足够或节省调用作为跳过接口的理由。")
    row = _find_interface(audit, interface)
    old = row["state"]
    transitions = {
        "待发现": {"元数据未发现", "入参缺失", "前置条件不满足", "待执行"},
        "待执行": set(EXECUTED_STATES),
    }
    if old in EXECUTED_STATES or old in EXEMPT_STATES:
        raise ValueError(f"接口 {interface} 已处于终态 {old}，不得覆盖审计记录。")
    if state not in transitions.get(old, set()):
        raise ValueError(f"禁止状态转换：{old} -> {state}")

    if state == "待执行":
        if not (metadata_found or row.get("metadata_found")):
            raise ValueError("进入待执行前必须确认元数据。")
        if inputs_ready is not True or prerequisite_met is not True:
            raise ValueError("进入待执行前必须确认入参齐备且前置条件成立。")
        if not (report_path or row.get("report_path")):
            raise ValueError("进入待执行前必须记录完整报表路径。")
    if state == "元数据未发现" and (metadata_found or row.get("metadata_found")):
        raise ValueError("元数据已发现后不得改记为元数据未发现。")
    if state == "入参缺失" and not reason:
        raise ValueError("入参缺失必须写明缺少字段。")
    if state == "前置条件不满足" and not reason:
        raise ValueError("前置条件不满足必须写明具体条件。")
    if state in EXECUTED_STATES and attempts < 1:
        raise ValueError("执行终态必须记录至少一次实际调用。")
    if state == "执行成功且有数据" and (row_count is None or row_count < 1):
        raise ValueError("执行成功且有数据必须记录大于0的返回行数。")
    if state == "执行成功但为空" and row_count not in (None, 0):
        raise ValueError("执行成功但为空的返回行数必须为0。")
    if state == "执行失败" and not (error_code or reason):
        raise ValueError("执行失败必须记录错误类别或原因。")

    row.update({
        "state": state,
        "metadata_found": bool(metadata_found or row.get("metadata_found")),
        "report_path": report_path or row.get("report_path"),
        "inputs_ready": inputs_ready if inputs_ready is not None else row.get("inputs_ready"),
        "prerequisite_met": prerequisite_met if prerequisite_met is not None else row.get("prerequisite_met"),
        "attempt_count": int(row.get("attempt_count") or 0) + attempts,
        "row_count": row_count,
        "execution_id": execution_id,
        "error_code": error_code,
        "reason": reason,
    })
    changed = _now()
    row.setdefault("history", []).append({
        "at": changed, "from": old, "state": state, "attempts_added": attempts,
        "row_count": row_count, "execution_id": execution_id, "error_code": error_code,
        "reason": reason,
    })
    audit["updated_at"] = changed
    return audit


def audit_summary(audit: dict[str, Any]) -> dict[str, Any]:
    rows = audit["interfaces"]
    should_execute = [r for r in rows if r.get("metadata_found") is True and r.get("inputs_ready") is True and r.get("prerequisite_met") is True]
    actually_executed = [r for r in should_execute if r.get("state") in EXECUTED_STATES and int(r.get("attempt_count") or 0) > 0]
    pending = [r["interface"] for r in rows if r.get("state") in ("待发现", "待执行")]
    missing_attempt = [r["interface"] for r in should_execute if r not in actually_executed]
    total = len(should_execute)
    coverage = 100.0 if total == 0 else round(len(actually_executed) * 100 / total, 2)
    return {
        "计划接口数": len(rows),
        "元数据发现数": sum(bool(r.get("metadata_found")) for r in rows),
        "应执行接口数": total,
        "实际执行接口数": len(actually_executed),
        "执行覆盖率": coverage,
        "成功有数据数": sum(r.get("state") == "执行成功且有数据" for r in rows),
        "成功为空数": sum(r.get("state") == "执行成功但为空" for r in rows),
        "失败数": sum(r.get("state") == "执行失败" for r in rows),
        "未发现数": sum(r.get("state") == "元数据未发现" for r in rows),
        "入参缺失数": sum(r.get("state") == "入参缺失" for r in rows),
        "前置条件不满足数": sum(r.get("state") == "前置条件不满足" for r in rows),
        "待处理接口": pending,
        "应执行但未执行接口": missing_attempt,
    }


def validate_audit(audit: dict[str, Any], chapter: str | None = None) -> dict[str, Any]:
    selected = audit["interfaces"] if chapter is None else [r for r in audit["interfaces"] if r.get("chapter") == chapter]
    if chapter is not None and not selected:
        raise ValueError(f"审计矩阵中不存在章节：{chapter}")
    incomplete = [r["interface"] for r in selected if r.get("state") in ("待发现", "待执行")]
    unexecuted = [r["interface"] for r in selected if r.get("metadata_found") is True and r.get("inputs_ready") is True and r.get("prerequisite_met") is True and not (r.get("state") in EXECUTED_STATES and int(r.get("attempt_count") or 0) > 0)]
    if incomplete or unexecuted:
        scope = f"章节“{chapter}”" if chapter else "写作前总验收"
        raise ValueError(f"{scope}未通过；待处理={incomplete}；应执行但未执行={unexecuted}")
    summary = audit_summary(audit)
    if chapter is None and summary["执行覆盖率"] != 100.0:
        raise ValueError(f"写作前总验收未通过；执行覆盖率={summary['执行覆盖率']}%")
    return summary


def output_manifest(fund_code: str) -> dict[str, str]:
    """返回三种强制交付格式的统一文件名。"""
    code = fund_code.strip().upper()
    if not code:
        raise ValueError("基金代码不能为空。")
    stem = f"{code}-ETF一页纸"
    return {
        "html": f"{stem}.html",
        "docx": f"{stem}.docx",
        "pdf": f"{stem}.pdf",
    }


def build_plan(condition_result: dict[str, Any]) -> dict[str, Any]:
    code = str(condition_result.get("ETF_TYPE_ONE") or condition_result.get("投资范畴分类-一级代码") or "").strip()
    etf_type = ETF_TYPES.get(code)
    if not etf_type:
        raise ValueError("条件接口未返回可识别的ETF_TYPE_ONE，禁止依据名称猜测分类。")
    chapters = CHAPTERS[etf_type]
    calls: list[dict[str, Any]] = [{"order": 1, "interface": "RPT_ETF_FUND_SHEETPAPER", "required": True}]
    order = 2
    for chapter in chapters:
        names = list(MODULES.get(chapter, []))
        if chapter == "业绩与运作特质" and etf_type == "货币ETF":
            names = ["RPT_FUND_DAILYNAV_DAILYDER", "RPT_FUND_PERTREND_PERNAV", "RPT_FUND_DAILYNAV_YEARLY"]
        if chapter == "投资组合分析":
            names = PORTFOLIO.get(etf_type, [])
        for name in names:
            calls.append({"order": order, "interface": name, "chapter": chapter, "required": False})
            order += 1
    return {"etf_type_code": code, "etf_type": etf_type, "chapters": chapters, "calls": calls}


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, dict[str, Any]]:
    """加载由新版取数工具表生成的接口目录。"""
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {str(row["interface"]): row for row in rows}


def _compact_fields(fields: list[str], limit: int = 8) -> list[str]:
    cleaned = [re.sub(r"\s+", " ", str(x)).strip() for x in fields]
    return [x for x in cleaned if x][:limit]


def build_discovery_plan(condition_result: dict[str, Any]) -> dict[str, Any]:
    """按章节生成1至3个接口一批的定向MQL元数据发现计划。"""
    report_plan = build_plan(condition_result)
    catalog = load_catalog()
    batches: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    current_chapter = ""

    def flush() -> None:
        nonlocal pending
        if not pending:
            return
        batches.append({
            "batch": len(batches) + 1,
            "chapter": current_chapter,
            "interfaces": pending,
            "search_indicator_keys": [x["primary_query"] for x in pending],
            "fallback_policy": "仅对元数据未发现的单个接口进行一次定向补检；不得整批降级。",
        })
        pending = []

    for call in report_plan["calls"]:
        name = call["interface"]
        meta = catalog.get(name, {"interface": name})
        chapter = call.get("chapter") or "条件接口"
        if chapter != current_chapter or len(pending) >= DISCOVERY_BATCH_SIZE:
            flush()
            current_chapter = chapter
        fields = _compact_fields(meta.get("outputs", []))
        chinese_name = str(meta.get("chinese_name") or "").strip()
        path_hint = str(meta.get("path_hint") or "").strip()
        primary = " ".join(x for x in [name, chinese_name, path_hint, " ".join(fields)] if x)
        retry = " ".join(x for x in [chinese_name, chapter, "入参", " ".join(meta.get("input_names", [])), "返回字段", " ".join(fields)] if x)
        pending.append({
            "interface": name,
            "chinese_name": chinese_name,
            "path_hint": path_hint,
            "primary_query": primary,
            "directed_retry_query": retry,
            "inputs": meta.get("inputs", []),
            "expected_fields": meta.get("outputs", []),
            "state": "待发现",
        })
    flush()
    return {**report_plan, "interface_states": INTERFACE_STATES, "discovery_batches": batches}


def _query_key(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


def run_query(command: list[str], query: str, ledger_path: Path) -> str:
    """执行完全相同的query；仅对成功返回且明确标记retryable的结果重试。"""
    ledger: dict[str, int] = {}
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    key = _query_key(query)
    used = int(ledger.get(key, 0))
    remaining = MAX_CALLS_PER_QUERY - used
    if remaining <= 0:
        raise RuntimeError(FAILURE_TEXT)

    attempts_this_run = min(MAX_CALLS_PER_QUERY, remaining)
    last_error = ""
    for attempt in range(attempts_this_run):
        ledger[key] = int(ledger.get(key, 0)) + 1
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            completed = subprocess.run(
                command,
                input=query,
                text=True,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(FAILURE_TEXT) from None
        except KeyboardInterrupt:
            raise RuntimeError(FAILURE_TEXT) from None
        else:
            if completed.returncode != 0:
                raise RuntimeError(FAILURE_TEXT)
            output = completed.stdout
            try:
                parsed = json.loads(output)
            except json.JSONDecodeError:
                return output
            if not (isinstance(parsed, dict) and parsed.get("retryable") is True):
                return output
            last_error = str(parsed.get("error") or "retryable failure")

        if attempt + 1 < attempts_this_run:
            time.sleep(BACKOFF_SECONDS[0])

    raise RuntimeError(f"{FAILURE_TEXT}（{last_error}）")


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes", "是"):
        return True
    if normalized in ("false", "0", "no", "否"):
        return False
    raise argparse.ArgumentTypeError("布尔值必须为 true/false。")


def _walk_public(value: Any, location: str = "$") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_PUBLIC_KEYS:
                issues.append(f"{location}.{key} 使用了禁止公开的字段名")
            issues.extend(_walk_public(item, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_walk_public(item, f"{location}[{index}]"))
    elif isinstance(value, str):
        for pattern in FORBIDDEN_PUBLIC_PATTERNS:
            if re.search(pattern, value, flags=re.IGNORECASE):
                issues.append(f"{location} 含禁止公开的信息：{pattern}")
                break
    return issues


def validate_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != VERSION or not isinstance(payload.get("sources"), list):
        raise ValueError("公开溯源必须包含 version=6.0 和 sources 数组。")
    issues = _walk_public(payload)
    seen: set[str] = set()
    for index, source in enumerate(payload["sources"]):
        where = f"sources[{index}]"
        if not isinstance(source, dict):
            issues.append(f"{where} 必须为对象")
            continue
        source_id = str(source.get("source_id") or "")
        if not re.fullmatch(r"数据表-\d{3}", source_id):
            issues.append(f"{where}.source_id 必须形如 数据表-001")
        if source_id in seen:
            issues.append(f"{where}.source_id 重复")
        seen.add(source_id)
        columns = source.get("columns")
        rows = source.get("rows")
        used_in = source.get("used_in")
        if not str(source.get("title") or "").strip():
            issues.append(f"{where}.title 不能为空")
        if not isinstance(columns, list) or not columns or any(not str(x).strip() for x in columns):
            issues.append(f"{where}.columns 必须是非空列名数组")
        if not isinstance(rows, list):
            issues.append(f"{where}.rows 必须是二维数组")
        elif isinstance(columns, list):
            for row_index, row in enumerate(rows):
                if not isinstance(row, list) or len(row) != len(columns):
                    issues.append(f"{where}.rows[{row_index}] 列数与columns不一致")
        if not isinstance(used_in, list) or not used_in:
            issues.append(f"{where}.used_in 至少包含一个正文引用位置")
    if issues:
        raise ValueError("公开溯源验收失败：\n- " + "\n- ".join(issues))
    return {"检查结果": "通过", "公开数据表数": len(payload["sources"])}


def _extract_report_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".html", ".htm", ".txt"):
        return path.read_text(encoding="utf-8", errors="ignore")
    if suffix == ".docx":
        with zipfile.ZipFile(path) as archive:
            names = [name for name in archive.namelist() if name.startswith("word/") and name.endswith(".xml")]
            return "\n".join(archive.read(name).decode("utf-8", errors="ignore") for name in names)
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("检查PDF需要安装requirements.txt中的pypdf。") from exc
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_bytes().decode("utf-8", errors="ignore")


def scan_reports(paths: list[Path]) -> dict[str, Any]:
    issues: list[str] = []
    scanned: list[str] = []
    for path in paths:
        if not path.exists() or path.stat().st_size == 0:
            issues.append(f"文件不存在或为空：{path}")
            continue
        scanned.append(path.name)
        text = _extract_report_text(path)
        for pattern in FORBIDDEN_PUBLIC_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE):
                issues.append(f"{path.name} 含禁止公开的信息：{pattern}")
        suffix = path.suffix.lower()
        if suffix in (".html", ".htm"):
            if "data-source-id=" not in text or "查看原始数据" not in text:
                issues.append(f"{path.name} 缺少公开溯源触发器或data-source-id绑定")
            if not re.search(r"<(dialog|[^>]+role=[\"']dialog[\"'])", text, flags=re.IGNORECASE):
                issues.append(f"{path.name} 缺少点击后展示原始数据表的对话框")
        if suffix in (".docx", ".pdf") and not re.search(r"数据表-\d{3}", text):
            issues.append(f"{path.name} 缺少数据表编号或原始数据表附录")
    if issues:
        raise ValueError("交付脱敏检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果": "通过", "已检查文件": scanned}


def main() -> int:
    parser = argparse.ArgumentParser(description="ETF一页纸6.0辅助脚本")
    sub = parser.add_subparsers(dest="action", required=True)

    plan = sub.add_parser("plan", help="根据条件接口JSON生成分类与调用计划")
    plan.add_argument("condition_json", type=Path)

    run = sub.add_parser("run", help="按超时与累计次数上限执行外部查询命令")
    run.add_argument("--query", required=True)
    run.add_argument("--ledger", type=Path, required=True)
    run.add_argument("command", nargs=argparse.REMAINDER)

    outputs = sub.add_parser("outputs", help="输出HTML、Word和PDF的标准文件名")
    outputs.add_argument("fund_code")

    discovery = sub.add_parser("discovery-plan", help="生成按章节、小批量的MQL报表发现计划")
    discovery.add_argument("condition_json", type=Path)

    audit_init = sub.add_parser("audit-init", help="根据条件接口结果初始化逐接口执行矩阵")
    audit_init.add_argument("condition_json", type=Path)
    audit_init.add_argument("audit_json", type=Path)

    audit_update = sub.add_parser("audit-update", help="即时更新单个接口的审计状态")
    audit_update.add_argument("audit_json", type=Path)
    audit_update.add_argument("interface")
    audit_update.add_argument("--state", required=True, choices=INTERFACE_STATES)
    audit_update.add_argument("--metadata-found", action="store_true")
    audit_update.add_argument("--report-path")
    audit_update.add_argument("--inputs-ready", type=_parse_bool)
    audit_update.add_argument("--prerequisite-met", type=_parse_bool)
    audit_update.add_argument("--attempts", type=int, default=0)
    audit_update.add_argument("--row-count", type=int)
    audit_update.add_argument("--execution-id")
    audit_update.add_argument("--error-code")
    audit_update.add_argument("--reason")

    checkpoint = sub.add_parser("audit-checkpoint", help="检查指定章节全部接口是否进入合法终态")
    checkpoint.add_argument("audit_json", type=Path)
    checkpoint.add_argument("--chapter", required=True)

    finalize = sub.add_parser("audit-finalize", help="写作前验收接口执行覆盖率是否达到100%%")
    finalize.add_argument("audit_json", type=Path)

    provenance = sub.add_parser("provenance-validate", help="验收公开溯源JSON结构和脱敏规则")
    provenance.add_argument("provenance_json", type=Path)

    report_scan = sub.add_parser("report-scan", help="检查交付文件不含接口、脚本和失败诊断信息")
    report_scan.add_argument("files", nargs="+", type=Path)

    args = parser.parse_args()
    try:
        if args.action == "plan":
            payload = json.loads(args.condition_json.read_text(encoding="utf-8"))
            print(json.dumps(build_plan(payload), ensure_ascii=False, indent=2))
            return 0
        if args.action == "outputs":
            print(json.dumps(output_manifest(args.fund_code), ensure_ascii=False, indent=2))
            return 0
        if args.action == "discovery-plan":
            payload = json.loads(args.condition_json.read_text(encoding="utf-8"))
            print(json.dumps(build_discovery_plan(payload), ensure_ascii=False, indent=2))
            return 0
        if args.action == "audit-init":
            payload = json.loads(args.condition_json.read_text(encoding="utf-8"))
            audit = init_audit(payload)
            _write_json(args.audit_json, audit)
            print(json.dumps(audit_summary(audit), ensure_ascii=False, indent=2))
            return 0
        if args.action == "audit-update":
            audit = _load_audit(args.audit_json)
            update_audit(
                audit, args.interface, args.state, report_path=args.report_path,
                metadata_found=args.metadata_found, inputs_ready=args.inputs_ready,
                prerequisite_met=args.prerequisite_met, attempts=args.attempts,
                row_count=args.row_count, execution_id=args.execution_id,
                error_code=args.error_code, reason=args.reason,
            )
            _write_json(args.audit_json, audit)
            print(json.dumps(audit_summary(audit), ensure_ascii=False, indent=2))
            return 0
        if args.action == "audit-checkpoint":
            summary = validate_audit(_load_audit(args.audit_json), args.chapter)
            print(json.dumps({"检查结果": "通过", "章节": args.chapter, **summary}, ensure_ascii=False, indent=2))
            return 0
        if args.action == "audit-finalize":
            summary = validate_audit(_load_audit(args.audit_json))
            print(json.dumps({"检查结果": "通过", **summary}, ensure_ascii=False, indent=2))
            return 0
        if args.action == "provenance-validate":
            payload = json.loads(args.provenance_json.read_text(encoding="utf-8"))
            print(json.dumps(validate_provenance(payload), ensure_ascii=False, indent=2))
            return 0
        if args.action == "report-scan":
            print(json.dumps(scan_reports(args.files), ensure_ascii=False, indent=2))
            return 0
        if not args.command:
            raise ValueError("缺少外部查询命令。")
        sys.stdout.write(run_query(args.command, args.query, args.ledger))
        return 0
    except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
