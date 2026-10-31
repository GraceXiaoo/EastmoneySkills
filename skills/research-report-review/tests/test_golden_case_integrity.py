"""金标准案例清单完整性回归（§17 回归，关联 §22-2 R28）。

缺陷背景：`golden_case_manager.verify_case` 此前用二进制读取计算清单指纹，而清单
是在 LF 检出下登记的；Windows 的 `core.autocrlf=true` 会把文本文件转成 CRLF，
于是 `mql_scripts.md` 的 sha256 与 size 双双失配 → `verify` FAIL、`match` 的
`can_export_golden` 变 false，SKILL.md 的「金标准精确命中可快速演示」路径被锁死。

本模块的合成夹具（第 2–4 例）均为进程内生成、不调用外部服务；第 1 例校验仓库内
真实案例清单，用于防止清单与实际文件再次漂移。
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import golden_case_manager  # noqa: E402

CASE_DIR = ROOT / "examples" / "golden-cases" / "weekly-global-macro-20260913"


class GoldenCaseIntegrityTests(unittest.TestCase):
    def test_bundled_golden_case_passes_verification(self):
        # 真实清单：文本指纹必须与文件一致，且与检出时的行尾设置无关。
        manifest = json.loads((CASE_DIR / "manifest.json").read_text("utf-8"))
        result = golden_case_manager.verify_case(CASE_DIR, manifest)
        self.assertEqual(result["status"], "PASS", result["errors"])

    def test_text_fingerprint_is_stable_across_line_endings(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            lf_path = directory / "lf.md"
            lf_path.write_bytes("a\nb\nc\n".encode("utf-8"))
            crlf_path = directory / "crlf.md"
            crlf_path.write_bytes("a\r\nb\r\nc\r\n".encode("utf-8"))
            self.assertEqual(
                golden_case_manager.file_digest(lf_path),
                golden_case_manager.file_digest(crlf_path),
            )

    def test_binary_fingerprint_keeps_raw_bytes(self):
        # 反向对照：二进制文件不得被归一化，否则 xlsx / pdf 会误判为同形。
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            first = directory / "blob.xlsx"
            first.write_bytes(b"PK\x03\x04\r\n\x00padding\r\n")
            second = directory / "same.xlsx"
            second.write_bytes(b"PK\x03\x04\n\x00padding\n")
            self.assertNotEqual(
                golden_case_manager.file_digest(first),
                golden_case_manager.file_digest(second),
            )

    def test_fingerprint_registered_from_raw_bytes_is_rejected(self):
        # 反向对照：清单口径必须是归一化后的指纹；按 CRLF 原始字节登记必须失败。
        with tempfile.TemporaryDirectory() as folder:
            case_dir = Path(folder) / "case"
            case_dir.mkdir()
            script = case_dir / "mql_scripts.md"
            raw = "a\r\nb\r\n".encode("utf-8")
            script.write_bytes(raw)
            manifest = {
                "case_id": "synthetic-case",
                "files": {
                    "mql_scripts.md": {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                    }
                },
            }
            result = golden_case_manager.verify_case(case_dir, manifest)
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("sha256 mismatch: mql_scripts.md", result["errors"])


if __name__ == "__main__":
    unittest.main()
