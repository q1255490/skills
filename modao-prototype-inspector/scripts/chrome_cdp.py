#!/usr/bin/env python3

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import requests
import websocket


DEFAULT_BASE_URL = "http://127.0.0.1:9222"


def get_json(base_url: str, path: str, method: str = "GET") -> Any:
    response = requests.request(method=method, url=f"{base_url}{path}", timeout=10)
    response.raise_for_status()
    return response.json()


def list_targets(base_url: str, target_type: str | None = None) -> list[dict[str, Any]]:
    targets = get_json(base_url, "/json/list")
    if target_type:
        targets = [target for target in targets if target.get("type") == target_type]
    return targets


def get_browser_info(base_url: str) -> dict[str, Any]:
    return get_json(base_url, "/json/version")


def get_browser_ws_url(base_url: str) -> str:
    return get_browser_info(base_url)["webSocketDebuggerUrl"]


def match_targets(targets: list[dict[str, Any]], query: str | None) -> list[dict[str, Any]]:
    pages = [target for target in targets if target.get("type") == "page"]
    if not query:
        return pages

    query_lower = query.lower()
    return [
        target
        for target in pages
        if query_lower in target.get("title", "").lower()
        or query_lower in target.get("url", "").lower()
        or query_lower == target.get("id", "").lower()
    ]


class CDPSession:
    def __init__(self, ws_url: str):
        self.ws = websocket.create_connection(
            ws_url,
            timeout=10,
            suppress_origin=True,
        )
        self.next_id = 1

    def close(self):
        self.ws.close()

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        message_id = self.next_id
        self.next_id += 1
        self.ws.send(
            json.dumps(
                {"id": message_id, "method": method, "params": params or {}},
                ensure_ascii=False,
            )
        )
        while True:
            payload = json.loads(self.ws.recv())
            if payload.get("id") == message_id:
                if "error" in payload:
                    raise RuntimeError(payload["error"])
                return payload.get("result", {})

    def evaluate(
        self,
        expression: str,
        *,
        return_by_value: bool = True,
        await_promise: bool = True,
    ) -> Any:
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": return_by_value,
                "awaitPromise": await_promise,
            },
        )
        return result.get("result", {}).get("value")

    def capture_screenshot(
        self,
        *,
        full_page: bool = False,
        clip: dict[str, Any] | None = None,
    ) -> bytes:
        self.call("Page.enable")
        if full_page:
            metrics = self.call("Page.getLayoutMetrics")
            content_size = metrics["contentSize"]
            width = max(1, int(content_size["width"]))
            height = max(1, int(content_size["height"]))
            self.call(
                "Emulation.setDeviceMetricsOverride",
                {
                    "mobile": False,
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                },
            )
        params: dict[str, Any] = {"format": "png", "captureBeyondViewport": full_page}
        if clip:
            params["clip"] = clip
        result = self.call("Page.captureScreenshot", params)
        return base64.b64decode(result["data"])

    def click(self, x: float, y: float, *, wait_ms: int = 800):
        self.call("Page.enable")
        self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        self.call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        self.call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        if wait_ms:
            self.evaluate(
                f"new Promise(resolve => setTimeout(resolve, {wait_ms}))",
                await_promise=True,
            )


def require_single_target(base_url: str, query: str | None) -> dict[str, Any]:
    matched = match_targets(list_targets(base_url), query)
    if not matched:
        raise SystemExit(f"No page target matched query: {query!r}")
    if len(matched) > 1:
        print("Multiple targets matched. Refine --query.", file=sys.stderr)
        for target in matched:
            print(
                json.dumps(
                    {
                        "title": target.get("title"),
                        "url": target.get("url"),
                        "id": target.get("id"),
                    },
                    ensure_ascii=False,
                ),
                file=sys.stderr,
            )
        raise SystemExit(2)
    return matched[0]


def create_target(base_url: str, url: str) -> str:
    session = CDPSession(get_browser_ws_url(base_url))
    try:
        result = session.call("Target.createTarget", {"url": url})
        return result["targetId"]
    finally:
        session.close()


def activate_target(base_url: str, target_id: str):
    session = CDPSession(get_browser_ws_url(base_url))
    try:
        session.call("Target.activateTarget", {"targetId": target_id})
    finally:
        session.close()


def open_page_session(base_url: str, query: str) -> CDPSession:
    target = require_single_target(base_url, query)
    return CDPSession(target["webSocketDebuggerUrl"])


def cmd_list(args):
    for target in match_targets(list_targets(args.base_url), args.query):
        print(
            json.dumps(
                {
                    "title": target.get("title"),
                    "url": target.get("url"),
                    "id": target.get("id"),
                    "type": target.get("type"),
                },
                ensure_ascii=False,
            )
        )


def cmd_screenshot(args):
    target = require_single_target(args.base_url, args.query)
    session = CDPSession(target["webSocketDebuggerUrl"])
    try:
        payload = session.capture_screenshot(full_page=args.full_page)
    finally:
        session.close()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    print(str(output))


def cmd_eval(args):
    target = require_single_target(args.base_url, args.query)
    session = CDPSession(target["webSocketDebuggerUrl"])
    try:
        result = session.evaluate(args.expression)
    finally:
        session.close()

    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_click(args):
    target = require_single_target(args.base_url, args.query)
    session = CDPSession(target["webSocketDebuggerUrl"])
    try:
        session.click(args.x, args.y, wait_ms=args.wait_ms)
    finally:
        session.close()


def cmd_open(args):
    target_id = create_target(args.base_url, args.url)
    activate_target(args.base_url, target_id)
    print(target_id)


def build_parser():
    parser = argparse.ArgumentParser(description="Small Chrome DevTools Protocol helper")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List page targets")
    list_parser.add_argument("--query", help="Filter by title, URL, or target id")
    list_parser.set_defaults(func=cmd_list)

    screenshot_parser = subparsers.add_parser("screenshot", help="Save a page screenshot")
    screenshot_parser.add_argument("--query", required=True, help="Target title, URL, or target id")
    screenshot_parser.add_argument("--output", required=True, help="Output PNG path")
    screenshot_parser.add_argument("--full-page", action="store_true", help="Capture full page")
    screenshot_parser.set_defaults(func=cmd_screenshot)

    eval_parser = subparsers.add_parser("eval", help="Evaluate JS in a page target")
    eval_parser.add_argument("--query", required=True, help="Target title, URL, or target id")
    eval_parser.add_argument("--expression", required=True, help="JavaScript expression")
    eval_parser.set_defaults(func=cmd_eval)

    click_parser = subparsers.add_parser("click", help="Click a point in a page target")
    click_parser.add_argument("--query", required=True, help="Target title, URL, or target id")
    click_parser.add_argument("--x", required=True, type=float, help="Viewport x coordinate")
    click_parser.add_argument("--y", required=True, type=float, help="Viewport y coordinate")
    click_parser.add_argument("--wait-ms", type=int, default=800, help="Milliseconds to wait after click")
    click_parser.set_defaults(func=cmd_click)

    open_parser = subparsers.add_parser("open", help="Open a URL in a new target")
    open_parser.add_argument("--url", required=True, help="URL to open")
    open_parser.set_defaults(func=cmd_open)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
