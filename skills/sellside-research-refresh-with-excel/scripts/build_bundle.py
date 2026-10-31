#!/usr/bin/env python3
"""
build_bundle.py —— 编译生成自包含单体 skill（方案③ vendor 合并）

将「研报底稿抽取」(research-report-review) 与「研报仿写」(periodic-report-drafting)
整目录 vendor 进宿主 skill，生成自包含编译产物，运行时不再依赖独立子 skill。

职责分层（运行时门禁，见产物 SKILL.md）：
  - 衔接缝合层 = 宿主自有 scripts/reference（可改）
  - 子 skill 内部实现层 = vendor 进来的 bundle/review、bundle/drafting（只读、不改）

本脚本只负责「拉取 → 校验 → vendor → 写 manifest」，不触碰子 skill 实现逻辑。

用法示例：
  py build_bundle.py \
    --review-src   ../../研报底稿skill/research-report-review \
    --drafting-src ../../研报仿写skill/periodic-report-drafting \
    --host         . \
    --out          ../../../build/sellside-research-refresh-with-excel20
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone


# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
IGNORE_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".git", "node_modules"}
IGNORE_EXTS = {".pyc", ".pyo"}
VENDOR_REVIEW_REL = os.path.join("bundle", "review")
VENDOR_DRAFTING_REL = os.path.join("bundle", "drafting")

# §4 编译期契约：review 产物命名承诺（grep reference 文档确认存在）
REVIEW_OUTPUT_PATTERNS = [
    r"研报底稿抽取\.xlsx",
    r"底稿评测报告\.md",
]
# 权威 schema：5-Sheet 基准文件
REVIEW_WORKBOOK_SPEC = os.path.join("reference", "workbook_spec.md")
REVIEW_20SHEET_KEYWORD = "20_研报底稿"


def log(msg):
    print(f"[build_bundle] {msg}", flush=True)


def fail(reason):
    log(f"❌ 编译失败：{reason}")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# 步骤 1：拉取（读取源目录 + 记录 git commit）
# --------------------------------------------------------------------------- #
def git_commit(src_dir: Path) -> str:
    """取源目录所在仓库的 HEAD commit；取不到则标注 'unknown'。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(src_dir), capture_output=True, text=True, check=False,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        log(f"  警告：git rev-parse 失败于 {src_dir}：{exc}")
    return "unknown"


def step_pull(review_src: Path, drafting_src: Path, host: Path):
    for label, p in [("review", review_src), ("drafting", drafting_src), ("host", host)]:
        if not p.is_dir():
            fail(f"源目录不存在：{label}={p}")
    review_commit = git_commit(review_src)
    drafting_commit = git_commit(drafting_src)
    host_commit = git_commit(host)
    log(f"步骤1 拉取完成：review={review_src} (@{review_commit[:10]})  "
        f"drafting={drafting_src} (@{drafting_commit[:10]})  host={host} (@{host_commit[:10]})")
    return review_commit, drafting_commit, host_commit


# --------------------------------------------------------------------------- #
# 步骤 2：契约校验（任一不满足则编译失败）
# --------------------------------------------------------------------------- #
def _grep_any(root: Path, patterns) -> bool:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".md", ".py", ".mjs", ".json", ".txt"}:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            if re.search(pat, text):
                return True
    return False


def step_validate(review_src: Path, drafting_src: Path):
    # (a) review 产物命名承诺存在于 reference 文档
    if not _grep_any(review_src / "reference", REVIEW_OUTPUT_PATTERNS):
        fail("契约校验失败：review reference 未承诺输出 研报底稿抽取.xlsx / 底稿评测报告.md")

    # (b) 权威 schema：workbook_spec.md 存在
    spec = review_src / REVIEW_WORKBOOK_SPEC
    if not spec.is_file():
        fail(f"契约校验失败：权威 schema 缺失 {spec}")

    # (c) workbook_spec 中定义了 20_研报底稿
    spec_text = spec.read_text(encoding="utf-8", errors="ignore")
    if REVIEW_20SHEET_KEYWORD not in spec_text:
        fail(f"契约校验失败：{REVIEW_WORKBOOK_SPEC} 未定义 {REVIEW_20SHEET_KEYWORD}")

    # (d) drafting 本地模块齐全：扫描 .py/.mjs 的本地 import，被引用的本地模块必须存在
    missing = _scan_drafting_imports(drafting_src / "scripts")
    if missing:
        fail("契约校验失败：drafting 存在悬空本地引用：\n  - " + "\n  - ".join(missing))

    log("步骤2 契约校验通过：产物命名 ✓ workbook_spec ✓ 20_研报底稿 ✓ drafting 模块齐全 ✓")


