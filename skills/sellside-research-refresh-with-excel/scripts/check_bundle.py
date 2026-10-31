#!/usr/bin/env python3
"""首跑 bundle 自检（P1-5 发布硬条件）。

校验本 skill 是「已编译的自包含单体」：
  1. bundle/review、bundle/drafting、bundle_manifest.json 齐全；
  2. bundle/ 实际文件指纹与 bundle_manifest.json 的 checksums 全量一致；
  3. 三对齐：bundle_manifest 指纹可用 + 宿主 SKILL.md §4 文本存在
     + SKILL.md version == run_manifest.json target_version。

任何一项失败都以 BLOCKED 退出码 1 结束，并提示唯一的合规恢复路径：
改上游源目录后重跑 build_bundle.py 重新编译，禁止运行时现场重建 bundle。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

REQUIRED_DIRS = ("bundle/review", "bundle/drafting")
REQUIRED_SUB_SKILLS = ("bundle/review/SKILL.md", "bundle/drafting/SKILL.md")
SECTION4_MARKERS = ("## 4. 阶段 4", "--finalize-unrendered")
VERSION_LINE = re.compile(r'^version:\s*"?([^"\s]+)"?', re.MULTILINE)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _skill_md_version(skill_md: Path) -> str | None:
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None
    match = VERSION_LINE.search(text)
    return match.group(1) if match else None


def check_bundle(package_dir: Path) -> dict:
    failures: list[str] = []

    manifest_path = package_dir / "bundle_manifest.json"
    for rel in REQUIRED_DIRS:
        if not (package_dir / rel).is_dir():
            failures.append(f"missing directory: {rel}")
    for rel in REQUIRED_SUB_SKILLS:
        if not (package_dir / rel).is_file():
            failures.append(f"missing file: {rel}")
    if not manifest_path.is_file():
        failures.append("missing file: bundle_manifest.json")

    if manifest_path.is_file() and all(
        (package_dir / rel).is_dir() for rel in REQUIRED_DIRS
    ):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            failures.append(f"bundle_manifest.json unreadable: {exc}")
            manifest = None
        if isinstance(manifest, dict):
            recorded = manifest.get("checksums", {})
            for rel in REQUIRED_DIRS:
                expected = recorded.get(rel)
                if not isinstance(expected, dict):
                    failures.append(f"bundle_manifest.json lacks checksums[{rel!r}]")
                    continue
                root = package_dir / rel
                actual = {
                    p.relative_to(package_dir).as_posix(): _sha256_file(p)
                    for p in sorted(root.rglob("*"))
                    if p.is_file() and p.name != "bundle_manifest.json"
                }
                missing = sorted(set(expected) - set(actual))
                extra = sorted(set(actual) - set(expected))
                changed = sorted(
                    key for key in set(expected) & set(actual)
                    if expected[key] != actual[key]
                )
                if missing:
                    failures.append(f"{rel}: files missing vs manifest: {missing[:5]}")
                if extra:
                    failures.append(f"{rel}: files not in manifest: {extra[:5]}")
                if changed:
                    failures.append(f"{rel}: hash mismatch vs manifest: {changed[:5]}")

    skill_md = package_dir / "SKILL.md"
    try:
        skill_text = skill_md.read_text(encoding="utf-8")
        has_section4 = all(marker in skill_text for marker in SECTION4_MARKERS)
        if not has_section4:
            failures.append("SKILL.md lacks section-4 drafting pipeline markers")
    except OSError as exc:
        skill_text = ""
        failures.append(f"SKILL.md unreadable: {exc}")
    skill_version = _skill_md_version(skill_md)
    if not skill_version:
        failures.append("SKILL.md frontmatter lacks version")

    run_manifest_path = package_dir / "run_manifest.json"
    try:
        run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
        target_version = run_manifest.get("target_version")
    except (OSError, json.JSONDecodeError) as exc:
        target_version = None
        failures.append(f"run_manifest.json unreadable: {exc}")
    if skill_version and target_version and skill_version != target_version:
        failures.append(
            f"version mismatch: SKILL.md={skill_version} "
            f"run_manifest.target_version={target_version}"
        )

    status = "BLOCKED" if failures else "PASS"
    return {
        "status": status,
        "package_dir": str(package_dir.resolve()),
        "skill_version": skill_version,
        "failures": failures,
        "recovery": (
            "改上游源目录后重跑 scripts/build_bundle.py 重新编译 bundle，"
            "禁止运行时现场重建。"
        )
        if failures
        else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="首跑 bundle 自检")
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    result = check_bundle(args.package_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
