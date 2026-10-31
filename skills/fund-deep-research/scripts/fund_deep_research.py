from __future__ import annotations
import argparse, hashlib, json, re, subprocess, time, zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ROUTES = ROOT / "references" / "classification_routes.json"
TEMPLATES = ROOT / "references" / "mql_templates.json"
FINAL = {"执行成功且有数据", "执行成功但为空", "执行失败", "元数据未发现", "入参缺失", "前置条件不满足"}
FAILURE_TEXT = "数据查询失败，本轮已停止。未改写查询、未更换标的，也未在后台继续执行。请稍后使用同一请求重新发起。"
MAX_CALLS_PER_QUERY = 2
TIMEOUT_SECONDS = 1200
RETRY_DELAY_SECONDS = 30
COMPATIBLE_BACKOFF_SECONDS = 90
PROVENANCE_VERSION = "1.0"
FORBIDDEN_PUBLIC_KEYS = {
    "interface", "interface_name", "report_path", "report_code", "mql", "query",
    "script", "execution_id", "process_id", "error", "error_code", "reason",
    "org_code", "manager_code", "secu_inner_code", "security_inner_code",
}
FORBIDDEN_PUBLIC_PATTERNS = (
    r"RPT_[A-Z0-9_]+", r"ReportBlock\s*\(", r"SetCodes\s*\(",
    r"SetReportFilter\s*\(", r"REPORT_FIELD\s*\(", r"Choice报表[\\/]",
    r"\bmcp[-_]mql[-_][a-z0-9_-]+\b", r"\b(?:Get|Search|Execute)_[A-Z][A-Za-z0-9_]*\b",
    r"\brequire[A-Za-z0-9_]*CompatibilityVersion\b", r"Runtime\s*(?:版本|version)\s*[:：]?\s*\d",
    r"(?:execution|process)[_-]?id", r"机构代码", r"基金经理代码", r"证券内码",
    r"通过\s*MQL", r"接口返回", r"取数失败", r"元数据未发现",
)

def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))

def yes(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "是", "y"}

def route(condition: dict[str, Any]) -> dict[str, Any]:
    if yes(condition.get("IFETF") or condition.get("是否ETF基金")):
        raise ValueError("检测到ETF标的，请改用平台当前可用的ETF一页纸研究Skill（以平台注册名称为准）。")
    kind = str(condition.get("PAPER_FUND_TYPE") or condition.get("一页纸专用分类") or "").strip()
    cfg = load(ROUTES)
    if kind == "ETF":
        raise ValueError("检测到ETF标的，请改用平台当前可用的ETF一页纸研究Skill（以平台注册名称为准）。")
    if kind not in cfg["fund_types"]:
        raise ValueError("条件接口未返回合法的一页纸专用分类。")
    chapters, calls = cfg["chapters"][kind], ["RPT_ETF_FUND_SHEETPAPER"]
    for chapter in chapters:
        calls += cfg["chapter_interfaces"].get(chapter, [])
        if chapter == "投资组合分析":
            portfolio = kind
            if kind == "指数型":
                portfolio = "QDII-非指数" if yes(condition.get("IS_QDII") or condition.get("是否QDII基金")) else "股债混-非指数"
            calls += cfg["portfolio_interfaces"].get(portfolio, [])
    if kind == "指数型": calls += cfg["conditional_interfaces"]["一页纸专用分类=指数型"]
    if yes(condition.get("IS_LJJJ") or condition.get("是否ETF联接基金")): calls += cfg["conditional_interfaces"]["是否ETF联接基金=是"]
    if yes(condition.get("IS_FQS") or condition.get("是否发起式基金")): calls += cfg["conditional_interfaces"]["是否发起式基金=是"]
    return {"fund_type": kind, "chapters": chapters, "interfaces": list(dict.fromkeys(calls))}

