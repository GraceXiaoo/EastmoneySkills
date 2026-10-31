
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from auth import (  # noqa: E402
    AUTH_ERROR,
    AUTH_NEED_USER,
    AUTH_OK,
    clear_em_api_key_file,
    ensure_auth,
    load_em_api_key,
    mark_api_key_revoked,
)
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()
if not EM_API_KEY:
    EM_API_KEY = load_em_api_key()

BASE_URL = "https://ai-saas.eastmoney.com"
SEARCH_URL = "{0}/proxy/b/self-select/search-code".format(BASE_URL)
ADD_URL = "{0}/proxy/b/self-select/add-self-select".format(BASE_URL)
DELETE_URL = "{0}/proxy/b/self-select/delete-self-select".format(BASE_URL)
ENTITY_URL = "{0}/proxy/entity/saas".format(BASE_URL)

TIMEOUT_SECONDS = 60
PAGE_SIZE = 200
DEFAULT_OUTPUT_DIR = Path.cwd() / "miaoxiang" / "self_select"

MSG_EMPTY_EASTMONEY = "您的东方财富app自选列表暂无证券，通过对话直接添加吧"
MSG_EMPTY_CHOICE = "您的choice自选列表暂无证券，通过对话直接添加吧"
MSG_ADD_EASTMONEY_UNSUPPORTED = "暂时不支持新增东财app自选股"
MSG_DELETE_EASTMONEY_UNSUPPORTED = "暂时不支持删除东财app自选股"
MSG_ADD_TYPE_UNSUPPORTED = "该实体类型暂不支持加自选"
MSG_DELETE_TYPE_UNSUPPORTED = "该实体类型暂不支持删除自选"
MSG_LIMIT_REACHED = "【我的自选】数量已达到10000上限"
MSG_ADD_SUCCESS = "已成功添加到 choice--我的自选分类下"
MSG_DELETE_SUCCESS = "已成功删除 choice--我的自选 分类下对应证券"
MSG_ALREADY_IN_WATCHLIST = "已在自选"
MSG_NOT_IN_WATCHLIST = "自选股不存在"
MSG_REBIND = "未获取到用户信息，请重新绑定通行证"
NOTE_EASTMONEY = "数据来源于东方财富，当前仅支持查询东财app的沪深京自选股"
NOTE_CHOICE = "数据来源于choice，查询仅支持【我的自选】分类下的A股（加减自选支持A/港/美）"

