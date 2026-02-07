"""无需外部依赖，从 .env 文件加载环境变量。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class DotenvLoadResult:
    """返回一次 .env 加载操作的摘要结果。

    Args:
        loaded_count: 写入到 os.environ 的变量数量。
        skipped_count: 被跳过的条目数量（如：已存在且未覆盖）。
        source_path: .env 文件路径。
    """

    loaded_count: int
    skipped_count: int
    source_path: str


def _strip_quotes(value: str) -> str:
    """去掉 .env 值两端的一对匹配引号。

    Args:
        value: .env 行中的原始 value 字符串。

    Returns:
        若 value 被同类引号包裹，则返回去引号后的值；否则返回原值。
    """

    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def parse_dotenv_text(text: str) -> Dict[str, str]:
    """解析 .env 文本内容为键值对字典。

    Args:
        text: .env 文件的原始文本内容。

    Returns:
        解析得到的环境变量字典。
    """

    parsed: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        value = _strip_quotes(value)
        parsed[key] = value
    return parsed


def load_dotenv(path: str = ".env", override: bool = False) -> Optional[DotenvLoadResult]:
    """将 .env 文件中的变量加载进 os.environ。

    Args:
        path: .env 文件路径。
        override: 是否覆盖 os.environ 中已存在的同名变量。

    Returns:
        若文件存在并完成解析，返回 DotenvLoadResult；否则返回 None。
    """

    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        data = parse_dotenv_text(f.read())
    loaded = 0
    skipped = 0
    for k, v in data.items():
        if not override and k in os.environ:
            skipped += 1
            continue
        os.environ[k] = v
        loaded += 1
    return DotenvLoadResult(loaded_count=loaded, skipped_count=skipped, source_path=path)

