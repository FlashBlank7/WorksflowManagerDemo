"""连接配置：环境变量优先，其次 ~/.bench.json，命令行参数最高。"""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_config(server: str | None = None, token: str | None = None) -> dict:
    file_cfg = {}
    for name in (".guanjia.json", ".bench.json"):  # 老文件名兼容读
        path = Path.home() / name
        if path.is_file():
            file_cfg = json.loads(path.read_text(encoding="utf-8"))
            break
    return {
        "server": (server or os.getenv("GUANJIA_SERVER") or os.getenv("BENCH_SERVER") or file_cfg.get("server") or "http://127.0.0.1:8000").rstrip("/"),
        "token": token or os.getenv("GUANJIA_TOKEN") or os.getenv("BENCH_TOKEN") or file_cfg.get("token") or "",
    }
