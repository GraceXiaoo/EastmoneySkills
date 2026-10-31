#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate one policy conference interpretation report via mx-saas-platform."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib import error as urllib_error
from urllib import request as urllib_request

DEFAULT_OUTPUT_SUBDIR = "reports"
TIMEOUT_SECONDS = 1200
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()
RESEARCH_URL = "https://ai-saas.eastmoney.com/proxy/app-robo-advisor-api/assistant/write/policy-comparison/research"

DEFAULT_FORM_CONFIG = [
    {"chineseName": "报告信源", "englishName": "informationTypeEnumList", "value": "资讯,公告,研报"},
    {"chineseName": "报告长度", "englishName": "reportLength", "value": "长篇（1800字）"},
    {"chineseName": "章节数量", "englishName": "subChapterSum", "value": "10"},
    {"chineseName": "写作风格", "englishName": "writingStyle", "value": "严谨"},
    {"chineseName": "语言", "englishName": "language", "value": "中文"},
    {"chineseName": "用户写作要求", "englishName": "writingRequirements", "value": "按照原始会议章节维度解读会议内容"},
    {"chineseName": "参考模板", "englishName": "reportOutline", "value": ""},
]

DEFAULT_OBJECTIVE = ["按照原始会议章节维度解读会议内容"]


def output_root(output_dir: str | None = None) -> Path:
    if output_dir:
        return Path(output_dir)
    value = os.environ.get("POLICY_COMPARISON_OUTPUT_DIR", "").strip()
    return Path(value) if value else Path.cwd() / "miaoxiang" / "policy-comparison"


def api_key() -> str:
    if not EM_API_KEY:
        raise RuntimeError("未配置 EM_API_KEY")
    return EM_API_KEY


def error_message(body: str) -> str:
    try:
        parsed = json.loads(body)
    except Exception:
        return (body or "")[:200]
    if isinstance(parsed, dict):
        for key in ("message", "msg", "error"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return (body or "")[:200]


def call_api(url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "em_api_key": api_key()},
    )
    try:
        with urllib_request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8", errors="replace")
    except urllib_error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        raise RuntimeError(error_message(text) or "HTTP {0}".format(exc.code))
    except urllib_error.URLError as exc:
        raise RuntimeError("政策会议报告接口请求失败: {0}".format(exc.reason))
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        raise RuntimeError("政策会议报告接口返回了无法解析的响应")
    if not isinstance(result, dict):
        raise RuntimeError("政策会议报告接口返回格式异常")
    return result


def extract_data(raw: Dict[str, Any], fallback: str) -> Dict[str, Any]:
    code, status = raw.get("code"), raw.get("status")
    data = raw.get("data")
    if code not in (None, 0, 200) or status not in (None, 0, 200) or not isinstance(data, dict):
        raise RuntimeError(str(raw.get("message") or fallback))
    return data


def save_base64(value: Any, path: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        path.write_bytes(base64.b64decode(value.strip(), validate=True))
    except Exception as exc:
        raise RuntimeError("附件解码失败: {0}".format(exc))
    return str(path.resolve())


def generate_policy_document(
    conference_name: str,
    output_dir: str,
    *,
    form_config: List[dict] | None = None,
    objective: List[str] | None = None,
    save_to_file: bool = True,
    debug: bool = False,
    **_: Any,
) -> dict[str, Any]:
    query = (conference_name or "").strip()
    if not query:
        return {"success": False, "message": "请提供会议名称或政策主题"}

    run_dir = output_root(output_dir)
    attachment_dir = run_dir / "attachments"
    attachment_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw = call_api(RESEARCH_URL, {
            "query": query,
            "userFormConfigList": form_config or DEFAULT_FORM_CONFIG,
            "userObjectiveList": objective or DEFAULT_OBJECTIVE,
        })
        data = extract_data(raw, "政策会议正文生成失败")
        word_base64 = data.get("wordBase64")
        if not isinstance(word_base64, str) or not word_base64.strip():
            raise RuntimeError(str(raw.get("message") or "政策会议正文生成失败"))
        article_id = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(data.get("articleId") or "policy_comparison"))
        word_path = ""
        if save_to_file:
            word_path = save_base64(word_base64, attachment_dir / (article_id + ".docx"))
        if debug:
            (run_dir / "response.json").write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "success": True,
            "file_path": word_path,
            "title": str(data.get("title") or ""),
            "article_id": str(data.get("articleId") or ""),
        }
    except Exception as exc:
        return {"success": False, "message": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate policy conference Word report")
    parser.add_argument("--conference", required=True, help="Conference name, e.g. 2025年中央经济工作会议")
    parser.add_argument("--output-dir", required=True, help="Output directory for docx")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    result = generate_policy_document(
        conference_name=args.conference,
        output_dir=args.output_dir,
        save_to_file=not args.no_save,
        debug=args.debug,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
