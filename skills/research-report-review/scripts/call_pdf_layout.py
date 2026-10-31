#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PDF layout parsing caller script for research-report-review Skill (self-contained).

This script is internalized into research-report-review so the Skill can call
the pdf/layoutV2 interface directly without depending on any external PDF
parsing Skill at runtime. Endpoint mapping, curl invocation, merged JSON
output, raw response preservation, and the docInfo / layoutAnalysis /
imageBlocks three-section schema are all retained from the original source.

Usage:
    python call_pdf_layout.py --pdf <PDF abs path> --out-dir <output dir> [options]

Options:
    --timeout    curl timeout seconds (default 120)
    --stem        output filename prefix (default: PDF filename without .pdf)

Outputs in --out-dir:
    <stem>-PDF版面解析最终结果.json   merged structured result
    <stem>-PDF版面解析最终结果.md     readable markdown
    <stem>-版面解析原始响应.json      raw API response (preserved)

Exit codes:
    0 = PASS
    2 = BLOCKED (network/HTTP/JSON/biz code failure)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime

# Build placeholders are replaced automatically for the current environment.
# Keep these assignments verbatim so the package can target test or production.
EM_BASE_URL_PLACEHOLDER = "{em" + "_base_url}"
EM_BASE_URL = os.environ.get("EM_BASE_URL", "https://ai-saas.eastmoney.com").strip().rstrip("/")
EM_API_KEY_PLACEHOLDER = "{em" + "_api_key}"
EM_API_KEY = os.environ.get("EM_API_KEY", "").strip()

# Do not hard-code a test or production hostname and do not silently fall back
# to unrelated internal services.
ENDPOINTS = {
    'current-env': (
        EM_BASE_URL,
        False,
        None,
        True,
    )
}

# Datetime format (defined as constant to avoid quote-escaping issues in source)
DT_FMT = '%Y-%m-%d %H:%M:%S'


def resolve_base_url():
    """Return the build-injected gateway root for the current environment."""
    if not EM_BASE_URL or EM_BASE_URL == EM_BASE_URL_PLACEHOLDER:
        raise ValueError(
            '基础地址尚未注入：请先将构建占位符 https://ai-saas.eastmoney.com 替换为当前环境接口网关地址')
    return EM_BASE_URL


def resolve_api_key():
    """Read the only supported credential source without leaking its value."""
    value = EM_API_KEY
    if not value or value == EM_API_KEY_PLACEHOLDER:
        raise ValueError(
            '缺少有效 EM_API_KEY 环境变量；未注入值或 <EM_API_KEY> 占位符不能发送')
    if '\r' in value or '\n' in value:
        raise ValueError('EM_API_KEY 含非法换行符')
    return value


def build_curl_cmd(pdf_path, out_raw_path, endpoint, timeout, api_key):
    _, need_resolve, resolve_str, need_api_key = ENDPOINTS[endpoint]
    base_url = resolve_base_url()
    url = f"{base_url}/proxy/pdf/layoutV2"
    curl = shutil.which('curl') or shutil.which('curl.exe')
    if not curl:
        raise RuntimeError('curl executable not found')
    cmd = [
        curl,
        '-s', '-L',
        '--max-time', str(timeout),
        '-X', 'POST', url,
        '-F', 'srcFile=@' + pdf_path,
        '-F', 'source=2',
        '-o', out_raw_path,
        '-w', 'HTTP_CODE:%{http_code}\nTIME:%{time_total}\nSIZE:%{size_download}',
    ]
    if need_api_key and api_key:
        # Insert -H "em_api_key: <key>" right after URL
        idx = cmd.index('-X', 4) if '-X' in cmd[4:] else len(cmd)
        cmd.insert(idx, '-H')
        cmd.insert(idx + 1, 'em_api_key: ' + api_key)
    return cmd, url, None


def parse_curl_writeln(writeln_text):
    info = {'httpCode': 0, 'elapsedSec': 0.0, 'responseBytes': 0}
    for line in (writeln_text or '').splitlines():
        line = line.strip()
        if line.startswith('HTTP_CODE:'):
            try:
                info['httpCode'] = int(line.split(':', 1)[1].strip() or '0')
            except ValueError:
                info['httpCode'] = 0
        elif line.startswith('TIME:'):
            try:
                info['elapsedSec'] = round(float(line.split(':', 1)[1].strip() or '0'), 3)
            except ValueError:
                info['elapsedSec'] = 0.0
        elif line.startswith('SIZE:'):
            try:
                info['responseBytes'] = int(line.split(':', 1)[1].strip() or '0')
            except ValueError:
                info['responseBytes'] = 0
    return info


