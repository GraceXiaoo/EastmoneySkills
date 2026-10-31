from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / "scripts"))

from check_bundle import check_bundle


SKILL_MD = """---
name: "fixture-skill"
version: "3.0.4"
description: "fixture"
---

## 4. 阶段 4：仿写新研报

```
node report_workflow.mjs workflow.json --finalize-unrendered "no browser"
```
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_package(root: Path) -> Path:
    """构造一个与 bundle_manifest.json 指纹一致的最小自包含单体。"""
    package = root / "package"
    for rel in ("bundle/review", "bundle/drafting"):
        (package / rel).mkdir(parents=True)
    files = {
        "bundle/review/SKILL.md": "review skill",
        "bundle/review/scripts/run.py": "print('review')",
        "bundle/drafting/SKILL.md": "drafting skill",
        "bundle/drafting/scripts/run.mjs": "console.log('drafting')",
    }
    for rel, content in files.items():
        target = package / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    checksums = {
        "bundle/review": {
            rel: sha256(package / rel) for rel in files if rel.startswith("bundle/review")
        },
        "bundle/drafting": {
            rel: sha256(package / rel)
            for rel in files
            if rel.startswith("bundle/drafting")
        },
    }
    (package / "bundle_manifest.json").write_text(
        json.dumps({"checksums": checksums}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (package / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (package / "run_manifest.json").write_text(
        json.dumps({"target_version": "3.0.4"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return package


class BundleCheckTests(unittest.TestCase):
    def test_passes_when_bundle_matches_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = make_package(Path(directory))
            result = check_bundle(package)
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["failures"], [])
            self.assertEqual(result["skill_version"], "3.0.4")

    def test_blocked_when_bundle_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = make_package(Path(directory))
            import shutil

            shutil.rmtree(package / "bundle")
            result = check_bundle(package)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(
                any("missing directory" in f for f in result["failures"])
            )
            self.assertIn("build_bundle.py", result["recovery"])

    def test_blocked_when_file_hash_mismatches_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = make_package(Path(directory))
            target = package / "bundle" / "drafting" / "scripts" / "run.mjs"
            target.write_text("console.log('tampered')", encoding="utf-8")
            result = check_bundle(package)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(
                any("hash mismatch" in f for f in result["failures"])
            )

    def test_blocked_when_version_sources_disagree(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = make_package(Path(directory))
            manifest = json.loads(
                (package / "run_manifest.json").read_text(encoding="utf-8")
            )
            manifest["target_version"] = "3.0.2"
            (package / "run_manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
            )
            result = check_bundle(package)
            self.assertEqual(result["status"], "BLOCKED")
            self.assertTrue(
                any("version mismatch" in f for f in result["failures"])
            )


if __name__ == "__main__":
    unittest.main()