# 未绑定通行证的典型返回：code=401, message="未获取到用户 ct/ut，请先绑定通行证"
# 鉴权判断：优先 code/status=401|403；文案只认明确的通行证/ct-ut 相关句，不用「未登录」等泛词
_REBIND_HINT_RE = re.compile(
    r"(未获取到用户|绑定通行证|ct\s*/\s*ut|请先绑定)",
    re.IGNORECASE,
)
# 加减接口业务失败文案：用户信息校验未过，需重新扫码绑定（不等于 HTTP 401）
_USER_VERIFY_FAIL_RE = re.compile(r"验证用户信息", re.IGNORECASE)
_LIMIT_HINT_RE = re.compile(r"(上限|10000|已满|超限)", re.IGNORECASE)
_DUPLICATE_ADD_HINT_RE = re.compile(r"(重复添加|已存在|已在自选)", re.IGNORECASE)
_DELETE_MISSING_HINT_RE = re.compile(r"(成分不存在|自选股不存在)", re.IGNORECASE)
_CHOICE_CODE_RE = re.compile(r"^[0-9A-Za-z]+\.[A-Za-z]+$")
# 实体识别只取 A/港/美股票，避免板块、指数、基金等混入
ENTITY_TYPE_CODES = "002001,002002,002003,002004"
_AUTH_CODES = {401, 403, "401", "403"}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _extract_error_message(body: str) -> str:
    body = (body or "").strip()
    if not body:
        return ""
    try:
        data = json.loads(body)
    except Exception:
        return body[:200]
    if isinstance(data, dict):
        for key in ("msg", "message", "error", "stack"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return body[:200]


def _http_post(url: str, payload: Dict[str, Any]) -> Any:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "em_api_key": EM_API_KEY or load_em_api_key(),
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            http_code = getattr(resp, "status", None) or resp.getcode()
    except urllib_error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if exc.code in (401, 403):
            raise AuthError("HTTP {0}".format(exc.code))
        try:
            parsed = json.loads(err_body) if err_body else {}
        except Exception:
            message = _extract_error_message(err_body) or "http status {0}".format(exc.code)
            raise RuntimeError("请求失败：{0}".format(message))
        if isinstance(parsed, dict):
            _raise_if_auth_failure(parsed, http_fallback=exc.code)
            return parsed
        raise RuntimeError("请求失败：http status {0}".format(exc.code))
    except urllib_error.URLError as exc:
        raise RuntimeError("请求失败：{0}".format(exc.reason))

    raw_body = (raw_body or "").strip()
    if not raw_body:
        raise RuntimeError("接口返回为空。")
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        if _REBIND_HINT_RE.search(raw_body):
            raise AuthError(raw_body[:200])
        return raw_body

    if isinstance(parsed, dict):
        _raise_if_auth_failure(parsed, http_fallback=http_code)
    return parsed


class AuthError(RuntimeError):
    """User is not a bound Miaoxiang user / passport binding missing."""


def _extract_payload_message(payload: Dict[str, Any]) -> str:
    for key in ("message", "msg", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("message", "msg"):
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _is_auth_status_code(code: Any, status: Any, http_fallback: Any = None) -> bool:
    """仅认明确的 401/403；status=-1 等业务码不算鉴权失败。"""
    if http_fallback in (401, 403):
        return True
    if code in _AUTH_CODES:
        return True
    if status in _AUTH_CODES:
        return True
    return False


def _raise_if_auth_failure(payload: Dict[str, Any], http_fallback: Any = None) -> None:
    """
    鉴权失败判定：
      1. 文案明确是未绑定通行证（如「未获取到用户 ct/ut，请先绑定通行证」）
      2. code/status/HTTP 为 401/403
    由上层转成授权链接，请用户打开链接扫码绑定，不再只回注册文案。
    """
    message = _extract_payload_message(payload)
    if message and _REBIND_HINT_RE.search(message):
        raise AuthError(message)

    if _is_auth_status_code(
        payload.get("code"),
        payload.get("status"),
        http_fallback=http_fallback,
    ):
        raise AuthError(message or "HTTP/业务鉴权失败")


def _apply_need_auth(result: Dict[str, Any], auth: Dict[str, Any], message: str) -> Dict[str, Any]:
    result.pop("remember_api_key", None)
    result.pop("api_key", None)
    result["need_auth"] = True
    result["authUrl"] = auth.get("auth_url")
    result["apiKeyUrl"] = auth.get("api_key_url") or AUTH_API_KEY_URL_FALLBACK
    result["auth_message"] = message
    result["content"] = message
    return result


def _mutate_items_need_reauth(items: List[Dict[str, Any]]) -> bool:
    """
    加减结果是否应走重新授权：全部失败且原因均为「验证用户信息失败」。
    查询可能仍可用，但写接口校验更严，需让用户重新扫码。
    """
    if not items:
        return False
    saw_verify_fail = False
    for entry in items:
        state = entry.get("state")
        message = _flatten(entry.get("message"))
        if state == 0 or message in _SUCCESS_MESSAGES:
            return False
        if message and _USER_VERIFY_FAIL_RE.search(message):
            saw_verify_fail = True
        else:
            return False
    return saw_verify_fail


def _handle_auth_revoked(reason: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Key 失效或未绑定通行证：忽略本地/环境变量中的旧 Key，直接生成扫码授权链接。"""
    global EM_API_KEY
    result.pop("remember_api_key", None)
    result.pop("api_key", None)
    dead_key = (EM_API_KEY or load_em_api_key()).strip()
    if dead_key:
        mark_api_key_revoked(dead_key)
    clear_em_api_key_file()
    os.environ.pop("EM_API_KEY", None)
    EM_API_KEY = ""

    reauth = ensure_auth(force_refresh=True)
    if reauth.get("status") == AUTH_NEED_USER:
        # 「验证用户信息失败」给更明确的解决指引
        if reason and _USER_VERIFY_FAIL_RE.search(reason):
            tip = (
                "自选写入失败：验证用户信息失败（当前 EM_API_KEY / 通行证绑定无效或不完整）。"
                "请打开授权链接重新扫码绑定，完成后重新发送原指令。"
            )
        else:
            tip = (
                "未绑定通行证或 EM_API_KEY 已失效（{0}）。请打开授权链接完成扫码绑定，"
                "完成后重新发送原指令。".format(reason)
            )
        return _apply_need_auth(result, reauth, tip)
    if reauth.get("status") == AUTH_OK and reauth.get("newly_obtained") and reauth.get("api_key"):
        result["remember_api_key"] = True
        result["api_key"] = reauth["api_key"]
        result["content"] = "授权已更新，请重新发送原指令。"
        return result
    result["error"] = "EM_API_KEY 失效后重新授权失败: {0}".format(
        reauth.get("message", "未知错误")
    )
    return result


def _flatten(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


# ---------------------------------------------------------------------------
# Entity recognition (/proxy/entity/saas)
# ---------------------------------------------------------------------------

def _extract_entity_items(api_result: Any) -> List[Dict[str, Any]]:
    """
    从实体识别 SaaS 接口返回中提取证券实体。

    优先顺序：
    1. data.entityMetricList（每组取首个候选）
    2. data.entityList（SaaS 标准返回）

    注意：忽略 metricList（可能是地区等非证券指标，不能用于加减自选）。
    """
    if not isinstance(api_result, dict):
        return []
    data_node = api_result.get("data")
    if not isinstance(data_node, dict):
        return []

    raw_items: List[Dict[str, Any]] = []
    entity_metric_list = data_node.get("entityMetricList")
    if isinstance(entity_metric_list, list) and entity_metric_list:
        for group in entity_metric_list:
            if isinstance(group, list) and group and isinstance(group[0], dict):
                raw_items.append(group[0])
            elif isinstance(group, dict):
                raw_items.append(group)
        return raw_items

    entity_list = data_node.get("entityList")
    if isinstance(entity_list, list):
        for item in entity_list:
            if isinstance(item, dict):
                raw_items.append(item)
    return raw_items


def _build_choice_code(item: Dict[str, Any]) -> Optional[str]:
    """
    用实体识别结果拼出 Choice 格式实体代码（新增/删除接口的 sc）。

    实测 SaaS 返回：
      secuCode=300059, marketChar=.SZ  →  300059.SZ
      secuCode=600519, marketChar=.SH  →  600519.SH
    """
    # Already a full Choice code
    for key in ("emCode", "emcode", "fullCode", "securityCode", "sc"):
        candidate = _flatten(item.get(key))
        if candidate and _CHOICE_CODE_RE.match(candidate):
            return candidate.upper()

    secu = _flatten(item.get("secuCode") or item.get("SECURITY_CODE") or item.get("code"))
    market_char = _flatten(
        item.get("marketChar")
        or item.get("MARKET_SHORT_NAME")
        or item.get("marketCode")
    )

    if not secu:
        return None

    # secuCode itself may already be "600519.SH"
    if "." in secu and _CHOICE_CODE_RE.match(secu):
        return secu.upper()

    if not market_char:
        return None

    # marketChar 常见形态：".SZ" / "SZ" / ".SH"
    if market_char.startswith("."):
        code = "{0}{1}".format(secu, market_char)
    else:
        # 纯数字 market 无法拼 Choice 代码
        if market_char.isdigit():
            return None
        code = "{0}.{1}".format(secu, market_char)

    code = code.upper()
    if not _CHOICE_CODE_RE.match(code):
        return None
    return code


def _entity_display_name(item: Dict[str, Any]) -> str:
    for key in (
        "fullName",
        "shortName",
        "securityShortName",
        "SECURITY_SHORT_NAME",
        "entityName",
        "name",
        "showName",
    ):
        value = _flatten(item.get(key))
        if value:
            return value
    code = _build_choice_code(item)
    return code or "未知证券"


def _entity_type_label(item: Dict[str, Any]) -> str:
    for key in ("className", "typeName", "entityType", "securityType", "classCode"):
        value = _flatten(item.get(key))
        if value:
            return value
    return ""


def recognize_entities(user_query: str) -> Tuple[List[Dict[str, Any]], Any]:
    """
    调用实体识别 SaaS 专用接口，将用户自然语言转为可加减自选的实体代码。

    请求体：
      - content: 必填，用户问句
      - typeCodes: 仅 A/港/美股票（002001,002002,002003,002004）
      - disamb: false
    """
    payload = {
        "content": user_query,
        "typeCodes": ENTITY_TYPE_CODES,
        "disamb": False,
    }
    raw = _http_post(ENTITY_URL, payload)
    items = _extract_entity_items(raw)
    results: List[Dict[str, Any]] = []
    seen: set = set()
    for item in items:
        code = _build_choice_code(item)
        name = _entity_display_name(item)
        key = code or _flatten(item.get("entityId")) or name
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "name": name,
                "sc": code,  # Choice 实体代码，供 add/delete 的 sc 参数使用
                "entity_type": _entity_type_label(item),
                "raw": item,
            }
        )
    return results, raw

# ---------------------------------------------------------------------------
# Search / CSV
# ---------------------------------------------------------------------------

def _dig_result_node(raw: Any) -> Dict[str, Any]:
    """Locate the search-code result object that holds dataList/total."""
    if not isinstance(raw, dict):
        return {}
    # Platform wrapper: {code, data: {code, data: {result: {...}}}}
    node: Any = raw
    for _ in range(4):
        if not isinstance(node, dict):
            break
        if isinstance(node.get("dataList"), list) or (
            isinstance(node.get("result"), dict)
            and isinstance(node["result"].get("dataList"), list)
        ):
            break
        nxt = node.get("data")
        if isinstance(nxt, dict):
            node = nxt
            continue
        break

    if isinstance(node, dict) and isinstance(node.get("result"), dict):
        return node["result"]
    if isinstance(node, dict):
        return node
    return {}


def _row_from_datalist_item(item: Dict[str, Any]) -> Dict[str, str]:
    name = _flatten(
        item.get("SECURITY_SHORT_NAME")
        or item.get("securityShortName")
        or item.get("name")
    )
    code = _flatten(item.get("SECURITY_CODE") or item.get("securityCode") or item.get("code"))
    market = _flatten(
        item.get("MARKET_SHORT_NAME")
        or item.get("marketShortName")
        or item.get("market")
    )
    price = _flatten(item.get("NEWEST_PRICE") or item.get("newestPrice") or item.get("price"))
    chg = _flatten(item.get("CHG") or item.get("chg") or item.get("changePct"))
    return {
        "名称": name,
        "代码": code,
        "市场代码": market,
        "最新价（元）": price,
        "涨跌幅（%）": chg,
    }


def search_watchlist(
    need_choice_optional: bool,
    key_word: str,
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Paginate search-code until all rows are collected. key_word 为 user-query 原样。"""
    key_word = (key_word or "").strip()
    if not key_word:
        raise ValueError("查询 keyWord（user-query）不能为空")
    all_rows: List[Dict[str, str]] = []
    page_no = 1
    total: Optional[int] = None
    last_raw: Dict[str, Any] = {}

    while True:
        payload = {
            "keyWord": key_word,
            "pageNo": page_no,
            "pageSize": PAGE_SIZE,
            "needChoiceOptional": need_choice_optional,
        }
        raw = _http_post(SEARCH_URL, payload)
        if not isinstance(raw, dict):
            raise RuntimeError("自选查询接口返回格式异常")
        last_raw = raw

        result_node = _dig_result_node(raw)
        data_list = result_node.get("dataList")
        if not isinstance(data_list, list):
            data_list = []

        for item in data_list:
            if isinstance(item, dict):
                all_rows.append(_row_from_datalist_item(item))

        if total is None:
            for key in ("total", "totalRecordCount"):
                value = result_node.get(key)
                if isinstance(value, int):
                    total = value
                    break
                if isinstance(value, str) and value.isdigit():
                    total = int(value)
                    break

        if not data_list:
            break
        if total is not None and len(all_rows) >= total:
            break
        if len(data_list) < PAGE_SIZE:
            break
        page_no += 1
        if page_no > 1000:
            break

    return all_rows, last_raw


def _csv_text_cell(value: str) -> str:
    """Excel 打开 CSV 时把纯数字当数值，会丢掉 000001 的前导 0；写成文本公式保留原样。"""
    text = (value or "").strip()
    if not text:
        return ""
    return '="{0}"'.format(text.replace('"', '""'))


def _write_csv(rows: List[Dict[str, str]], note: str, output_dir: Path) -> str:
    """Write watchlist rows as CSV (utf-8-sig for Excel-friendly Chinese)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "self_select_{0}.csv".format(uuid.uuid4().hex[:8])
    headers = ["名称", "代码", "市场代码", "最新价（元）", "涨跌幅（%）"]

    with path.open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "名称": row.get("名称", ""),
                    "代码": _csv_text_cell(row.get("代码", "")),
                    "市场代码": row.get("市场代码", ""),
                    "最新价（元）": row.get("最新价（元）", ""),
                    "涨跌幅（%）": row.get("涨跌幅（%）", ""),
                }
            )
        # Blank row then footnote at list bottom.
        writer.writerow({h: "" for h in headers})
        writer.writerow({"名称": note})

    return str(path)


def _summarize_rows(rows: List[Dict[str, str]], limit: int = 20) -> str:
    lines = ["共 {0} 条自选。".format(len(rows)), ""]
    preview = rows[:limit]
    for idx, row in enumerate(preview, start=1):
        name = row.get("名称") or "-"
        code = row.get("代码") or "-"
        market = row.get("市场代码") or "-"
        price = row.get("最新价（元）") or "-"
        chg = row.get("涨跌幅（%）") or "-"
        lines.append(
            "{0}. {1} ({2}.{3}) 最新价={4} 涨跌幅={5}".format(
                idx, name, code, market, price, chg
            )
        )
    if len(rows) > limit:
        lines.append("... 其余 {0} 条见 CSV 文件".format(len(rows) - limit))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Add / Delete
# ---------------------------------------------------------------------------

_SUCCESS_MESSAGES = {"成功", "部分成功"}


def _extract_fail_list(raw: Any) -> List[Any]:
    """新增/删除接口 failList；空列表表示该标的成功。"""
    if not isinstance(raw, dict):
        return []
    fail_list = raw.get("failList")
    if isinstance(fail_list, list):
        return fail_list
    data = raw.get("data")
    if isinstance(data, dict):
        fail_list = data.get("failList")
        if isinstance(fail_list, list):
            return fail_list
        inner = data.get("raw")
        if isinstance(inner, dict):
            fail_list = inner.get("failList")
            if isinstance(fail_list, list):
                return fail_list
            inner_data = inner.get("data")
            if isinstance(inner_data, dict):
                fail_list = inner_data.get("failList")
                if isinstance(fail_list, list):
                    return fail_list
    return []


def _fail_list_hit(fail_list: List[Any], sc: str) -> Optional[str]:
    """
    按 secuCode 匹配 failList。命中返回 reason（可为空串）；未命中返回 None。

    失败项形态：{"secuCode":"09988.HK","reason":"成分不存在"}
    同一份 failList 可能被复制到每条 data 上，必须按代码对齐，不能把别人的失败算到当前标的。
    """
    if not sc or not fail_list:
        return None
    sc_u = sc.upper()
    hit = False
    reasons: List[str] = []
    for item in fail_list:
        if isinstance(item, dict):
            item_sc = _flatten(
                item.get("secuCode") or item.get("sc") or item.get("code")
            ).upper()
            if item_sc != sc_u:
                continue
            hit = True
            reason = _flatten(
                item.get("reason")
                or item.get("message")
                or item.get("msg")
                or item.get("error")
            )
            if reason:
                reasons.append(reason)
        elif isinstance(item, str) and item.strip().upper() == sc_u:
            hit = True
    if not hit:
        return None
    return "；".join(reasons)


def _top_looks_success(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    message = _flatten(payload.get("message"))
    if message in _SUCCESS_MESSAGES:
        return True
    state = payload.get("state")
    if isinstance(state, int) and state == 0:
        return True
    return False


def _items_from_fail_list(
    sc_list: List[str],
    fail_list: List[Any],
    *,
    fallback_success: bool,
    missing_msg: str,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for code in sc_list:
        sc = _flatten(code).upper()
        hit_reason = _fail_list_hit(fail_list, sc) if fail_list else None
        if hit_reason is not None:
            items.append(
                {
                    "sc": sc,
                    "state": 1,
                    "message": hit_reason or "操作失败",
                }
            )
        elif fallback_success:
            items.append({"sc": sc, "state": 0, "message": "成功"})
        else:
            items.append({"sc": sc, "state": 1, "message": missing_msg})
    return items


def _parse_one_mutate_entry(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    解析 data[] 中单条新增/删除结果。

    成功：state=0，failList=[]
    部分成功：外层 message=部分成功、state=0，failList 只列出失败标的
    失败：failList=[{"secuCode":"...","reason":"成分不存在"|"证券代码不存在"|...}]
    有 failList 时只把出现在列表里的 sc 判失败；其它标的即使外层是「部分成功」也不跟读。
    """
    sc = _flatten(entry.get("sc")).upper()
    if not sc:
        return None
    raw = entry.get("raw") if isinstance(entry.get("raw"), dict) else {}
    state = entry.get("state")
    if not isinstance(state, int):
        state = raw.get("state") if isinstance(raw.get("state"), int) else 1
    message = _flatten(raw.get("message") or entry.get("message"))

    fail_list = _extract_fail_list(raw) or _extract_fail_list(entry)
    if fail_list:
        hit_reason = _fail_list_hit(fail_list, sc)
        if hit_reason is not None:
            state = 1
            if hit_reason:
                message = hit_reason
            elif not message or message in {"成功", "失败", "部分成功"}:
                message = "操作失败"
        else:
            # failList 属于其它标的（接口会把同一份失败列表挂到每条上）
            state = 0
            message = "成功"
    return {"sc": sc, "state": state, "message": message}


def _parse_mutate_item_results(payload: Any) -> List[Dict[str, Any]]:
    """解析新增/删除接口返回：优先 data 数组，每项含 sc、raw.data.failList。"""
    items: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return items
    data = payload.get("data")
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            parsed = _parse_one_mutate_entry(entry)
            if parsed:
                items.append(parsed)
    return items


def _coerce_mutate_items(
    raw: Any,
    sc_list: List[str],
    missing_msg: str,
) -> List[Dict[str, Any]]:
    """
    把接口返回收成逐 sc 结果。
    data 为对象（非数组）时：按 failList 逐码判定；外层 message=成功 且未命中失败列表 → 成功。
    """
    items = _parse_mutate_item_results(raw)
    if items:
        return items
    if not sc_list:
        return items

    data = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(data, dict):
        parsed = _parse_one_mutate_entry(data)
        if parsed:
            return [parsed]
        fail_list = _extract_fail_list(data) or _extract_fail_list(raw)
        return _items_from_fail_list(
            sc_list,
            fail_list,
            fallback_success=_top_looks_success(raw) or bool(fail_list),
            missing_msg=missing_msg,
        )

    looks_ok = _top_looks_success(raw)
    for code in sc_list:
        items.append(
            {
                "sc": _flatten(code).upper(),
                "state": 0 if looks_ok else 1,
                "message": "成功" if looks_ok else missing_msg,
            }
        )
    return items


def add_self_select(sc_list: List[str]) -> Tuple[List[Dict[str, Any]], Any]:
    """
    新增自选；返回逐实体结果列表 + 原始响应。

    每项：{"sc": "MU.O", "state": 0|1, "message": "成功"|失败原因}
    """
    sc = ",".join(sc_list)
    raw = _http_post(ADD_URL, {"source": "choice", "sc": sc})
    return _coerce_mutate_items(raw, sc_list, "添加结果未返回"), raw


def delete_self_select(sc_list: List[str]) -> Tuple[List[Dict[str, Any]], Any]:
    """
    删除自选；返回逐实体结果列表 + 原始响应。

    每项：{"sc": "603127.SH", "state": 0|1, "message": "成功"|"自选股不存在"|...}
    """
    sc = ",".join(sc_list)
    raw = _http_post(DELETE_URL, {"source": "choice", "sc": sc})
    return _coerce_mutate_items(raw, sc_list, "删除结果未返回"), raw


def _format_add_result(
    supported: List[Dict[str, Any]],
    unsupported: List[Dict[str, Any]],
    add_items: List[Dict[str, Any]],
) -> str:
    """
    按新增接口逐实体 state/message 组装话术。

    示例：
      已成功添加到 choice--我的自选分类下：武钢股份；已在自选：美光
      已成功添加到 choice--我的自选分类下：茅台；自选添加失败：某标的（无匹配数据）
    """
    parts: List[str] = []
    sc_to_name = {
        _flatten(item.get("sc")).upper(): item.get("name") or _flatten(item.get("sc"))
        for item in supported
        if item.get("sc")
    }

    success_names: List[str] = []
    already_names: List[str] = []
    fail_parts: List[str] = []
    seen_sc: set = set()
    hit_limit = False

    for entry in add_items:
        sc = _flatten(entry.get("sc")).upper()
        if not sc or sc in seen_sc:
            continue
        seen_sc.add(sc)
        name = sc_to_name.get(sc) or sc
        state = entry.get("state")
        message = _flatten(entry.get("message")) or "添加失败"
        if state == 0 or message in _SUCCESS_MESSAGES:
            success_names.append(name)
        elif message and _LIMIT_HINT_RE.search(message):
            hit_limit = True
            fail_parts.append("{0}（{1}）".format(name, MSG_LIMIT_REACHED))
        elif message and _DUPLICATE_ADD_HINT_RE.search(message):
            # 「重复添加或无匹配数据」等接口原文 → 产品化为「已在自选」
            already_names.append(name)
        else:
            fail_parts.append("{0}（{1}）".format(name, message))

    for item in supported:
        sc = _flatten(item.get("sc")).upper()
        if sc and sc not in seen_sc:
            fail_parts.append("{0}（添加结果未返回）".format(item.get("name") or sc))

    # 全部因上限失败时，直接返回统一上限话术
    if hit_limit and not success_names and not already_names and fail_parts and all(
        MSG_LIMIT_REACHED in p for p in fail_parts
    ):
        parts.append(MSG_LIMIT_REACHED)
    else:
        if success_names:
            parts.append("{0}：{1}".format(MSG_ADD_SUCCESS, "、".join(success_names)))
        if already_names:
            parts.append("{0}：{1}".format(MSG_ALREADY_IN_WATCHLIST, "、".join(already_names)))
        if fail_parts:
            parts.append("自选添加失败：{0}".format("、".join(fail_parts)))

    if unsupported:
        names = "、".join(item["name"] for item in unsupported)
        parts.append(
            "{0}：{1}".format(MSG_ADD_TYPE_UNSUPPORTED, names)
            if names
            else MSG_ADD_TYPE_UNSUPPORTED
        )

    if not parts:
        return MSG_ADD_TYPE_UNSUPPORTED
    return "；".join(parts)


def _format_delete_result(
    supported: List[Dict[str, Any]],
    unsupported: List[Dict[str, Any]],
    delete_items: List[Dict[str, Any]],
) -> str:
    """
    按删除接口逐实体 state/message 组装话术。

    示例：
      已成功删除 choice--我的自选 分类下对应证券：昭衍新药；自选删除失败：深桑达Ａ（自选股不存在）
    """
    parts: List[str] = []
    sc_to_name = {
        _flatten(item.get("sc")).upper(): item.get("name") or _flatten(item.get("sc"))
        for item in supported
        if item.get("sc")
    }

    success_names: List[str] = []
    fail_parts: List[str] = []
    seen_sc: set = set()

    for entry in delete_items:
        sc = _flatten(entry.get("sc")).upper()
        if not sc or sc in seen_sc:
            continue
        seen_sc.add(sc)
        name = sc_to_name.get(sc) or sc
        state = entry.get("state")
        message = _flatten(entry.get("message")) or "删除失败"
        if state == 0 or message in _SUCCESS_MESSAGES:
            success_names.append(name)
        elif message and _DELETE_MISSING_HINT_RE.search(message):
            fail_parts.append("{0}（{1}）".format(name, MSG_NOT_IN_WATCHLIST))
        else:
            fail_parts.append("{0}（{1}）".format(name, message))

    # 请求了但响应里没有的 sc
    for item in supported:
        sc = _flatten(item.get("sc")).upper()
        if sc and sc not in seen_sc:
            fail_parts.append("{0}（删除结果未返回）".format(item.get("name") or sc))

    if success_names:
        parts.append("{0}：{1}".format(MSG_DELETE_SUCCESS, "、".join(success_names)))
    if fail_parts:
        parts.append("自选删除失败：{0}".format("、".join(fail_parts)))

    if unsupported:
        names = "、".join(item["name"] for item in unsupported)
        parts.append(
            "{0}：{1}".format(MSG_DELETE_TYPE_UNSUPPORTED, names)
            if names
            else MSG_DELETE_TYPE_UNSUPPORTED
        )

    if not parts:
        return MSG_DELETE_TYPE_UNSUPPORTED
    return "；".join(parts)


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def manage_watchlist(
    user_query: str,
    operation: str,
    business_line: str,
    output_dir: Optional[Path] = None,
    save_to_file: bool = True,
) -> Dict[str, Any]:
    user_query = (user_query or "").strip()
    operation = (operation or "").strip().lower()
    business_line = (business_line or "").strip().lower()

    result: Dict[str, Any] = {
        "user_query": user_query,
        "operation": operation,
        "business_line": business_line,
        "content": "",
        "output_path": None,
        "raw": None,
    }

    if operation not in {"query", "add", "delete"}:
        result["error"] = "operation 必须是 query / add / delete"
        return result
    if business_line not in {"eastmoney", "choice", "other"}:
        result["error"] = "business-line 必须是 eastmoney / choice / other"
        return result
    if not user_query:
        result["error"] = "user-query 不能为空"
        return result

    global EM_API_KEY
    auth = ensure_auth()
    if auth.get("status") == AUTH_NEED_USER:
        return _apply_need_auth(
            result,
            auth,
            "尚未完成授权或未绑定通行证。请打开授权链接扫码绑定，完成后重新发送原指令。",
        )
    if auth.get("status") == AUTH_ERROR:
        result["error"] = auth.get("message", "授权流程出错")
        return result

    newly_obtained_key = auth.get("api_key") if auth.get("newly_obtained") else None
    if newly_obtained_key:
        result["remember_api_key"] = True
        result["api_key"] = newly_obtained_key
    EM_API_KEY = newly_obtained_key or load_em_api_key()
    if not EM_API_KEY:
        result["error"] = "EM_API_KEY 落盘异常，请重新执行或检查 ~/.mx-skills/em_api_key"
        return result

    try:
        if operation == "query":
            return _handle_query(
                result,
                user_query=user_query,
                business_line=business_line,
                output_dir=output_dir,
                save_to_file=save_to_file,
            )
        if business_line == "eastmoney":
            result["content"] = (
                MSG_ADD_EASTMONEY_UNSUPPORTED
                if operation == "add"
                else MSG_DELETE_EASTMONEY_UNSUPPORTED
            )
            return result
        return _handle_mutate(result, user_query, operation)
    except AuthError as exc:
        return _handle_auth_revoked(str(exc) or MSG_REBIND, result)
    except Exception as exc:
        result["error"] = str(exc)
        return result


def _handle_query(
    result: Dict[str, Any],
    user_query: str,
    business_line: str,
    output_dir: Optional[Path],
    save_to_file: bool,
) -> Dict[str, Any]:
    # other（未指明业务线）默认按 Choice 处理
    need_choice = business_line != "eastmoney"
    # 查询 keyWord：user-query 原样透传，不做归一/启发式改写
    key_word = (user_query or "").strip()

    rows, raw = search_watchlist(
        need_choice_optional=need_choice,
        key_word=key_word,
    )
    result["raw"] = {"search_keyword": key_word, "response": raw}

    # 查询结果：接口返回什么就展示什么；空结果不走启发式分流，按业务线固定话术
    if business_line == "eastmoney":
        empty_msg = MSG_EMPTY_EASTMONEY
        note = NOTE_EASTMONEY
    else:
        empty_msg = MSG_EMPTY_CHOICE
        note = NOTE_CHOICE

    if not rows:
        result["content"] = empty_msg
        return result

    out_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
    lines: List[str] = []
    if save_to_file:
        path = _write_csv(rows, note=note, output_dir=out_dir)
        result["output_path"] = path
        lines.append("Saved: {0}".format(path))
    lines.append("查询问句：{0}".format(key_word))
    lines.append(_summarize_rows(rows))
    lines.append("")
    lines.append("备注：{0}".format(note))
    result["content"] = "\n".join(lines)
    return result


def _handle_mutate(
    result: Dict[str, Any],
    user_query: str,
    operation: str,
) -> Dict[str, Any]:
    """
    新增/删除统一流程：
      1. 用户问句 → 实体识别 SaaS（/proxy/entity/saas，仅 A/港/美 typeCodes）
      2. 识别结果有实体代码则原样用于 add/delete；为空则返回类型不支持兜底话术
    禁止跳过实体识别、禁止直接把用户原文当 sc。
    """
    entities, entity_raw = recognize_entities(user_query)
    result["raw"] = {"entity_api": entity_raw, "entities": entities}
    # 识别为空（板块等不在 typeCodes 内）→ 该实体类型暂不支持
    usable = [e for e in entities if e.get("sc")]
    if not usable:
        result["content"] = (
            MSG_ADD_TYPE_UNSUPPORTED
            if operation == "add"
            else MSG_DELETE_TYPE_UNSUPPORTED
        )
        return result

    # sc 必须来自实体识别返回字段拼装，不能用用户原文
    sc_list = [e["sc"] for e in usable]
    if operation == "add":
        add_items, mutate_raw = add_self_select(sc_list)
        result["raw"]["mutate_api"] = mutate_raw
        result["raw"]["sc"] = ",".join(sc_list)
        result["raw"]["add_items"] = add_items
        if _mutate_items_need_reauth(add_items):
            return _handle_auth_revoked("验证用户信息失败", result)
        result["content"] = _format_add_result(
            supported=usable,
            unsupported=[],
            add_items=add_items,
        )
    else:
        delete_items, mutate_raw = delete_self_select(sc_list)
        result["raw"]["mutate_api"] = mutate_raw
        result["raw"]["sc"] = ",".join(sc_list)
        result["raw"]["delete_items"] = delete_items
        if _mutate_items_need_reauth(delete_items):
            return _handle_auth_revoked("验证用户信息失败", result)
        result["content"] = _format_delete_result(
            supported=usable,
            unsupported=[],
            delete_items=delete_items,
        )
    return result


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage Miaoxiang Choice / Eastmoney watchlists."
    )
    parser.add_argument("--user-query", required=True, help="指代消解后的用户问句")
    parser.add_argument(
        "--operation",
        required=True,
        choices=["query", "add", "delete"],
        help="操作类型",
    )
    parser.add_argument(
        "--business-line",
        required=True,
        choices=["eastmoney", "choice", "other"],
        help="业务线：eastmoney=东财App；choice=Choice；other=未指明时的默认值（按Choice处理）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="",
        help="查询结果 CSV 输出目录（默认 miaoxiang/self_select）",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="查询时不写入 CSV",
    )
    return parser


def _print_remember_api_key(result: Dict[str, Any]) -> None:
    """
    仅在 Agent 捕获 stdout（非交互终端）时输出，供平台落盘 EM_API_KEY。
    人在终端直接跑脚本时不打印，避免把 apiKey 混进业务结果。
    """
    if not result.get("remember_api_key"):
        return
    if sys.stdout.isatty():
        return
    print("remember_api_key: true")
    print("credential_name: EM_API_KEY")
    print("apiKey: {0}".format(result["api_key"]))
    print(
        "agent_action: 将 apiKey 的精确完整值以 EM_API_KEY 保存到所在平台提供的私有跨会话持久存储；"
        "绝不向用户展示、复述或写入业务文件。后续调用前先从该持久存储读取，并仅作为当前进程的"
        " EM_API_KEY 环境变量注入；若平台不支持持久化或读取失败，则回退到正常授权流程。"
    )


def run_cli() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = _build_arg_parser()
    args = parser.parse_args()
    output_dir = Path(args.output_dir) if args.output_dir else None

    result = manage_watchlist(
        user_query=args.user_query,
        operation=args.operation,
        business_line=args.business_line,
        output_dir=output_dir,
        save_to_file=not args.no_save,
    )

    _print_remember_api_key(result)
    if result.get("need_auth"):
        print("need_auth: true")
        if result.get("authUrl"):
            print("authUrl: {0}".format(result["authUrl"]))
        if result.get("apiKeyUrl"):
            print("apiKeyUrl: {0}".format(result["apiKeyUrl"]))
        if result.get("auth_message"):
            print(result["auth_message"])
        raise SystemExit(10)

    if result.get("error"):
        print("Error: {0}".format(result["error"]))
        raise SystemExit(2)

    content = result.get("content") or ""
    print(content)


if __name__ == "__main__":
    run_cli()
