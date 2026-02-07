"""Test .env path resolution and loading behavior."""

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

import openclaw_gateway_adapter.config as config_mod
from openclaw_gateway_adapter.config import AdapterSettings, _resolve_dotenv_path


@contextlib.contextmanager
def _temporary_working_directory(path: Path) -> Iterator[None]:
    old = os.getcwd()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(old)


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


class TestDotenvPathResolution(unittest.TestCase):
    def test_resolve_dotenv_from_src_workdir_finds_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project_root = Path(td)
            (project_root / ".env").write_text("OPENCLAW_GATEWAY_TOKEN=abc\n", encoding="utf-8")

            fake_config_path = project_root / "src" / "openclaw_gateway_adapter" / "config.py"
            fake_config_path.parent.mkdir(parents=True, exist_ok=True)
            fake_config_path.write_text("# placeholder\n", encoding="utf-8")

            old_file = getattr(config_mod, "__file__", None)
            config_mod.__file__ = str(fake_config_path)
            try:
                with _temporary_working_directory(project_root / "src"):
                    resolved = _resolve_dotenv_path(".env")
                    self.assertEqual(Path(resolved), (project_root / ".env").resolve())
            finally:
                if old_file is not None:
                    config_mod.__file__ = old_file

    def test_from_env_loads_dotenv_even_when_cwd_is_src(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            project_root = Path(td)
            (project_root / ".env").write_text("OPENCLAW_GATEWAY_TOKEN=from_dotenv\n", encoding="utf-8")

            fake_config_path = project_root / "src" / "openclaw_gateway_adapter" / "config.py"
            fake_config_path.parent.mkdir(parents=True, exist_ok=True)
            fake_config_path.write_text("# placeholder\n", encoding="utf-8")

            old_file = getattr(config_mod, "__file__", None)
            config_mod.__file__ = str(fake_config_path)
            try:
                with _temporary_env(
                    {
                        "OPENCLAW_GATEWAY_TOKEN": None,
                        "OPENCLAW_GATEWAY_PASSWORD": None,
                        "OPENCLAW_GATEWAY_URL": None,
                        "OPENCLAW_SESSION_KEY": None,
                    }
                ):
                    with _temporary_working_directory(project_root / "src"):
                        settings = AdapterSettings.from_env(dotenv_path=".env")
                self.assertEqual(settings.token, "from_dotenv")
            finally:
                if old_file is not None:
                    config_mod.__file__ = old_file
