from __future__ import annotations

import base64
import copy
import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from verify_build import (
    BuildVerificationError,
    _verify_rendered_html,
    decrypt_payload,
    extract_index_payload,
    verify_build,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "full_data.json"
PASSWORD = "synthetic-test-password-密碼"


def load_fixture() -> dict:
    with FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def copy_programs(destination: Path, *names: str) -> None:
    for name in names:
        shutil.copy2(REPO_ROOT / name, destination / name)


def run_program(directory: Path, name: str, password: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["SITE_PASSWORD"] = password
    return subprocess.run(
        [sys.executable, name],
        cwd=directory,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class EncryptedBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.work = Path(cls.temporary.name)
        copy_programs(cls.work, "build.py", "decrypt.py", "validate_data.py")
        cls.fixture_data = load_fixture()
        write_json(cls.work / "data.json", cls.fixture_data)
        result = run_program(cls.work, "build.py", PASSWORD)
        if result.returncode != 0:
            cls.temporary.cleanup()
            raise AssertionError(f"synthetic build failed:\n{result.stdout}\n{result.stderr}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def setUp(self) -> None:
        write_json(self.work / "data.json", self.fixture_data)

    def test_envelopes_use_current_format_and_verify_against_plaintext(self) -> None:
        with (self.work / "data.enc").open(encoding="utf-8") as handle:
            data_payload = json.load(handle)
        index_payload = extract_index_payload((self.work / "index.html").read_text(encoding="utf-8"))

        for label, payload in (("data.enc", data_payload), ("index", index_payload)):
            with self.subTest(payload=label):
                self.assertEqual(300_000, payload["iter"])
                self.assertEqual(16, len(base64.b64decode(payload["salt"], validate=True)))
                self.assertEqual(12, len(base64.b64decode(payload["iv"], validate=True)))
                self.assertGreaterEqual(len(base64.b64decode(payload["ct"], validate=True)), 16)

        result = verify_build(
            PASSWORD,
            data_path=str(self.work / "data.json"),
            encrypted_data_path=str(self.work / "data.enc"),
            index_path=str(self.work / "index.html"),
        )
        self.assertEqual(64, len(result["data_sha256"]))
        self.assertEqual(64, len(result["rendered_sha256"]))
        self.assertNotIn("Synthetic 每日巡檢", (self.work / "index.html").read_text(encoding="utf-8"))

    def test_build_then_decrypt_is_a_lossless_round_trip(self) -> None:
        (self.work / "data.json").unlink()

        result = run_program(self.work, "decrypt.py", PASSWORD)

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        with (self.work / "data.json").open(encoding="utf-8") as handle:
            restored = json.load(handle)
        self.assertEqual(self.fixture_data, restored)
        self.assertIn("future_root_field", restored)

    def test_deep_dive_metrics_and_caveats_are_rendered(self) -> None:
        index_text = (self.work / "index.html").read_text(encoding="utf-8")
        payload = extract_index_payload(index_text)
        rendered = decrypt_payload(payload, PASSWORD, label="fixture index").decode(
            "utf-8"
        )

        for expected in (
            "2.17x",
            "以 650 億下限",
            "-40 億",
            "170 億/月",
            "≈90 億/月",
            "≈-53.3 億/月²",
            "二階導示意代理",
            "Claude Opus 5",
            "Claude Fable 5",
            "Grok 4.6",
            "Kimi K3",
            "GPT-5.6 Sol",
            "Claude Code",
            "OpenAI Codex",
            "-24.8%",
            "Anthropic 放緩不等於 AI 總需求放緩，支出可能轉往 GPU／推理託管／網路／儲存／運維。",
            "媒體報導",
            "第三方估算",
            "第三方樣本",
            "第三方評測",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, rendered)

    def test_section_update_history_remains_available_and_verified(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            copy_programs(work, "build.py", "validate_data.py")
            data = copy.deepcopy(self.fixture_data)
            events = [
                {
                    "date": "2026-10-20",
                    "cat": "模型",
                    "text": f"Archived event {number:02d} <&>",
                    "url": f"https://example.org/archive/{number}",
                    "source": "Official Feed",
                }
                for number in range(60)
            ]
            data.setdefault("section_updates", {})["analysis"] = events
            write_json(work / "data.json", data)
            result = run_program(work, "build.py", PASSWORD)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            verify_build(
                PASSWORD,
                data_path=str(work / "data.json"),
                encrypted_data_path=str(work / "data.enc"),
                index_path=str(work / "index.html"),
            )
            payload = extract_index_payload((work / "index.html").read_text(encoding="utf-8"))
            rendered = decrypt_payload(payload, PASSWORD, label="history index").decode("utf-8")
            for number in (19, 20, 59):
                self.assertIn(html.escape(events[number]["text"], quote=False), rendered)
            self.assertLess(rendered.index("<details>"), rendered.index("Archived event 20"))
            oldest = html.escape(events[-1]["text"], quote=False)
            with self.assertRaisesRegex(BuildVerificationError, "missing rendered value"):
                _verify_rendered_html(rendered.replace(oldest, ""), data)

    def test_wrong_password_does_not_overwrite_existing_plaintext(self) -> None:
        sentinel = b'{"sentinel":"keep exactly"}\n'
        (self.work / "data.json").write_bytes(sentinel)

        result = run_program(self.work, "decrypt.py", "definitely-wrong-password")

        self.assertNotEqual(0, result.returncode)
        self.assertEqual(sentinel, (self.work / "data.json").read_bytes())

    def test_verifier_rejects_outputs_built_from_stale_data(self) -> None:
        stale = copy.deepcopy(self.fixture_data)
        stale["meta"]["updated"] = "2100-01-01 07:00（台北）"
        write_json(self.work / "data.json", stale)

        with self.assertRaisesRegex(BuildVerificationError, "does not match"):
            verify_build(
                PASSWORD,
                data_path=str(self.work / "data.json"),
                encrypted_data_path=str(self.work / "data.enc"),
                index_path=str(self.work / "index.html"),
            )


class FailureAtomicityTests(unittest.TestCase):
    def test_invalid_data_does_not_overwrite_existing_build_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            copy_programs(work, "build.py", "validate_data.py")
            invalid = load_fixture()
            invalid["arr_series"]["companies"][0]["points"][0]["v"] = 0
            write_json(work / "data.json", invalid)
            data_sentinel = b"existing-encrypted-data"
            index_sentinel = b"existing-encrypted-index"
            (work / "data.enc").write_bytes(data_sentinel)
            (work / "index.html").write_bytes(index_sentinel)

            result = run_program(work, "build.py", PASSWORD)

            self.assertNotEqual(0, result.returncode)
            self.assertEqual(data_sentinel, (work / "data.enc").read_bytes())
            self.assertEqual(index_sentinel, (work / "index.html").read_bytes())


if __name__ == "__main__":
    unittest.main()