def build_merged_output(pdf_path, pdf_basename, base_url, resolve_str,
                        call_info, raw_json_path, stem_override=None):
    extracted_at = datetime.now().strftime(DT_FMT)
    stem = stem_override or os.path.splitext(pdf_basename)[0]

    base = {
        'extractedAt': extracted_at,
        'sourcePdf': pdf_basename,
        'sourcePdfPath': pdf_path,
        'apiEndpoint': base_url,
        'responseFile': os.path.basename(raw_json_path) if raw_json_path else None,
        'callInfo': {
            'httpCode': call_info.get('httpCode', 0),
            'elapsedSec': call_info.get('elapsedSec', 0.0),
            'responseBytes': call_info.get('responseBytes', 0),
            'curlResolve': resolve_str,
            'failureStage': call_info.get('failureStage'),
            'errorMessage': call_info.get('errorMessage'),
        },
        'docInfo': {},
        'layoutAnalysis': {'totalBlocks': 0, 'classTypeSummary': {},
                           'blocksByPage': {}, 'pageContent': {}},
        'imageBlocks': [],
    }

    # Read raw response
    raw = None
    if raw_json_path and os.path.exists(raw_json_path) and os.path.getsize(raw_json_path) > 0:
        try:
            with open(raw_json_path, 'r', encoding='utf-8') as fp:
                raw = json.load(fp)
        except json.JSONDecodeError as e:
            base['callInfo']['failureStage'] = 'JSON_PARSE_ERROR'
            base['callInfo']['errorMessage'] = 'JSON parse error: ' + str(e)[:300]
            return base, stem, None

    if raw is None:
        if not base['callInfo']['failureStage']:
            base['callInfo']['failureStage'] = 'EMPTY_RESPONSE'
            base['callInfo']['errorMessage'] = 'Empty response body'
        return base, stem, None

    code = raw.get('code')
    status = raw.get('status')
    message = raw.get('message')
    if call_info.get('httpCode') in (401, 403) or code in (401, 403):
        base['callInfo']['failureStage'] = 'AUTH_INVALID'
        base['callInfo']['errorMessage'] = (
            'layoutV2 拒绝当前进程中的 EM_API_KEY（HTTP/业务码 401 或 403）；'
            '请重新注入有效 Key 后再恢复该服务')
        return base, stem, raw
    if not (code == 200 or status == 0):
        base['callInfo']['failureStage'] = 'BIZ_ERROR'
        base['callInfo']['errorMessage'] = 'code=' + str(code) + ' status=' + str(status) + ' message=' + str(message)
        return base, stem, raw

    data = raw.get('data') or {}
    base['docInfo'] = {
        'docId': data.get('docId'),
        'orgName': data.get('orgName'),
        'md5': data.get('md5'),
        'docSize': data.get('docSize'),
        'page': data.get('page'),
        'previewUrl': data.get('previewUrl'),
        'parseSecurityStatus': data.get('parseSecurityStatus'),
    }

    tb = data.get('textBlocks') or []
    pc = data.get('pageContent') or {}
    img_blocks = [b for b in tb if b.get('classType') == 'image']

    pages_set = sorted({b.get('page') for b in tb if b.get('page') is not None})
    blocks_by_page = {}
    for page in pages_set:
        blocks_by_page[str(page)] = [
            {
                'index': b.get('index'),
                'classType': b.get('classType'),
                'minX': b.get('minX'), 'maxX': b.get('maxX'),
                'minY': b.get('minY'), 'maxY': b.get('maxY'),
                'content': b.get('content'),
                'tableContent': b.get('tableContent'),
                'contentPreview': (b.get('content') or '')[:120],
            }
            for b in tb if b.get('page') == page
        ]

    base['layoutAnalysis'] = {
        'totalBlocks': len(tb),
        'classTypeSummary': dict(Counter(b.get('classType') for b in tb)),
        'blocksByPage': blocks_by_page,
        'pageContent': pc,
    }

    base['imageBlocks'] = [
        {
            'page': b.get('page'),
            'index': b.get('index'),
            'classType': b.get('classType'),
            'minX': b.get('minX'), 'maxX': b.get('maxX'),
            'minY': b.get('minY'), 'maxY': b.get('maxY'),
            'width': round(b.get('maxX', 0) - b.get('minX', 0), 2)
                     if b.get('maxX') is not None and b.get('minX') is not None else None,
            'height': round(b.get('maxY', 0) - b.get('minY', 0), 2)
                      if b.get('maxY') is not None and b.get('minY') is not None else None,
            'imageUrl': b.get('imageUrl'),
            'content': b.get('content'),
        }
        for b in img_blocks
    ]

    return base, stem, raw


