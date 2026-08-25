#!/usr/bin/env python3

import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from chrome_cdp import (
    DEFAULT_BASE_URL,
    activate_target,
    create_target,
    get_browser_info,
    list_targets,
)


DEFAULT_DEBUG_PORT = 9222
DEFAULT_PROFILE_DIR = Path.home() / ".codex" / "modao-browser-profile"
CHROME_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
]


class ChromeRuntimeError(RuntimeError):
    pass


def detect_chrome_binary() -> Path:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    raise ChromeRuntimeError("Google Chrome Stable was not found on this macOS machine.")


def debug_base_url(port: int = DEFAULT_DEBUG_PORT) -> str:
    return f"http://127.0.0.1:{port}"


def can_connect(base_url: str) -> bool:
    try:
        get_browser_info(base_url)
        return True
    except Exception:
        return False


def wait_for_debug_server(base_url: str, timeout_s: float = 15.0):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if can_connect(base_url):
            return
        time.sleep(0.5)
    raise ChromeRuntimeError(f"Chrome remote debugging endpoint did not come up at {base_url}.")


def launch_debug_chrome(
    *,
    port: int = DEFAULT_DEBUG_PORT,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
    initial_url: str = "about:blank",
) -> dict[str, Any]:
    chrome_path = detect_chrome_binary()
    profile_dir.mkdir(parents=True, exist_ok=True)
    command = [
        str(chrome_path),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-popup-blocking",
        initial_url,
    ]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    base_url = debug_base_url(port)
    wait_for_debug_server(base_url)
    return {
        "mode": "launched",
        "debug_port": port,
        "profile_dir": str(profile_dir),
        "chrome_path": str(chrome_path),
        "base_url": base_url,
    }


def ensure_debug_chrome(
    *,
    port: int = DEFAULT_DEBUG_PORT,
    profile_dir: Path = DEFAULT_PROFILE_DIR,
) -> dict[str, Any]:
    base_url = debug_base_url(port)
    if can_connect(base_url):
        return {
            "mode": "reused",
            "debug_port": port,
            "profile_dir": str(profile_dir),
            "chrome_path": str(detect_chrome_binary()),
            "base_url": base_url,
        }
    return launch_debug_chrome(port=port, profile_dir=profile_dir)


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def _same_prototype_url(current_url: str, target_url: str) -> bool:
    if _normalize_url(current_url) == _normalize_url(target_url):
        return True
    current = urlparse(current_url)
    target = urlparse(target_url)
    return (
        current.netloc == target.netloc
        and current.path == target.path
        and bool(current.path)
        and current.path != "/"
    )


def find_existing_modao_target(base_url: str, prototype_url: str) -> dict[str, Any] | None:
    for target in list_targets(base_url, target_type="page"):
        current_url = target.get("url", "")
        if _same_prototype_url(current_url, prototype_url):
            return target
    return None


def wait_for_target(base_url: str, prototype_url: str, timeout_s: float = 15.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        target = find_existing_modao_target(base_url, prototype_url)
        if target:
            return target
        time.sleep(0.5)
    raise ChromeRuntimeError(f"Could not find a Chrome target for {prototype_url}.")


def open_or_reuse_target(base_url: str, prototype_url: str) -> dict[str, Any]:
    existing = find_existing_modao_target(base_url, prototype_url)
    if existing:
        activate_target(base_url, existing["id"])
        return existing

    target_id = create_target(base_url, prototype_url)
    activate_target(base_url, target_id)
    return wait_for_target(base_url, prototype_url)