def render(interface: str, variables: dict[str, Any]) -> str:
    item = next((x for x in load(TEMPLATES)["templates"] if x["interface"] == interface), None)
    if not item: raise ValueError(f"模板不存在：{interface}")
    text, missing = item["mql"], []
    for name in sorted(set(re.findall(r"\{\{([A-Z0-9_]+)\}\}", text))):
        if variables.get(name) in (None, ""): missing.append(name)
        else: text = text.replace("{{" + name + "}}", str(variables[name]))
    if missing: raise ValueError("缺少模板变量：" + ", ".join(missing))
    if text.count("ReportBlock(") != 1: raise ValueError("单接口模板必须且只能包含一个ReportBlock。")
    return text

def render_plan(condition: dict[str, Any], variables: dict[str, Any]) -> list[dict[str, Any]]:
    result = route(condition)
    queue = []
    for interface in result["interfaces"]:
        try:
            mql = render(interface, variables)
            queue.append({"interface": interface, "state": "待执行", "mql": mql})
        except ValueError as exc:
            queue.append({"interface": interface, "state": "入参缺失", "reason": str(exc)})
    return queue

def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    invalid = [x for x in rows if x.get("state") not in FINAL]
    if invalid: raise ValueError("存在未完成状态")
    required = [x for x in rows if x.get("should_execute", True)]
    attempted = [x for x in required if int(x.get("attempt_count") or 0) > 0]
    return {"计划接口数": len(rows), "应执行接口数": len(required), "实际执行接口数": len(attempted),
            "执行覆盖率": 100.0 if not required else round(len(attempted)*100/len(required), 2),
            "成功有数据数": sum(x.get("state")=="执行成功且有数据" for x in rows),
            "成功为空数": sum(x.get("state")=="执行成功但为空" for x in rows),
            "失败数": sum(x.get("state")=="执行失败" for x in rows),
            "未发现数": sum(x.get("state")=="元数据未发现" for x in rows),
            "入参缺失数": sum(x.get("state")=="入参缺失" for x in rows),
            "前置条件不满足数": sum(x.get("state")=="前置条件不满足" for x in rows),
            "失败接口": [x.get("interface") for x in rows if x.get("state")=="执行失败"]}

def query_key(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query).strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

def run_query(command: list[str], query: str, ledger_path: Path) -> str:
    ledger = load(ledger_path) if ledger_path.exists() else {}
    key = query_key(query)
    if int(ledger.get(key, 0)) >= MAX_CALLS_PER_QUERY:
        raise RuntimeError(FAILURE_TEXT)
    last_error = ""
    while int(ledger.get(key, 0)) < MAX_CALLS_PER_QUERY:
        ledger[key] = int(ledger.get(key, 0)) + 1
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            completed = subprocess.run(command, input=query, text=True, capture_output=True,
                                       timeout=TIMEOUT_SECONDS, check=False)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            raise RuntimeError(FAILURE_TEXT) from None
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
        if int(ledger[key]) < MAX_CALLS_PER_QUERY:
            time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"{FAILURE_TEXT}（{last_error}）")

