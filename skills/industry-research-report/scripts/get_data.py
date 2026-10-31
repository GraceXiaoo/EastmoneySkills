"""
行业研究报告生成脚本

功能：
- 根据用户输入的行业关键词，生成行业深度研究报告。
- 结果输出的行业研究报告内容：最终返回标题、正文、PDF/DOC附件、溯源信息。
"""

import asyncio
import json
import os
from pathlib import Path
import httpx
import base64
import argparse
import sys
import zipfile
import re
import uuid

_SCRIPTS_DIR = str(Path(__file__).resolve().parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from auth import AUTH_ERROR, AUTH_NEED_USER, ensure_auth

EM_BASE_URL = "https://ai-saas.eastmoney.com".rstrip("/")
EM_API_KEY_PLACEHOLDER = "{em" + "_api_key}"
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()

if EM_API_KEY and EM_API_KEY != EM_API_KEY_PLACEHOLDER:
    os.environ.setdefault("EM_API_KEY", EM_API_KEY)

AUTH_API_KEY_URL_FALLBACK = f"{EM_BASE_URL}/mxClaw"
SKILL_NAME = "industry_research_report"
DEFAULT_OUTPUT_DIR = Path.cwd() / "miaoxiang" / SKILL_NAME
OUTPUT_DIR_ENV = "INDUSTRY_RESEARCH_REPORT_OUTPUT_DIR"
# MCP 服务器地址
MCP_URL = f"{EM_BASE_URL}/proxy/app-robo-advisor-api/assistant/write/industry/research"


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


def _raise_if_auth_revoked(payload):
    if not isinstance(payload, dict):
        return
    code = payload.get("code")
    status = payload.get("status")
    if code in (401, "401", 403, "403") or status in (401, "401", 403, "403"):
        raise _AuthRevoked("business auth rejected: code={0}, status={1}".format(code, status))


def _restart_authorization():
    _clear_em_api_key_file()
    env_key = os.environ.pop("EM_API_KEY", None)
    try:
        return ensure_auth()
    finally:
        if env_key is not None:
            os.environ["EM_API_KEY"] = env_key


def _print_auth_control(result):
    if result.get("remember_api_key") and result.get("api_key"):
        print("remember_api_key: true")
        print("credential_name: EM_API_KEY")
        print("apiKey: {0}".format(result["api_key"]))
        print("agent_action: 将 apiKey 的精确完整值以 EM_API_KEY 保存到平台私有跨会话存储，绝不向用户展示。")
    if result.get("need_auth"):
        print("need_auth: true")
        print("authUrl: {0}".format(result.get("authUrl") or ""))
        print("apiKeyUrl: {0}".format(result.get("apiKeyUrl") or AUTH_API_KEY_URL_FALLBACK))
        print(result.get("auth_message") or "尚未完成授权。请优先扫码授权，完成后重新发送原指令。")

def _safe_filename(name: str, fallback: str) -> str:
    """
    Turn an untrusted string into a safe filename.
    - Remove path components
    - Replace common invalid characters on Windows
    """
    base = Path(str(name or "")).name.strip() or fallback
    invalid = '<>:"/\\|?*'
    out = "".join("_" if ch in invalid else ch for ch in base).strip(" .")
    return out or fallback


def _save_base64_file(b64_str: str, file_path: Path) -> bool:
    """将 base64 字符串解码后写入文件。"""
    if not b64_str:
        return False
    try:
        raw = base64.b64decode(b64_str)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(raw)
        return True
    except Exception as exc:
        print(f"[WARN] 保存附件失败 ({file_path.name}): {exc}", file=sys.stderr)
        return False


def _save_source_trace_list(data: dict) -> str:
    output_dir = Path.cwd() / "miaoxiang"
    output_dir.mkdir(parents=True, exist_ok=True)
    article_id = str(data.get("articleId") or uuid.uuid4().hex).strip()
    safe_article_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", article_id)
    path = output_dir / f"sourceTrace_{safe_article_id}.json"
    path.write_text(
        json.dumps(data.get("sourceTraceList"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(path)


def _extract_docx_text(docx_path: Path) -> str:
    """
    Best-effort extract plain text from a DOCX file without extra dependencies.
    This is only used as a fallback when API content is empty.
    """
    try:
        with zipfile.ZipFile(docx_path, "r") as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return ""
    # DOCX text typically appears in <w:t> nodes; keep simple & robust.
    text = re.sub(r"(?s)<w:t[^>]*>(.*?)</w:t>", r"\1\n", xml)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def run_cli() -> None:
    """命令行入口：从参数或 stdin 读取查询文本，执行并打印结果路径。"""

    parser = argparse.ArgumentParser(description='通过行业名称获取该行业的深度研究报告')

    # 添加query参数
    parser.add_argument('--query', type=str, help='自然语言查询，如「股价大于1000元的股票」', required=True)

    args = parser.parse_args()

    if not args.query.strip():
        print("用法: python3 scripts/get_data.py --query \"行业名称\"", file=sys.stderr)
        print("示例: 半导体 / 新能源汽车 / AI芯片 / 消费电子与智能家居", file=sys.stderr)
        sys.exit(1)

    async def _main() -> None:
        output_dir_env = os.environ.get(OUTPUT_DIR_ENV, "").strip()
        output_dir = Path(output_dir_env) if output_dir_env else DEFAULT_OUTPUT_DIR
        r = await get_industry_research_report(args.query, output_dir=output_dir)
        _print_auth_control(r)
        if r.get("need_auth"):
            sys.exit(10)
        if "error" in r:
            print(f"错误: {r['error']}", file=sys.stderr)
            sys.exit(2)

        # stdout must be a single JSON object for the skill contract
        r.pop("remember_api_key", None)
        r.pop("api_key", None)
        print(json.dumps(r, ensure_ascii=False))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(_main())
    finally:
        loop.close()


async def get_industry_research_report(query: str, output_dir: Path):
    """行业研究报告 异步调用函数"""

    result_data = {}

    if not isinstance(query, str) or len(query) > 500:
        result_data["error"] = "字数超出限制，请尝试其它主体。"
        return result_data

    auth = ensure_auth()
    if auth.get("status") == AUTH_NEED_USER:
        return {
            "need_auth": True,
            "authUrl": auth.get("auth_url"),
            "apiKeyUrl": auth.get("api_key_url") or AUTH_API_KEY_URL_FALLBACK,
            "auth_message": "尚未完成授权。请优先扫码授权，完成后重新发送原指令。",
        }
    if auth.get("status") == AUTH_ERROR:
        return {"error": auth.get("message", "授权流程出错")}

    newly_obtained_key = auth.get("api_key") if auth.get("newly_obtained") else None
    api_key = newly_obtained_key or _load_em_api_key()
    if not api_key:
        return {"error": "EM_API_KEY 落盘异常，请重新执行或检查 ~/.mx-skills/em_api_key"}
    if newly_obtained_key:
        result_data["remember_api_key"] = True
        result_data["api_key"] = newly_obtained_key

    try:
        async with httpx.AsyncClient(timeout=1200.0) as client:
            result = await client.post(
                MCP_URL,
                json={"query": query, "needFullContent": True},
                headers={
                    "Content-Type": "application/json",
                    "em_api_key": api_key,
                },
            )

            if result.status_code in (401, 403):
                raise _AuthRevoked("HTTP {0}".format(result.status_code))
            result.raise_for_status()
            
            result_data_api = result.json()
            _raise_if_auth_revoked(result_data_api)
            
            title = result_data_api["data"]["title"]
            content = result_data_api["data"].get("content") if isinstance(result_data_api.get("data"), dict) else ""
            content = content if isinstance(content, str) else ""
            share_url = result_data_api["data"]["shareUrl"]
            result_data["source_trace_path"] = _save_source_trace_list(
                result_data_api["data"]
            )

            safe_base = _safe_filename(title, "industry_research_report")
            
            pdf_output_path = output_dir / f"{safe_base}.pdf"
            pdf_saved = _save_base64_file(result_data_api["data"]["pdfBase64"], pdf_output_path)

            word_output_path = output_dir / f"{safe_base}.docx"
            word_saved  = _save_base64_file(result_data_api["data"]["wordBase64"], word_output_path)

            if not word_saved or not pdf_saved:
                result_data["error"] = "保存附件失败"
                return result_data

            result_data["title"] = title
            truncated_text = content.strip()
            # Fallback: if API returns empty content, try extracting from DOCX
            if not truncated_text and word_saved and word_output_path.is_file():
                truncated_text = _extract_docx_text(word_output_path)
            result_data["truncated_text"] = truncated_text
            result_data["pdf_output_path"] = str(pdf_output_path)
            result_data["docx_output_path"] = str(word_output_path)
            result_data["share_url"] = share_url

            return result_data

    except _AuthRevoked as exc:
        reauth = _restart_authorization()
        if reauth.get("status") == AUTH_NEED_USER:
            message = "EM_API_KEY 已失效（{0}），已清理保存的 key。请扫码重新授权。".format(exc)
            if os.environ.get("EM_API_KEY", "").strip():
                message += " 环境变量 EM_API_KEY 仍含有失效 key，请先清除该环境变量。"
            return {
                "need_auth": True,
                "authUrl": reauth.get("auth_url"),
                "apiKeyUrl": reauth.get("api_key_url") or AUTH_API_KEY_URL_FALLBACK,
                "auth_message": message,
            }
        return {"error": "EM_API_KEY 失效后重新授权失败: {0}".format(reauth.get("message", "未知错误"))}
    except Exception as e:
        print(f"调用工具时出错: {e}", file=sys.stderr)
        result_data["error"] = f"调用工具时出错: {e}"
        import traceback
        traceback.print_exc()
        return result_data


if __name__ == "__main__":
    run_cli()
