from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from config.env_store import save_env

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = PROJECT_ROOT / "run"
LOG_DIR = PROJECT_ROOT / "logs"
DEFAULT_WEB_PORT = 3333


class InstanceAction(BaseModel):
    env_file: str = Field(..., description="Env file name, e.g. .env-lqx")
    target: str = Field("all", description="collector|web|all")


class PortUpdateAction(BaseModel):
    env_file: str = Field(..., description="Env file name, e.g. .env-lqx")
    web_port: int = Field(..., ge=1, le=65535)


def _ensure_dirs() -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _safe_name(env_file: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in env_file)


def _pid_file(env_file: str, role: str) -> Path:
    return RUN_DIR / f"{role}.{_safe_name(env_file)}.pid"


def _log_file(env_file: str, role: str) -> Path:
    return LOG_DIR / f"{role}.{_safe_name(env_file)}.log"


def _is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None
    return pid if pid > 0 else None


def _running_pid(path: Path) -> int | None:
    pid = _read_pid(path)
    if pid is None:
        return None
    if _is_pid_running(pid):
        return pid
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return None


def _read_env_vars(env_file: str) -> dict[str, str]:
    path = PROJECT_ROOT / env_file
    if not path.exists():
        return {}
    raw = dotenv_values(path)
    out: dict[str, str] = {}
    for k, v in raw.items():
        if k and v is not None:
            out[str(k)] = str(v)
    return out


def _resolve_web_port(env_file: str) -> int:
    env = _read_env_vars(env_file)
    for key in ("WEB_PORT", "PORT"):
        try:
            val = int(env.get(key, "").strip())
            if 1 <= val <= 65535:
                return val
        except Exception:
            continue
    return DEFAULT_WEB_PORT


def _port_owner_pid(port: int) -> int | None:
    if os.name != "nt":
        return None
    try:
        out = subprocess.check_output(
            ["netstat", "-ano", "-p", "tcp"],
            cwd=str(PROJECT_ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
    except Exception:
        return None
    needle = f":{port}"
    for line in out.splitlines():
        text = line.strip()
        if "LISTENING" not in text or needle not in text:
            continue
        parts = text.split()
        if len(parts) >= 5:
            try:
                pid = int(parts[-1])
                if pid > 0:
                    return pid
            except Exception:
                continue
    return None


def _is_port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _spawn_background(cmd: list[str], *, log_path: Path) -> int:
    _ensure_dirs()
    log_fp = open(log_path, "a", encoding="utf-8")
    flags = 0
    if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=log_fp,
        stderr=log_fp,
        creationflags=flags,
    )
    return int(proc.pid)


def _start_collector(env_file: str) -> int:
    pid_path = _pid_file(env_file, "collector")
    running = _running_pid(pid_path)
    if running is not None:
        return running
    pid = _spawn_background(
        [sys.executable, "-u", "collector_bot.py", "--env-file", env_file],
        log_path=_log_file(env_file, "collector"),
    )
    pid_path.write_text(str(pid), encoding="utf-8")
    return pid


def _start_web(env_file: str) -> int:
    pid_path = _pid_file(env_file, "web")
    running = _running_pid(pid_path)
    if running is not None:
        return running
    port = _resolve_web_port(env_file)
    if _is_port_listening(port):
        owner = _port_owner_pid(port)
        raise RuntimeError(f"端口 {port} 已被占用" + (f" (PID={owner})" if owner else ""))
    pid = _spawn_background(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "web.app:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(port),
            "--env-file",
            env_file,
        ],
        log_path=_log_file(env_file, "web"),
    )
    pid_path.write_text(str(pid), encoding="utf-8")
    return pid


def _stop_pid(pid: int) -> None:
    if pid <= 0:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def _stop_role(env_file: str, role: str) -> None:
    path = _pid_file(env_file, role)
    pid = _read_pid(path)
    if pid is not None:
        _stop_pid(pid)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _scan_env_files() -> list[str]:
    env_files = []
    for p in PROJECT_ROOT.glob(".env-*"):
        if p.is_file():
            env_files.append(p.name)
    env_files.sort()
    return env_files