def walk_public(value: Any, location: str = "$") -> list[str]:
    issues = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_PUBLIC_KEYS:
                issues.append(f"{location}.{key} 使用了禁止公开的字段名")
            issues += walk_public(item, f"{location}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value): issues += walk_public(item, f"{location}[{index}]")
    elif isinstance(value, str):
        for pattern in FORBIDDEN_PUBLIC_PATTERNS:
            if re.search(pattern, value, flags=re.IGNORECASE):
                issues.append(f"{location} 含禁止公开的信息：{pattern}"); break
    return issues

def validate_provenance(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != PROVENANCE_VERSION or not isinstance(payload.get("sources"), list):
        raise ValueError("公开溯源必须包含 version=1.0 和 sources 数组。")
    issues, seen = walk_public(payload), set()
    for index, source in enumerate(payload["sources"]):
        where = f"sources[{index}]"
        if not isinstance(source, dict): issues.append(f"{where} 必须为对象"); continue
        sid = str(source.get("source_id") or "")
        if not re.fullmatch(r"数据表-\d{3}", sid): issues.append(f"{where}.source_id 必须形如 数据表-001")
        if sid in seen: issues.append(f"{where}.source_id 重复")
        seen.add(sid)
        columns, rows, used_in = source.get("columns"), source.get("rows"), source.get("used_in")
        if not str(source.get("title") or "").strip(): issues.append(f"{where}.title 不能为空")
        if not str(source.get("as_of") or "").strip(): issues.append(f"{where}.as_of 不能为空")
        if not isinstance(columns, list) or not columns or any(not str(x).strip() for x in columns): issues.append(f"{where}.columns 必须是非空中文列名数组")
        if not isinstance(rows, list): issues.append(f"{where}.rows 必须是二维数组")
        elif isinstance(columns, list):
            for row_index, row in enumerate(rows):
                if not isinstance(row, list) or len(row) != len(columns): issues.append(f"{where}.rows[{row_index}] 列数与columns不一致")
        if not isinstance(used_in, list) or not used_in: issues.append(f"{where}.used_in 至少包含一个正文引用位置")
    if issues: raise ValueError("公开溯源验收失败：\n- " + "\n- ".join(issues))
    return {"检查结果": "通过", "公开数据表数": len(payload["sources"])}

def extract_report_text(path: Path) -> str:
    if path.suffix.lower() in {".html", ".htm", ".txt"}: return path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            return "\n".join(archive.read(n).decode("utf-8", errors="ignore") for n in archive.namelist() if n.startswith("word/") and n.endswith(".xml"))
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("检查PDF需要可用的pypdf运行环境。") from exc
        return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    return path.read_bytes().decode("utf-8", errors="ignore")

def scan_reports(paths: list[Path]) -> dict[str, Any]:
    issues, scanned = [], []
    for path in paths:
        if not path.exists() or path.stat().st_size == 0: issues.append(f"文件不存在或为空：{path}"); continue
        scanned.append(path.name); content = extract_report_text(path)
        for pattern in FORBIDDEN_PUBLIC_PATTERNS:
            if re.search(pattern, content, flags=re.IGNORECASE): issues.append(f"{path.name} 含禁止公开的信息：{pattern}")
        if path.suffix.lower() in {".html", ".htm"}:
            if "data-source-id=" not in content or "查看原始数据" not in content: issues.append(f"{path.name} 缺少溯源触发器或data-source-id绑定")
            if not re.search(r"<(dialog|[^>]+role=[\"']dialog[\"'])", content, flags=re.I): issues.append(f"{path.name} 缺少可关闭的原始数据对话框")
    if issues: raise ValueError("交付检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果": "通过", "已检查文件": scanned}

def validate_analysis(payload: dict[str, Any]) -> dict[str, Any]:
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        raise ValueError("深度检查失败：缺少sections。")
    issues, checked = [], 0
    required = ("facts", "time_changes", "relative_positions", "drivers", "risks", "watch_items", "data_limits")
    for index, section in enumerate(sections):
        card = section.get("fact_card") if isinstance(section, dict) else None
        title = str(section.get("title") or f"sections[{index}]") if isinstance(section, dict) else f"sections[{index}]"
        if not isinstance(card, dict): issues.append(f"{title} 缺少fact_card"); continue
        checked += 1
        for key in required:
            if not isinstance(card.get(key), list): issues.append(f"{title}.{key} 必须为数组")
        facts = card.get("facts") if isinstance(card.get("facts"), list) else []
        evidence = sum(bool(str(x).strip()) for x in facts)
        if evidence < 2: issues.append(f"{title} 核心事实少于2项")
        layers = sum(bool(card.get(k)) for k in ("time_changes", "relative_positions", "drivers", "risks", "watch_items"))
        if layers < 2: issues.append(f"{title} 未达到事实之外至少2层分析")
    if issues: raise ValueError("深度检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果": "通过", "已检查章节": checked}

def validate_content_model(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("version") != "1.0" or not isinstance(payload.get("sections"), list):
        raise ValueError("内容模型必须包含version=1.0和sections数组。")
    issues, section_ids, subsection_ids, block_ids, charts = [], set(), set(), set(), 0
    expected_section = 1
    def check_blocks(blocks: Any, where: str) -> None:
        nonlocal charts
        if not isinstance(blocks, list): issues.append(f"{where}.blocks必须为数组"); return
        for bi, block in enumerate(blocks):
            bwhere=f"{where}.blocks[{bi}]"; bid=str(block.get("block_id") or "")
            if not bid or bid in block_ids: issues.append(f"{bwhere}.block_id缺失或重复")
            block_ids.add(bid)
            if block.get("type") not in {"paragraph","chart","table","metric_cards","risk_note"}: issues.append(f"{bwhere}.type不合法")
            source_ids=block.get("source_ids")
            if not isinstance(source_ids,list) or not source_ids: issues.append(f"{bwhere}.source_ids不能为空")
            if block.get("type")=="chart":
                charts += 1; chart=block.get("chart")
                if not isinstance(chart,dict): issues.append(f"{bwhere}.chart不能为空"); continue
                for key in ("chart_id","question","type","unit","as_of","extreme_value_policy","label_policy","caption"):
                    if not str(chart.get(key) or "").strip(): issues.append(f"{bwhere}.chart.{key}不能为空")
                if not isinstance(chart.get("width"),(int,float)) or chart.get("width",0)<=0: issues.append(f"{bwhere}.chart.width必须大于0")
                if not isinstance(chart.get("height"),(int,float)) or chart.get("height",0)<=0: issues.append(f"{bwhere}.chart.height必须大于0")
    for si, section in enumerate(payload["sections"]):
        where = f"sections[{si}]"
        sid = str(section.get("section_id") or "")
        if not sid or sid in section_ids: issues.append(f"{where}.section_id缺失或重复")
        section_ids.add(sid)
        title=str(section.get("title") or "").strip()
        if not title: issues.append(f"{where}.title不能为空")
        if re.match(r"^\d+(?:\.\d+)*\s*",title): issues.append(f"{where}.title不得重复写入编号")
        number=str(section.get("number") or "")
        if number != str(expected_section): issues.append(f"{where}.number应为{expected_section}，实际为{number or '空'}")
        expected_section += 1
        check_blocks(section.get("blocks",[]),where)
        subsections=section.get("subsections",[])
        if not isinstance(subsections,list): issues.append(f"{where}.subsections必须为数组"); continue
        for ui,sub in enumerate(subsections,1):
            uwhere=f"{where}.subsections[{ui-1}]"; uid=str(sub.get("subsection_id") or "")
            if not uid or uid in subsection_ids: issues.append(f"{uwhere}.subsection_id缺失或重复")
            subsection_ids.add(uid)
            expected_number=f"{number}.{ui}"
            if str(sub.get("number") or "") != expected_number: issues.append(f"{uwhere}.number应为{expected_number}")
            subtitle=str(sub.get("title") or "").strip()
            if not subtitle: issues.append(f"{uwhere}.title不能为空")
            if re.match(r"^\d+(?:\.\d+)*\s*",subtitle): issues.append(f"{uwhere}.title不得重复写入编号")
            check_blocks(sub.get("blocks",[]),uwhere)
    if issues: raise ValueError("内容模型检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果":"通过","章节数":len(payload["sections"]),"内容块数":len(block_ids),"图表数":charts}

def validate_heading_numbers(model: dict[str, Any], paths: list[Path]) -> dict[str, Any]:
    expected=[]
    for section in model.get("sections",[]):
        expected.append(f"{section.get('number')} {section.get('title')}")
        for sub in section.get("subsections",[]) or []:
            expected.append(f"{sub.get('number')} {sub.get('title')}")
    issues=[]
    for path in paths:
        content=extract_report_text(path)
        normalized=re.sub(r"\s+"," ",content)
        for heading in expected:
            if re.sub(r"\s+"," ",heading).strip() not in normalized:
                issues.append(f"{path.name}缺少编号标题：{heading}")
    if issues: raise ValueError("章节编号检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果":"通过","标题数":len(expected),"已检查文件":[x.name for x in paths]}

def validate_layout(image_dir: Path, min_coverage: float = 0.18) -> dict[str, Any]:
    try:
        from PIL import Image, ImageChops
    except ImportError as exc:
        raise ValueError("版式检查需要Pillow运行环境。") from exc
    pages=sorted([*image_dir.glob("*.png"),*image_dir.glob("*.jpg"),*image_dir.glob("*.jpeg")])
    if not pages: raise ValueError("版式检查失败：目录中没有渲染页面图片。")
    issues, warnings, details = [], [], []
    for page in pages:
        im=Image.open(page).convert("RGB"); bg=Image.new("RGB",im.size,"white"); diff=ImageChops.difference(im,bg).convert("L")
        mask=diff.point(lambda p: 255 if p>18 else 0); bbox=mask.getbbox()
        if not bbox: issues.append(f"{page.name}为空白页"); continue
        coverage=(bbox[2]-bbox[0])*(bbox[3]-bbox[1])/(im.width*im.height)
        edge=min(bbox[0],bbox[1],im.width-bbox[2],im.height-bbox[3])
        if coverage < min_coverage: warnings.append(f"{page.name}内容覆盖率{coverage:.1%}，需人工确认大面积空白")
        if edge < 3: issues.append(f"{page.name}内容贴近或超出页面边界")
        details.append({"page":page.name,"coverage":round(coverage,4),"edge_px":edge})
    if issues: raise ValueError("版式检查失败：\n- " + "\n- ".join(issues))
    return {"检查结果":"通过","页面数":len(pages),"人工复核警告":warnings,"页面摘要":details}

def main() -> int:
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest="action",required=True)
    a=s.add_parser("route"); a.add_argument("condition",type=Path)
    a=s.add_parser("render"); a.add_argument("interface"); a.add_argument("variables",type=Path)
    a=s.add_parser("render-plan"); a.add_argument("condition",type=Path); a.add_argument("variables",type=Path); a.add_argument("output",type=Path)
    a=s.add_parser("audit-summary"); a.add_argument("records",type=Path)
    a=s.add_parser("run"); a.add_argument("--query",required=True); a.add_argument("--ledger",type=Path,required=True); a.add_argument("command",nargs=argparse.REMAINDER)
    a=s.add_parser("provenance-validate"); a.add_argument("provenance",type=Path)
    a=s.add_parser("report-scan"); a.add_argument("files",nargs="+",type=Path)
    a=s.add_parser("analysis-validate"); a.add_argument("content_model",type=Path)
    a=s.add_parser("content-model-validate"); a.add_argument("content_model",type=Path)
    a=s.add_parser("layout-validate"); a.add_argument("image_dir",type=Path); a.add_argument("--min-coverage",type=float,default=0.18)
    a=s.add_parser("heading-number-validate"); a.add_argument("content_model",type=Path); a.add_argument("files",nargs="+",type=Path)
    args=p.parse_args()
    try:
        if args.action=="route": result=route(load(args.condition))
        elif args.action=="render": print(render(args.interface,load(args.variables))); return 0
        elif args.action=="render-plan":
            result=render_plan(load(args.condition),load(args.variables)); args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({"output":str(args.output),"count":len(result)},ensure_ascii=False)); return 0
        elif args.action=="audit-summary": result=summary(load(args.records))
        elif args.action=="run":
            if not args.command: raise ValueError("缺少外部查询命令。")
            print(run_query(args.command,args.query,args.ledger),end=""); return 0
        elif args.action=="provenance-validate": result=validate_provenance(load(args.provenance))
        elif args.action=="report-scan": result=scan_reports(args.files)
        elif args.action=="analysis-validate": result=validate_analysis(load(args.content_model))
        elif args.action=="content-model-validate": result=validate_content_model(load(args.content_model))
        elif args.action=="layout-validate": result=validate_layout(args.image_dir,args.min_coverage)
        else: result=validate_heading_numbers(load(args.content_model),args.files)
        print(json.dumps(result,ensure_ascii=False,indent=2)); return 0
    except (ValueError,RuntimeError,json.JSONDecodeError) as exc:
        print(str(exc)); return 2

if __name__ == "__main__": raise SystemExit(main())
