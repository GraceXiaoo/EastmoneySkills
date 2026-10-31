"""
行业/个股跟踪报告生成脚本。

输入:
- query (用户原始问题)

输出(JSON):
- title: 报告标题
- content: 按 skill 规范生成的正文(仅总结章节)
- attachments: PDF/DOCX 保存路径

错误处理:
- ERROR_ENTITY -> "目前暂不支持此类实体体进行分析。"
- 其他异常 -> "报告生成服务暂时不可用，请稍后重试。"
"""

import argparse
import base64
import json
import os
import socket
import sys
import urllib.error
import urllib.request
import traceback
import uuid
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from auth import AUTH_ERROR, AUTH_NEED_USER, AUTH_OK, ensure_auth

EM_BASE_URL = "https://ai-saas.eastmoney.com".rstrip("/")
EM_API_KEY_PLACEHOLDER = "{em" + "_api_key}"
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()

if EM_API_KEY and EM_API_KEY != EM_API_KEY_PLACEHOLDER:
    os.environ.setdefault("EM_API_KEY", EM_API_KEY)

AUTH_API_KEY_URL_FALLBACK = f"{EM_BASE_URL}/mxClaw"
API_URL = f"{EM_BASE_URL}/proxy/app-robo-advisor-api/assistant/write/tracking/report"
TOOL_NAME = "行业/个股跟踪报告"
SKILL_SLUG = "industry_stock_tracker"
DEFAULT_OUTPUT_DIR = Path.cwd() / "miaoxiang" / SKILL_SLUG

ERROR_ENTITY_MSG = "目前暂不支持此类实体体进行分析。"
GENERAL_ERROR_MSG = "报告生成服务暂时不可用，请稍后重试。"


class ApiCallError(Exception):
    def __init__(self, code: str, detail: str):
        Exception.__init__(self, detail)
        self.code = code
        self.detail = detail


class _AuthRevoked(Exception):
    """The API rejected EM_API_KEY with HTTP or business status 401/403."""


def _load_em_api_key() -> str:
    env_value = (os.environ.get("EM_API_KEY") or "").strip()
    if env_value:
        return env_value
    if EM_API_KEY and EM_API_KEY != EM_API_KEY_PLACEHOLDER:
        return EM_API_KEY
    cred_path = Path.home() / ".mx-skills" / "em_api_key"
    if cred_path.exists():
        return cred_path.read_text(encoding="utf-8").strip()
    return ""


def _clear_em_api_key_file() -> None:
    cred_path = Path.home() / ".mx-skills" / "em_api_key"
    try:
        cred_path.unlink(missing_ok=True)
    except OSError:
        pass