def render_markdown(merged, stem):
    lines = []
    ci = merged['callInfo']
    di = merged['docInfo']
    la = merged['layoutAnalysis']
    ib = merged['imageBlocks']

    lines.append('# ' + stem + ' - PDF版面解析最终结果')
    lines.append('')
    lines.append('## 一、调用与文档信息')
    lines.append('')
    lines.append('| 字段 | 值 |')
    lines.append('|---|---|')
    lines.append('| 提取时间 | ' + merged['extractedAt'] + ' |')
    lines.append('| 源PDF | ' + merged['sourcePdf'] + ' |')
    lines.append('| 源PDF路径 | ' + merged['sourcePdfPath'] + ' |')
    lines.append('| 接口地址(apiEndpoint) | ' + merged['apiEndpoint'] + ' |')
    lines.append('| curl --resolve | `' + str(ci.get('curlResolve')) + '` |')
    lines.append('| HTTP状态码 | ' + str(ci.get('httpCode')) + ' |')
    lines.append('| 耗时(秒) | ' + str(ci.get('elapsedSec')) + ' |')
    lines.append('| 响应字节 | ' + str(ci.get('responseBytes')) + ' |')
    if ci.get('failureStage'):
        lines.append('| **failureStage** | **' + str(ci.get('failureStage')) + '** |')
        lines.append('| **errorMessage** | ' + str(ci.get('errorMessage')) + ' |')
    lines.append('| 原始响应文件 | ' + str(merged['responseFile']) + ' |')
    if di:
        lines.append('| docId | `' + str(di.get('docId')) + '` |')
        lines.append('| 原始文件名(orgName) | ' + str(di.get('orgName')) + ' |')
        lines.append('| MD5 | ' + str(di.get('md5')) + ' |')
        lines.append('| 文件大小(docSize) | ' + str(di.get('docSize')) + ' 字节 |')
        lines.append('| 总页数(page) | ' + str(di.get('page')) + ' |')
        lines.append('| parseSecurityStatus | ' + str(di.get('parseSecurityStatus')) + ' |')
        lines.append('| previewUrl | ' + str(di.get('previewUrl')) + ' |')
    lines.append('')

    if not la.get('totalBlocks'):
        lines.append('## 二、版面解析(layoutAnalysis)')
        lines.append('')
        lines.append('> 接口调用失败或响应为空,本段为空。详见一、中的 failureStage。')
        lines.append('')
        return '\n'.join(lines)

    lines.append('## 二、版面解析(layoutAnalysis)')
    lines.append('')
    lines.append('### 1. 块统计')
    lines.append('')
    lines.append('- textBlocks 总数: **' + str(la['totalBlocks']) + '**')
    lines.append('')
    lines.append('| classType | 数量 |')
    lines.append('|---|---|')
    for k, v in la['classTypeSummary'].items():
        lines.append('| ' + str(k) + ' | ' + str(v) + ' |')
    lines.append('')

    lines.append('### 2. 各页 block 概览(含坐标与 content 预览)')
    lines.append('')
    for page in sorted(la['blocksByPage'].keys(),
                       key=lambda x: int(x) if str(x).isdigit() else 0):
        blocks = la['blocksByPage'][page]
        lines.append('#### 第' + page + '页 (共' + str(len(blocks)) + '个 block)')
        lines.append('')
        lines.append('| index | classType | minX | maxX | minY | maxY | content预览 |')
        lines.append('|---|---|---|---|---|---|---|')
        for b in blocks:
            cp = (b.get('contentPreview') or '').replace('|', '\\|').replace('\n', ' ')
            lines.append('| ' + str(b.get('index')) + ' | ' + str(b.get('classType')) +
                         ' | ' + str(b.get('minX')) + ' | ' + str(b.get('maxX')) +
                         ' | ' + str(b.get('minY')) + ' | ' + str(b.get('maxY')) +
                         ' | ' + cp + ' |')
        lines.append('')

    lines.append('### 3. 各页文本内容(pageContent)')
    lines.append('')
    for page in sorted(la['pageContent'].keys(),
                       key=lambda x: int(x) if str(x).isdigit() else 0):
        lines.append('#### 第' + page + '页文本')
        lines.append('')
        lines.append('```')
        lines.append(la['pageContent'][page] or '')
        lines.append('```')
        lines.append('')

    lines.append('## 三、Image 块元信息(imageBlocks)')
    lines.append('')
    lines.append('共识别 **' + str(len(ib)) + '** 个 image 类型块'
                 '(接口未返回 imageUrl,仅提供坐标与周边识别文本)')
    lines.append('')
    for i, b in enumerate(ib, 1):
        lines.append('### 图' + str(i) + ': 第' + str(b.get('page')) + '页 index=' + str(b.get('index')))
        lines.append('')
        lines.append('| 字段 | 值 |')
        lines.append('|---|---|')
        lines.append('| page | ' + str(b.get('page')) + ' |')
        lines.append('| index | ' + str(b.get('index')) + ' |')
        lines.append('| classType | ' + str(b.get('classType')) + ' |')
        lines.append('| minX | ' + str(b.get('minX')) + ' |')
        lines.append('| maxX | ' + str(b.get('maxX')) + ' |')
        lines.append('| minY | ' + str(b.get('minY')) + ' |')
        lines.append('| maxY | ' + str(b.get('maxY')) + ' |')
        lines.append('| 宽度 | ' + str(b.get('width')) + ' |')
        lines.append('| 高度 | ' + str(b.get('height')) + ' |')
        lines.append('| imageUrl | `' + str(b.get('imageUrl')) + '` |')
        lines.append('')
        lines.append('**content(周边识别文本):**')
        lines.append('')
        lines.append('```')
        lines.append(b.get('content') or '')
        lines.append('```')
        lines.append('')

    return '\n'.join(lines)


