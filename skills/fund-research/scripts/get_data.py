"""Fund research report runtime with inline EM_API_KEY authorization."""

import argparse
import asyncio
import base64
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request

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
DEFAULT_OUTPUT_DIR = Path(
    os.environ.get("FUND_RESEARCH_OUTPUT_DIR")
    or Path.cwd() / "miaoxiang" / "fund-research"
)
TIMEOUT_SECONDS = 1200
REPORT_URL = f"{EM_BASE_URL}/proxy/app-robo-advisor-api/assistant/write/fund/research"


def _load_em_api_key() -> str:
    value = (os.environ.get("EM_API_KEY") or "").strip()
    if value:
        return value
    if EM_API_KEY and EM_API_KEY != EM_API_KEY_PLACEHOLDER:
        return EM_API_KEY
    path = Path.home() / ".mx-skills" / "em_api_key"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


class _AuthRevoked(Exception):
    pass


def _clear_em_api_key_file() -> None:
    try:
        (Path.home() / ".mx-skills" / "em_api_key").unlink(missing_ok=True)
    except OSError:
        pass


def _handle_auth_revoked(reason: str, result: Dict[str, Any]) -> Dict[str, Any]:
    result.pop("remember_api_key", None)
    result.pop("api_key", None)
    _clear_em_api_key_file()
    env_key = os.environ.pop("EM_API_KEY", None)
    try:
        auth = ensure_auth()
    finally:
        if env_key is not None:
            os.environ["EM_API_KEY"] = env_key
    if auth["status"] == AUTH_NEED_USER:
        result.update(
            need_auth=True,
            authUrl=auth["auth_url"],
            apiKeyUrl=auth["api_key_url"],
            auth_message=(
                "EM_API_KEY was revoked ({0}); authorize again and resend the original prompt."
            ).format(reason),
        )
        if env_key and env_key.strip():
            result["auth_message"] += " Clear the revoked EM_API_KEY environment variable first."
    elif auth["status"] == AUTH_OK:
        result["error"] = "Clear the revoked EM_API_KEY environment variable and retry authorization."
    else:
        result["error"] = "Failed to create a fresh authorization URL: {0}".format(
            auth.get("message", "unknown authorization error")
        )
    return result


def _error_message(body: str) -> str:
    try:
        data = json.loads((body or "").strip())
    except Exception:
        return (body or "").strip()[:200]
    if isinstance(data, dict):
        for key in ("msg", "message", "error", "stack"):
            if isinstance(data.get(key), str) and data[key].strip():
                return data[key].strip()
    return (body or "").strip()[:200]