def _raise_if_auth_revoked(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    code = payload.get("code")
    status = payload.get("status")
    if code in (401, "401", 403, "403") or status in (401, "401", 403, "403"):
        raise _AuthRevoked("business auth rejected: code={0}, status={1}".format(code, status))


def _print_auth_result(result: Dict[str, Any]) -> int:
    if result.get("newly_obtained") and result.get("api_key"):
        print("remember_api_key: true")
        print("credential_name: EM_API_KEY")
        print("apiKey: {0}".format(result["api_key"]))
        print("agent_action: 将 apiKey 的精确完整值以 EM_API_KEY 保存到平台私有跨会话存储，绝不向用户展示。")
    if result.get("status") == AUTH_NEED_USER:
        print("need_auth: true")
        print("authUrl: {0}".format(result.get("auth_url") or ""))
        print("apiKeyUrl: {0}".format(result.get("api_key_url") or AUTH_API_KEY_URL_FALLBACK))
        print("尚未完成授权。请优先扫码授权，完成后重新发送原指令。")
        return 10
    if result.get("status") == AUTH_ERROR:
        print(json.dumps({"ok": False, "error_code": "AUTH_ERROR", "message": result.get("message", "授权流程出错")}, ensure_ascii=False))
        return 2
    return 0


def _restart_authorization() -> Dict[str, Any]:
    _clear_em_api_key_file()
    env_key = os.environ.pop("EM_API_KEY", None)
    try:
        return ensure_auth()
    finally:
        if env_key is not None:
            os.environ["EM_API_KEY"] = env_key


def _safe_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _clean_report_text(text: str) -> str:
    if not text:
        return ""
    cleaned = text
    # 去掉内部协议链接（如 blockTitle://、table://）
    cleaned = re.sub(r"\[[^\]]*\]\((?:blockTitle|table)://[^)]*\)", "", cleaned)
    # 普通 markdown 链接转纯文本，仅保留标题
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    # 规范化换行和空白
    cleaned = cleaned.replace("\\n", "\n")
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def _read_query_from_stdin() -> str:
    raw = sys.stdin.read().strip()
    if not raw:
        return ""
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return _safe_str(payload.get("query", ""))
        if isinstance(payload, str):
            return payload.strip()
    except json.JSONDecodeError:
        return raw
    return ""

def _call_api(query: str, api_key: str, timeout: float = 1200.0) -> Dict[str, Any]:
    req_body = json.dumps(
        {"query": query, "needFullContent": True}, ensure_ascii=False
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        method="POST",
        data=req_body,
        headers={
            "Content-Type": "application/json",
            "em_api_key": api_key,
            "Accept": "application/json",
            "User-Agent": "industry-stock-tracker/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = getattr(resp, "status", None) or resp.getcode()
            content = resp.read()

    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise _AuthRevoked("HTTP {0}".format(e.code)) from e
        raw = e.read() if hasattr(e, "read") else b""
        snippet = raw[:500].decode("utf-8", errors="replace")
        raise ApiCallError("HTTP_ERROR", "status={0}, body={1}".format(e.code, snippet))
    except socket.timeout:
        raise ApiCallError("TIMEOUT", "read operation timed out")
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", e)
        if isinstance(reason, socket.timeout):
            raise ApiCallError("TIMEOUT", "read operation timed out")
        raise ApiCallError("NETWORK_ERROR", _safe_str(reason))

    text = content.decode("utf-8", errors="replace")
    if status_code and int(status_code) >= 400:
        raise ApiCallError("HTTP_ERROR", "status={0}, body={1}".format(status_code, text[:500]))

    try:
        parsed = json.loads(text) if text else {}
    except Exception:
        raise ApiCallError("INVALID_JSON", text[:500])

    if isinstance(parsed, dict):
        _raise_if_auth_revoked(parsed)
        return parsed
    return {"data": parsed}


def _unwrap_data(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "result", "content"):
        node = payload.get(key)
        if isinstance(node, dict):
            return node
    return payload

def _default_output_dir() -> str:
    """
    Allow overriding attachment output directory via env:
      INDUSTRY_STOCK_TRACKER_OUTPUT_DIR
    """
    env = os.environ.get("INDUSTRY_STOCK_TRACKER_OUTPUT_DIR", "").strip()
    return env or str(DEFAULT_OUTPUT_DIR)


def _save_source_trace_list(data: Dict[str, Any]) -> str:
    output_dir = Path.cwd() / "miaoxiang"
    output_dir.mkdir(parents=True, exist_ok=True)
    article_id = _safe_str(data.get("articleId"), default=uuid.uuid4().hex)
    safe_article_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", article_id)
    path = output_dir / "sourceTrace_{0}.json".format(safe_article_id)
    path.write_text(
        json.dumps(data.get("sourceTraceList"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def _decode_attachment_base64(data: Dict[str, Any], output_dir: str) -> List[Dict[str, str]]:
    attachments: List[Dict[str, str]] = []
    os.makedirs(output_dir, exist_ok=True)

    file_map = [
        ("wordBase64", "docx", "DOCX"),
        ("pdfBase64", "pdf", "PDF"),
    ]
    article_id = _safe_str(data.get("articleId"), default=uuid.uuid4().hex)
    safe_article_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", article_id)

    for key, ext, ftype in file_map:
        b64_str = _safe_str(data.get(key))
        if not b64_str:
            continue
        try:
            raw = base64.b64decode(b64_str)
        except Exception:
            continue
        file_name = "{0}_{1}.{2}".format(safe_article_id, ftype.lower(), ext)
        file_path = os.path.join(output_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(raw)
        attachments.append({"type": ftype, "url": file_path})
    return attachments

def _render_content(entity_type: str, summary_content: str) -> str:
    return (
        f"已生成{entity_type}跟踪报告，包括行业和个股的多种信源摘要。"
        "此处省略正文内容，仅展示总结章节，如需查看完整内容，请查看附件获取报告详情。\n\n"
        f"{summary_content}"
    )


def build_report_output(
    query: str,
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    raw_data = payload.get("data") if isinstance(payload, dict) else None
    data = _unwrap_data(payload)
    code = _safe_str(payload.get("code") if isinstance(payload, dict) else "")
    message = _safe_str(payload.get("message") if isinstance(payload, dict) else "")

    # 明确错误码处理
    if code == "ERROR_ENTITY" or _safe_str(data.get("code")) == "ERROR_ENTITY":
        return {"ok": False, "error_code": "ERROR_ENTITY", "message": ERROR_ENTITY_MSG}

    # 简化规则：message 有值且 data 为空，直接返回接口 message
    if message and not raw_data:
        return {
            "ok": False,
            "error_code": code or "API_ERROR",
            "message": message,
        }

    title = _safe_str(data.get("title"), default="行业/个股跟踪报告")
    share_url = _safe_str(data.get("shareUrl"), default="无")
    entity_type = _safe_str(data.get("entityType") or data.get("entity_type"), default="行业/个股")
    summary = _safe_str(data.get("content"), default="")
    attachments = _decode_attachment_base64(data, _default_output_dir())
    source_trace_path = _save_source_trace_list(data)

    if not summary:
        summary = "暂无总结内容，请查看附件获取报告详情。"

    output = {
        "ok": True,
        "tool": TOOL_NAME,
        "query": query,
        "title": title,
        "content": _render_content(entity_type=entity_type, summary_content=summary),
        "attachments": attachments,
        "share_url": share_url,
        "source_trace_path": source_trace_path,
    }
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成行业/个股跟踪报告")
    parser.add_argument("--query", type=str, default="", help="用户查询文本")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    query = _safe_str(args.query) or _read_query_from_stdin()
    if not query:
        print(
            json.dumps(
                {"ok": False, "error_code": "BAD_REQUEST", "message": "缺少 query 参数"},
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    auth = ensure_auth()
    auth_exit = _print_auth_result(auth)
    if auth_exit:
        sys.exit(auth_exit)
    api_key = auth.get("api_key") if auth.get("newly_obtained") else _load_em_api_key()
    if not api_key:
        print(json.dumps({"ok": False, "error_code": "AUTH_ERROR", "message": "EM_API_KEY 落盘异常"}, ensure_ascii=False))
        sys.exit(2)

    try:
        payload = _call_api(query=query, api_key=api_key)
        output = build_report_output(
            query=query,
            payload=payload,
        )
        print(json.dumps(output, ensure_ascii=False))
        sys.exit(0 if output.get("ok") else 2)
    except _AuthRevoked:
        reauth = _restart_authorization()
        auth_exit = _print_auth_result(reauth)
        if auth_exit == 10 and os.environ.get("EM_API_KEY", "").strip():
            print("环境变量 EM_API_KEY 仍含有失效 key，请先清除该环境变量。")
        sys.exit(auth_exit or 2)
    except ApiCallError as e:
        err = {
            "ok": False,
            "error_code": e.code,
            "message": GENERAL_ERROR_MSG,
            "detail": e.detail,
        }
        print(json.dumps(err, ensure_ascii=False))
        sys.exit(2)
    except Exception as e:
        err = {
            "ok": False,
            "error_code": "UNEXPECTED_ERROR",
            "message": GENERAL_ERROR_MSG,
            "detail": _safe_str(e),
            "traceback": traceback.format_exc(limit=8),
        }
        print(json.dumps(err, ensure_ascii=False))
        sys.exit(2)


if __name__ == "__main__":
    main()