def main():
    ap = argparse.ArgumentParser(description='PDF layout parsing caller for research-report-review')
    ap.add_argument('--pdf', required=True, help='Source PDF absolute path')
    ap.add_argument('--out-dir', required=True, help='Output directory absolute path')
    ap.add_argument('--endpoint', default='current-env',
                    choices=list(ENDPOINTS.keys()),
                    help='Build-injected current environment endpoint')
    ap.add_argument('--timeout', type=int, default=120, help='curl timeout seconds')
    ap.add_argument('--stem', default=None, help='Output filename prefix')
    args = ap.parse_args()

    pdf_path = os.path.abspath(args.pdf)
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    if not os.path.exists(pdf_path):
        print('ERROR: PDF not found: ' + pdf_path, file=sys.stderr)
        sys.exit(2)
    pdf_basename = os.path.basename(pdf_path)
    stem = args.stem or os.path.splitext(pdf_basename)[0]

    # Resolve api_key only from EM_API_KEY; never persist or print it.
    _, _, _, need_api_key = ENDPOINTS[args.endpoint]
    try:
        resolve_base_url()
        api_key = resolve_api_key() if need_api_key else ''
    except ValueError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(2)

    raw_path = os.path.join(out_dir, stem + '-版面解析原始响应.json')
    try:
        cmd, api_url, resolve_str = build_curl_cmd(
            pdf_path, raw_path, args.endpoint, args.timeout, api_key)
    except RuntimeError as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(2)

    print('[INFO] endpoint=' + args.endpoint + ' resolve=' + str(resolve_str))
    print('[INFO] url=' + api_url)
    print('[INFO] rawResponse=' + raw_path)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding='utf-8', timeout=args.timeout + 30)
    except subprocess.TimeoutExpired:
        print('ERROR: curl timed out after ' + str(args.timeout + 30) + 's', file=sys.stderr)
        sys.exit(2)

    writeln_text = result.stdout or ''
    call_info = parse_curl_writeln(writeln_text)
    print('[INFO] httpCode=' + str(call_info['httpCode']) +
          ' elapsedSec=' + str(call_info['elapsedSec']) +
          ' responseBytes=' + str(call_info['responseBytes']))

    if call_info['httpCode'] == 0:
        call_info['failureStage'] = 'NETWORK'
        call_info['errorMessage'] = 'curl timeout or connection refused'
    elif call_info['httpCode'] in (401, 403):
        call_info['failureStage'] = 'AUTH_INVALID'
        call_info['errorMessage'] = 'layoutV2 rejected EM_API_KEY with HTTP ' + str(call_info['httpCode'])
    elif call_info['httpCode'] != 200:
        call_info['failureStage'] = 'HTTP_ERROR'
        call_info['errorMessage'] = 'HTTP ' + str(call_info['httpCode'])

    merged, stem_out, raw = build_merged_output(
        pdf_path, pdf_basename, api_url, resolve_str,
        call_info, raw_path,
        stem_override=stem)

    merged_json_path = os.path.join(out_dir, stem_out + '-PDF版面解析最终结果.json')
    with open(merged_json_path, 'w', encoding='utf-8') as fp:
        json.dump(merged, fp, ensure_ascii=False, indent=2)

    md_text = render_markdown(merged, stem_out)
    md_path = os.path.join(out_dir, stem_out + '-PDF版面解析最终结果.md')
    with open(md_path, 'w', encoding='utf-8') as fp:
        fp.write(md_text)

    print('[INFO] mergedJson=' + merged_json_path)
    print('[INFO] mergedMd=' + md_path)

    if merged['callInfo'].get('failureStage'):
        print('[BLOCKED] failureStage=' + merged['callInfo']['failureStage'] +
              ' errorMessage=' + merged['callInfo']['errorMessage'],
              file=sys.stderr)
        sys.exit(2)

    print('[PASS] totalBlocks=' + str(merged['layoutAnalysis']['totalBlocks']) +
          ' imageBlocks=' + str(len(merged['imageBlocks'])) +
          ' pages=' + str(merged['docInfo'].get('page')))
    sys.exit(0)


if __name__ == '__main__':
    main()