def _business_error_message(raw: Dict[str, Any]) -> str:
    success_values = (None, 0, "0", 200, "200")
    code, status = raw.get("code"), raw.get("status")
    if code in success_values and status in success_values:
        return ""
    for key in ("msg", "message", "error", "stack"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "business response rejected (code={0!r}, status={1!r})".format(code, status)


def _extract_content(raw: Dict[str, Any]) -> str:
    data = raw.get("data") if isinstance(raw, dict) else None
    sources = [data, raw]
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("content", "displayData", "answer", "summary"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, (list, dict)):
                return json.dumps(value, ensure_ascii=False, indent=2)
    return ""


def _extract_data_markdown(raw: Dict[str, Any]) -> str:
    if not isinstance(raw, dict) or not isinstance(raw.get("data"), dict):
        return ""
    data = raw["data"]
    value = data.get("dataMarkdown")
    if value is None:
        value = data.get("dataMarkDown")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return ""


def _has_valid_report(raw: Dict[str, Any]) -> bool:
    if not isinstance(raw, dict):
        return False
    if raw.get("code") not in (None, 0, "0", 200, "200"):
        return False
    if raw.get("status") not in (None, 0, "0", 200, "200"):
        return False
    data = raw.get("data")
    return isinstance(data, dict) and bool(_extract_content(raw))


def _safe_id(value: Any) -> str:
    text = str(value).strip() if value is not None else ""
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", text or uuid.uuid4().hex)


def _save_source_trace_list(data: Dict[str, Any]) -> str:
    out_dir = Path.cwd() / "miaoxiang"
    out_dir.mkdir(parents=True, exist_ok=True)
    article_id = _safe_id(data.get("articleId"))
    path = out_dir / "sourceTrace_{0}.json".format(article_id)
    path.write_text(
        json.dumps(data.get("sourceTraceList"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def _decode_attachments(data: Dict[str, Any], output_dir: Path) -> List[Dict[str, str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    article_id = _safe_id(data.get("articleId"))
    specs = (
        (("wordBase64",), "docx", "DOCX"),
        (("pdfBase64",), "pdf", "PDF"),
    )
    attachments: List[Dict[str, str]] = []
    for keys, extension, file_type in specs:
        encoded = next(
            (data.get(key).strip() for key in keys if isinstance(data.get(key), str) and data.get(key).strip()),
            "",
        )
        if not encoded:
            continue
        try:
            content = base64.b64decode(encoded, validate=True)
        except Exception:
            continue
        path = output_dir / f"{article_id}_{file_type.lower()}.{extension}"
        path.write_bytes(content)
        attachments.append({"type": file_type, "path": str(path)})
    return attachments


def _http_call(query: str, api_key: str) -> Dict[str, Any]:
    request = urllib_request.Request(
        REPORT_URL,
        data=json.dumps({"query": query, "needFullContent": True}, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "em_api_key": api_key,
        },
    )
    try:
        with urllib_request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        if exc.code in (401, 403):
            raise _AuthRevoked("HTTP {0}: {1}".format(exc.code, _error_message(body)))
        raise RuntimeError("Fund research API request failed: {0}".format(
            _error_message(body) or f"http status {exc.code}"
        ))
    except urllib_error.URLError as exc:
        raise RuntimeError("Fund research API request failed: {0}".format(exc.reason))
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError("Fund research API returned invalid JSON response.")
    if isinstance(parsed, dict):
        code, status = parsed.get("code"), parsed.get("status")
        if code in (401, "401", 403, "403") or status in (401, "401", 403, "403"):
            raise _AuthRevoked("business auth rejected: code={0}, status={1}".format(code, status))
        business_error = _business_error_message(parsed)
        if business_error:
            raise RuntimeError("Fund research API request failed: {0}".format(business_error))
        return parsed
    return {"data": parsed}


async def generate_fund_research_report(
    query: str,
    output_dir: Optional[Path] = None,
    save_to_file: bool = True,
) -> Dict[str, Any]:
    query = (query or "").strip()
    result: Dict[str, Any] = {
        "query": query,
        "title": "",
        "article_id": "",
        "share_url": "",
        "content": "",
        "data_markdown": "",
        "data_md_path": None,
        "source_trace_path": None,
        "attachments": [],
        "raw": None,
    }
    if not query:
        result["error"] = "query is empty"
        return result
    auth = ensure_auth()
    if auth["status"] == AUTH_NEED_USER:
        result.update(
            need_auth=True,
            authUrl=auth["auth_url"],
            apiKeyUrl=auth["api_key_url"],
            auth_message="Authorization is required; authorize and resend the original prompt.",
        )
        return result
    if auth["status"] == AUTH_ERROR:
        result["error"] = auth.get("message", "Authorization failed")
        return result
    fresh_key = auth.get("api_key") if auth.get("newly_obtained") else None
    if fresh_key:
        result.update(remember_api_key=True, api_key=fresh_key)
    api_key = fresh_key or _load_em_api_key()
    if not api_key:
        result["error"] = "EM_API_KEY was not available after authorization"
        return result
    try:
        raw = await asyncio.get_event_loop().run_in_executor(None, _http_call, query, api_key)
    except _AuthRevoked as exc:
        return _handle_auth_revoked(str(exc), result)
    except Exception as exc:
        result["error"] = str(exc)
        return result
    result["raw"] = raw
    result["content"] = _extract_content(raw)
    result["data_markdown"] = _extract_data_markdown(raw)
    data = raw.get("data") if isinstance(raw, dict) else None
    if isinstance(data, dict):
        result["title"] = data.get("title") if isinstance(data.get("title"), str) else ""
        article_id = data.get("articleId")
        result["article_id"] = str(article_id) if article_id is not None else ""
        result["share_url"] = data.get("shareUrl") if isinstance(data.get("shareUrl"), str) else ""
        result["source_trace_path"] = _save_source_trace_list(data)
        if save_to_file and _has_valid_report(raw):
            result["attachments"] = _decode_attachments(data, Path(output_dir or DEFAULT_OUTPUT_DIR))
        if save_to_file and result["data_markdown"]:
            out_dir = Path(output_dir or DEFAULT_OUTPUT_DIR)
            out_dir.mkdir(parents=True, exist_ok=True)
            data_md_path = out_dir / "{0}_data.md".format(_safe_id(data.get("articleId")))
            data_md_path.write_text(result["data_markdown"], encoding="utf-8")
            result["data_md_path"] = str(data_md_path)
    return result


def _print_credential(result: Dict[str, Any]) -> None:
    if result.get("remember_api_key"):
        print("remember_api_key: true")
        print("credential_name: EM_API_KEY")
        print("apiKey: {0}".format(result["api_key"]))
        print("agent_action: 将 apiKey 完整保存到平台私有跨会话存储，不得向用户展示或写入业务文件。")


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Generate a fund research report.")
    parser.add_argument("--query")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    query = (args.query or "").strip() or sys.stdin.read().strip()
    if not query:
        parser.print_help()
        raise SystemExit(1)

    async def main() -> None:
        result = await generate_fund_research_report(query, save_to_file=not args.no_save)
        _print_credential(result)
        if result.get("need_auth"):
            print("need_auth: true")
            print("authUrl: {0}".format(result.get("authUrl", "")))
            print("apiKeyUrl: {0}".format(result.get("apiKeyUrl", AUTH_API_KEY_URL_FALLBACK)))
            print(result.get("auth_message", "Authorize and resend the original prompt."))
            raise SystemExit(10)
        if result.get("error"):
            print("Error: {0}".format(result["error"]))
            raise SystemExit(2)
        if result.get("title"):
            print("Title: {0}".format(result["title"]))
        if result.get("share_url"):
            print("ShareUrl: {0}".format(result["share_url"]))
        for item in result["attachments"]:
            print("{0}: {1}".format(item["type"], item["path"]))
        if result.get("data_md_path"):
            print("Data saved: {0}".format(result["data_md_path"]))
        if result.get("source_trace_path"):
            print("source_trace_path: {0}".format(result["source_trace_path"]))
        print(result["content"])

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()


if __name__ == "__main__":
    run_cli()
