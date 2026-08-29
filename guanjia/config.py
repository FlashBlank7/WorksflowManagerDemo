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
            _private(path)  # 见 _private：读的时候也收，不然老文件永远松着
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

    **写的时候收不够**：第一版只挂在 _write 上，于是这次改动之前
    已经登录过的人，只要不再改配置，那份 0644 的令牌就一直躺着。
    老文件名 .bench.json 更彻底——我们只读它、从不写它，永远收不到。
    所以读的时候也收：这是我们自己建的文件，收它不算越权
    （.env 是用户自己建的，那边只提醒不动手）。

    已经比 0600 更严的（比如 0400）不动它——用户可能是故意的。
    收不动也就算了（比如挂在不支持权限的文件系统上）：
    存不下配置比权限松更糟。
    """
    try:
        if os.stat(path).st_mode & 0o077:
            path.chmod(0o600)
    except OSError:
        pass


def _write(active: str, profiles: dict) -> None:
    """先写同目录的临时文件（一出生就是 0600），再原子换名过去。

    两件事一起解决，都是量出来的，不是设想的：

    1. **权限窗口**。原来是 write_text 之后再 chmod，中间那一小段
       文件已经带着令牌、权限却还是 0644。实测拿一个线程死盯着看：
       6103 次采样里 8 次逮到 0644。这台机器上确实还有别的用户。
       用 os.open 带 0o600 建，就没有那一段。

    2. **半截配置**。write_text 是先截断再写，写到一半掉电/被杀，
       留下的是一个空的或残缺的 json——下次启动 _read_raw 把它当空配置
       吞掉（那儿是 except 全捕），用户的登录**就这么没了**，
       而且没有任何提示。换名是原子的：要么是旧的完整配置，要么是新的。
    """
    path = _config_path()
    payload = json.dumps({"active": active, "profiles": profiles},
                         ensure_ascii=False, indent=1)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(fd, payload.encode("utf-8"))
        finally:
            os.close(fd)
        os.replace(tmp, path)
    except OSError:
        # 临时文件这条路走不通（只读目录、怪文件系统……）就退回直写：
        # **存不下配置比权限松更糟**，这是 _private 里已经定过的调子。
        try:
            os.unlink(tmp)
        except OSError:
            pass
        path.write_text(payload, encoding="utf-8")
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
