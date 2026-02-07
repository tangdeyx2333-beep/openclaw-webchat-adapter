"""Test dotenv parsing and loading behavior."""

from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, Iterator, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_gateway_adapter.env import load_dotenv, parse_dotenv_text


@contextlib.contextmanager
def _temporary_env(overrides: Dict[str, Optional[str]]) -> Iterator[None]:
    old_values: Dict[str, Optional[str]] = {}
    for k, v in overrides.items():
        old_values[k] = os.environ.get(k)
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    try:
        yield
    finally:
        for k, old in old_values.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old


class TestParseDotenvText(unittest.TestCase):
    def test_parse_skips_comments_blanks_invalid_and_strips_quotes(self) -> None:
        text = """
        # comment
        A=1
        B = "two"
        C='three'
        INVALID
        =novalue
        EMPTY=
        """
        parsed = parse_dotenv_text(text)
        self.assertEqual(parsed.get("A"), "1")
        self.assertEqual(parsed.get("B"), "two")
        self.assertEqual(parsed.get("C"), "three")
        self.assertEqual(parsed.get("EMPTY"), "")
        self.assertNotIn("INVALID", parsed)
        self.assertNotIn("", parsed)


class TestLoadDotenv(unittest.TestCase):
    def test_load_dotenv_no_override_skips_existing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            env_path.write_text("X=from_dotenv\nY=2\n", encoding="utf-8")

            with _temporary_env({"X": "from_env", "Y": None}):
                result = load_dotenv(path=str(env_path), override=False)
                self.assertIsNotNone(result)
                self.assertEqual(os.environ.get("X"), "from_env")
                self.assertEqual(os.environ.get("Y"), "2")
                self.assertEqual(result.source_path, str(env_path))
                self.assertEqual(result.loaded_count, 1)
                self.assertEqual(result.skipped_count, 1)

    def test_load_dotenv_override_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            env_path = Path(td) / ".env"
            env_path.write_text("X=from_dotenv\n", encoding="utf-8")

            with _temporary_env({"X": "from_env"}):
                result = load_dotenv(path=str(env_path), override=True)
                self.assertIsNotNone(result)
                self.assertEqual(os.environ.get("X"), "from_dotenv")
                self.assertEqual(result.loaded_count, 1)
                self.assertEqual(result.skipped_count, 0)

