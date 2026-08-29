"""连接配置：多远端 profile。命令行参数 > 环境变量 > 活动档案 > 默认值。

~/.guanjia.json 新格式：
    {"active": "default", "profiles": {"default": {"server": ..., "token": ..., "user": ...}}}
旧平铺格式（顶层 server/token）与老文件名 .bench.json 自动兼容读，
首次写入时迁移为新格式。密码永不落盘，只存会话令牌。
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _config_path() -> Path:
    return Path.home() / ".guanjia.json"


def _read_raw() -> dict:
    for name in (".guanjia.json", ".bench.json"):  # 老文件名兼容读
        path = Path.home() / name
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001 - 坏配置当空处理，别拦住启动
                return {}
    return {}


def _as_profiles(raw: dict) -> tuple[str, dict]:
    """返回 (active, profiles)；旧平铺格式视作 default 档案。"""
    if isinstance(raw.get("profiles"), dict):
        profiles = raw["profiles"]
        active = raw.get("active") or next(iter(profiles), "default")
        return active, profiles
    if raw.get("server") or raw.get("token"):
        return "default", {"default": {
            "server": str(raw.get("server") or ""),
            "token": str(raw.get("token") or ""),
            "user": str(raw.get("user") or ""),
        }}
    return "default", {}


def _private(path: Path) -> None:
    """把文件权限收成 0600——只有自己能读。

    2026-08-29 实测：~/.guanjia.json 里存着 API 令牌，权限却是 0644。
    这台机器上还有别的用户，谁都能读走令牌、以你的身份操作平台。
    umask 默认 022，所以不显式收就是 644。

    收不动就算了（比如挂在不支持权限的文件系统上）——
    存不下配置比权限松更糟。
    """
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write(active: str, profiles: dict) -> None:
    path = _config_path()
    path.write_text(
        json.dumps({"active": active, "profiles": profiles}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _private(path)


def load_config(server: str | None = None, token: str | None = None,
                profile: str | None = None) -> dict:
    active, profiles = _as_profiles(_read_raw())
    active = profile or os.getenv("GUANJIA_PROFILE") or active
    p = profiles.get(active) or {}
    return {
        "server": (server or os.getenv("GUANJIA_SERVER") or os.getenv("BENCH_SERVER")
                   or p.get("server") or "http://127.0.0.1:8000").rstrip("/"),
        "token": token or os.getenv("GUANJIA_TOKEN") or os.getenv("BENCH_TOKEN")
                 or p.get("token") or "",
        "profile": active,
    }


def save_login(server: str, token: str, user: str = "", profile: str | None = None) -> str:
    """登录成功后保存到指定（缺省为活动）档案并激活它，返回档案名。"""
    active, profiles = _as_profiles(_read_raw())
    name = profile or active or "default"
    profiles[name] = {"server": server.rstrip("/"), "token": token, "user": user}
    _write(name, profiles)
    return name


def list_profiles() -> tuple[str, dict]:
    return _as_profiles(_read_raw())


def use_profile(name: str) -> dict:
    active, profiles = _as_profiles(_read_raw())
    if name not in profiles:
        raise KeyError(name)
    _write(name, profiles)
    return profiles[name]


def drop_profile(name: str) -> None:
    active, profiles = _as_profiles(_read_raw())
    profiles.pop(name, None)
    if active not in profiles:
        active = next(iter(profiles), "default")
    _write(active, profiles)