@router.get("/api/manager/instances")
def manager_instances() -> list[dict[str, Any]]:
    _ensure_dirs()
    out: list[dict[str, Any]] = []
    for env_file in _scan_env_files():
        web_port = _resolve_web_port(env_file)
        cpid = _running_pid(_pid_file(env_file, "collector"))
        wpid = _running_pid(_pid_file(env_file, "web"))
        out.append(
            {
                "env_file": env_file,
                "web_port": web_port,
                "collector_running": cpid is not None,
                "collector_pid": cpid,
                "collector_log": str(_log_file(env_file, "collector")),
                "web_running": wpid is not None,
                "web_pid": wpid,
                "web_log": str(_log_file(env_file, "web")),
                "web_url": f"http://127.0.0.1:{web_port}/",
            }
        )
    return out


@router.post("/api/manager/start")
def manager_start(payload: InstanceAction) -> dict[str, Any]:
    env_file = payload.env_file.strip()
    if not env_file:
        raise HTTPException(status_code=400, detail="env_file required")
    if not (PROJECT_ROOT / env_file).exists():
        raise HTTPException(status_code=404, detail=f"env file not found: {env_file}")

    target = payload.target.strip().lower()
    if target not in {"collector", "web", "all"}:
        raise HTTPException(status_code=400, detail="target must be collector|web|all")

    started: dict[str, int] = {}
    try:
        if target in {"collector", "all"}:
            started["collector_pid"] = _start_collector(env_file)
        if target in {"web", "all"}:
            started["web_pid"] = _start_web(env_file)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "env_file": env_file, **started}


@router.post("/api/manager/stop")
def manager_stop(payload: InstanceAction) -> dict[str, Any]:
    env_file = payload.env_file.strip()
    if not env_file:
        raise HTTPException(status_code=400, detail="env_file required")

    target = payload.target.strip().lower()
    if target not in {"collector", "web", "all"}:
        raise HTTPException(status_code=400, detail="target must be collector|web|all")

    if target in {"collector", "all"}:
        _stop_role(env_file, "collector")
    if target in {"web", "all"}:
        _stop_role(env_file, "web")
    return {"ok": True, "env_file": env_file}


@router.post("/api/manager/set_port")
def manager_set_port(payload: PortUpdateAction) -> dict[str, Any]:
    env_file = payload.env_file.strip()
    if not env_file:
        raise HTTPException(status_code=400, detail="env_file required")
    env_path = PROJECT_ROOT / env_file
    if not env_path.exists():
        raise HTTPException(status_code=404, detail=f"env file not found: {env_file}")

    web_port = int(payload.web_port)
    save_env({"WEB_PORT": str(web_port)}, env_file)

    # Port is a startup parameter; restart web process to apply.
    _stop_role(env_file, "web")
    try:
        new_pid = _start_web(env_file)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"ok": True, "env_file": env_file, "web_port": web_port, "web_pid": new_pid}


@router.post("/api/manager/start_all")
def manager_start_all() -> dict[str, Any]:
    env_files = _scan_env_files()
    started: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for env_file in env_files:
        item: dict[str, Any] = {"env_file": env_file}
        try:
            item["collector_pid"] = _start_collector(env_file)
            item["web_pid"] = _start_web(env_file)
            started.append(item)
        except RuntimeError as exc:
            errors.append({"env_file": env_file, "error": str(exc)})
    return {"ok": len(errors) == 0, "started": started, "errors": errors}


@router.post("/api/manager/stop_all")
def manager_stop_all() -> dict[str, Any]:
    env_files = _scan_env_files()
    for env_file in env_files:
        _stop_role(env_file, "collector")
        _stop_role(env_file, "web")
    return {"ok": True, "stopped_envs": env_files}


@router.get("/api/manager/logs")
def manager_logs(
    env_file: str = Query(..., description="Env file name, e.g. .env-lqx"),
    role: str = Query("collector", description="collector|web"),
    tail: int = Query(200, ge=10, le=5000),
) -> dict[str, Any]:
    role = role.strip().lower()
    if role not in {"collector", "web"}:
        raise HTTPException(status_code=400, detail="role must be collector|web")

    log_path = _log_file(env_file, role)
    pid = _running_pid(_pid_file(env_file, role))

    if not log_path.exists():
        return {
            "env_file": env_file,
            "role": role,
            "running": pid is not None,
            "pid": pid,
            "log_path": str(log_path),
            "content": "",
        }

    try:
        text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"read log failed: {exc}")

    lines = text.splitlines()
    clipped = "\n".join(lines[-tail:])
    return {
        "env_file": env_file,
        "role": role,
        "running": pid is not None,
        "pid": pid,
        "log_path": str(log_path),
        "content": clipped,
    }