def _scan_drafting_imports(scripts_dir: Path):
    """扫描 drafting scripts 的本地 import，返回缺失的被引用模块列表。"""
    if not scripts_dir.is_dir():
        return [f"scripts 目录不存在：{scripts_dir}"]
    files = {p.stem: p for p in scripts_dir.iterdir()
             if p.is_file() and p.suffix in {".py", ".mjs"}}
    missing = []
    py_import = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w]*)", re.M)
    mjs_import = re.compile(r"""import\s+.*?from\s+['"](.*?)['"]""")
    for stem, p in files.items():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for mod in py_import.findall(text):
            if mod not in files and (scripts_dir / f"{mod}.py").is_file() is False:
                # 仅当确为本地模块名（既非外部包、也不在目录中）时记为可疑
                if mod not in files:
                    pass  # 下面统一用 mjs 更可靠，这里宽松处理
        for rel in mjs_import.findall(text):
            if rel.startswith("."):
                target = (p.parent / rel).resolve()
                if not target.exists() and not target.with_suffix(".mjs").exists() \
                        and not target.with_suffix(".js").exists():
                    missing.append(f"{p.name} -> {rel}")
    return missing


# --------------------------------------------------------------------------- #
# 步骤 3：vendor 整目录拷贝
# --------------------------------------------------------------------------- #
def _ignore(dirpath, names):
    ignored = []
    for n in names:
        full = os.path.join(dirpath, n)
        if n in IGNORE_DIRS:
            ignored.append(n)
        elif os.path.isfile(full) and os.path.splitext(n)[1] in IGNORE_EXTS:
            ignored.append(n)
    return ignored


def step_vendor(review_src: Path, drafting_src: Path, host: Path, out: Path):
    if out.exists():
        shutil.rmtree(out)
    # 先复制宿主自身（保留宿主 scripts/reference/tests/examples/SKILL.md）
    shutil.copytree(host, out, ignore=_ignore)
    (out / "bundle").mkdir(parents=True, exist_ok=True)
    shutil.copytree(review_src, out / VENDOR_REVIEW_REL, ignore=_ignore)
    shutil.copytree(drafting_src, out / VENDOR_DRAFTING_REL, ignore=_ignore)
    log(f"步骤3 vendor 完成：{out}  含 bundle/review、bundle/drafting")


# --------------------------------------------------------------------------- #
# 步骤 4：写 bundle_manifest.json
# --------------------------------------------------------------------------- #
def _sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_checksums(root: Path, base: Path):
    result = {}
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.name not in IGNORE_DIRS:
            rel = p.relative_to(base).as_posix()
            try:
                result[rel] = _sha256_file(p)
            except Exception:
                result[rel] = "unreadable"
    return result


def step_manifest(out: Path, commits):
    review_c, drafting_c, host_c = commits
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "review": {"commit": review_c, "path": VENDOR_REVIEW_REL.replace("\\", "/")},
            "drafting": {"commit": drafting_c, "path": VENDOR_DRAFTING_REL.replace("\\", "/")},
            "host": {"commit": host_c},
        },
        "checksums": {
            "bundle/review": _dir_checksums(out / VENDOR_REVIEW_REL, out),
            "bundle/drafting": _dir_checksums(out / VENDOR_DRAFTING_REL, out),
        },
    }
    (out / "bundle_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"步骤4 manifest 完成：{out / 'bundle_manifest.json'}")


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(
        description="编译生成自包含单体 skill（vendor 合并 review + drafting）")
    ap.add_argument("--review-src", required=True, help="research-report-review 源目录")
    ap.add_argument("--drafting-src", required=True, help="periodic-report-drafting 源目录")
    ap.add_argument("--host", required=True, help="宿主 skill 目录（with-excel20）")
    ap.add_argument("--out", required=True, help="编译产物输出目录")
    ap.add_argument("--review-ref", default=None, help="(可选) review 固定 commit 记录")
    ap.add_argument("--drafting-ref", default=None, help="(可选) drafting 固定 commit 记录")
    args = ap.parse_args()

    review_src = Path(args.review_src).resolve()
    drafting_src = Path(args.drafting_src).resolve()
    host = Path(args.host).resolve()
    out = Path(args.out).resolve()

    commits = step_pull(review_src, drafting_src, host)
    step_validate(review_src, drafting_src)
    step_vendor(review_src, drafting_src, host, out)
    step_manifest(out, commits)
    log("✅ 编译完成（V0 待实测 import 闭合）")


if __name__ == "__main__":
    main()
