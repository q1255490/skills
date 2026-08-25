#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from capture_engine import (
    build_compare_image,
    capture_detail,
    capture_detail_from_session,
    capture_overview,
    copy_artifact,
    slugify,
)
from chrome_cdp import CDPSession
from chrome_runtime import ChromeRuntimeError, ensure_debug_chrome, open_or_reuse_target
from modao_adapter import (
    click_tree_path,
    detect_access_mode,
    extract_tree,
    fit_canvas_to_viewport,
    flatten_page_nodes,
    get_selected_tree_path,
    get_view_context,
    infer_state,
    infer_surface,
    set_capture_mode,
    wait_for_modao_ready,
    wait_for_selected_path,
)


def parse_args():
    parser = argparse.ArgumentParser(description="Scan a Modao prototype and capture structured evidence.")
    parser.add_argument("prototype_url", help="Modao share URL")
    parser.add_argument(
        "--output-root",
        default="deliverables/modao",
        help="Root directory for scan sessions",
    )
    return parser.parse_args()


def timestamp_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def relative_to_session(path: Path, session_dir: Path) -> str:
    return str(path.relative_to(session_dir))


def write_summary(session_dir: Path, session_data: dict):
    lines = [
        "# Modao Scan Summary",
        "",
        f"- Prototype URL: {session_data['prototype_url']}",
        f"- Session ID: `{session_data['session_id']}`",
        f"- Access mode: `{session_data['auth']['access_mode']}`",
        f"- Chrome mode: `{session_data['chrome']['mode']}`",
        f"- Pages scanned: {session_data['stats']['node_count']}",
        f"- Interactions captured: {session_data['stats']['edge_count']}",
        f"- Failures or blocked items: {session_data['stats']['failure_count']}",
        "",
        "## Surface Counts",
        "",
    ]

    surface_counts = Counter(node["surface"] for node in session_data["nodes"])
    if surface_counts:
        for surface, count in sorted(surface_counts.items()):
            lines.append(f"- {surface}: {count}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Blocked Items",
            "",
        ]
    )
    if session_data["blocked_items"]:
        for item in session_data["blocked_items"]:
            lines.append(f"- {item['reason']}: {item.get('tree_path', item.get('path', 'n/a'))}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `session.json`",
            "- `screens/`",
            "- `interactions/`",
        ]
    )
    (session_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def record_login_block(session: CDPSession, session_dir: Path, session_data: dict):
    blocked_dir = session_dir / "blocked"
    blocked_dir.mkdir(parents=True, exist_ok=True)
    screenshot_path = blocked_dir / "login_required.png"
    screenshot_path.write_bytes(session.capture_screenshot(full_page=False))
    session_data["blocked_items"].append(
        {
            "reason": "login_required",
            "artifacts": {"overview": relative_to_session(screenshot_path, session_dir)},
        }
    )


def main():
    args = parse_args()
    started_at = datetime.now(UTC)
    prototype_slug = slugify(args.prototype_url)
    session_id = f"{timestamp_id()}-{prototype_slug}"
    session_dir = Path(args.output_root) / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    runtime = ensure_debug_chrome()
    base_url = runtime["base_url"]
    target = open_or_reuse_target(base_url, args.prototype_url)
    page_session = CDPSession(target["webSocketDebuggerUrl"])

    session_data = {
        "prototype_url": args.prototype_url,
        "session_id": session_id,
        "started_at": started_at.isoformat(),
        "chrome": {
            "mode": runtime["mode"],
            "debug_port": runtime["debug_port"],
            "profile_dir": runtime["profile_dir"],
        },
        "auth": {"access_mode": "unknown"},
        "nodes": [],
        "edges": [],
        "blocked_items": [],
        "stats": {
            "node_count": 0,
            "edge_count": 0,
            "failure_count": 0,
        },
    }

    try:
        ready_state = wait_for_modao_ready(page_session)
        session_data["auth"]["access_mode"] = detect_access_mode(ready_state)
        if session_data["auth"]["access_mode"] == "login_required":
            record_login_block(page_session, session_dir, session_data)
            session_data["stats"]["failure_count"] = len(session_data["blocked_items"])
            (session_dir / "session.json").write_text(
                json.dumps(session_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_summary(session_dir, session_data)
            return 1

        tree = extract_tree(page_session)
        page_nodes = flatten_page_nodes(tree)
        if not page_nodes:
            session_data["blocked_items"].append({"reason": "page_tree_empty"})
            session_data["stats"]["failure_count"] = 1
            (session_dir / "session.json").write_text(
                json.dumps(session_data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            write_summary(session_dir, session_data)
            return 1

        previous_node = None
        for node in page_nodes:
            tree_path = node["tree_path"]
            set_capture_mode(page_session, "overview")
            selected_path = get_selected_tree_path(page_session)
            if selected_path != tree_path:
                click_result = click_tree_path(page_session, node["segments"])
                if not click_result.get("ok"):
                    session_data["blocked_items"].append(
                        {"reason": "page_click_failed", "tree_path": tree_path, "detail": click_result}
                    )
                    continue
                if not wait_for_selected_path(page_session, tree_path):
                    session_data["blocked_items"].append(
                        {"reason": "page_settle_timeout", "tree_path": tree_path}
                    )
                    continue

            set_capture_mode(page_session, "overview")
            overview_context = fit_canvas_to_viewport(page_session, min_fill=0.58)
            node_slug = slugify(tree_path)
            node_dir = session_dir / "screens" / node_slug
            overview_path = node_dir / "overview.png"
            detail_path = node_dir / "detail.png"
            capture_overview(page_session, overview_path)

            set_capture_mode(page_session, "detail")
            detail_context = fit_canvas_to_viewport(page_session, min_fill=0.78)
            detail_mode = "clip"
            if not capture_detail_from_session(
                page_session,
                detail_path,
                canvas_rect=detail_context.get("canvasRect"),
                viewport=detail_context.get("viewport"),
            ):
                detail_mode = "crop_fallback"
                detail_source_path = node_dir / "_detail_source.png"
                capture_overview(page_session, detail_source_path)
                capture_detail(
                    detail_source_path,
                    detail_path,
                    canvas_rect=detail_context.get("canvasRect"),
                    viewport=detail_context.get("viewport"),
                )
                detail_source_path.unlink(missing_ok=True)
            set_capture_mode(page_session, "overview")

            current_record = {
                "tree_path": tree_path,
                "surface": infer_surface(tree_path),
                "screen_name": node["screen_name"],
                "state": infer_state(node["screen_name"]),
                "zoom_percent": detail_context.get("zoomPercent"),
                "overview_zoom_percent": overview_context.get("zoomPercent"),
                "detail_zoom_percent": detail_context.get("zoomPercent"),
                "source": ["overview", "detail"],
                "detail_mode": detail_mode,
                "artifacts": {
                    "overview": relative_to_session(overview_path, session_dir),
                    "detail": relative_to_session(detail_path, session_dir),
                },
            }
            session_data["nodes"].append(current_record)

            if previous_node:
                edge_slug = f"{slugify(previous_node['tree_path'])}__to__{node_slug}"
                edge_dir = session_dir / "interactions" / edge_slug
                before_path = edge_dir / "before.png"
                after_path = edge_dir / "after.png"
                compare_path = edge_dir / "compare.png"
                copy_artifact(Path(previous_node["abs_overview"]), before_path)
                copy_artifact(overview_path, after_path)
                build_compare_image(
                    before_path,
                    after_path,
                    compare_path,
                    before_label="Before",
                    after_label="After",
                )
                session_data["edges"].append(
                    {
                        "from": previous_node["tree_path"],
                        "to": current_record["tree_path"],
                        "artifacts": {
                            "before": relative_to_session(before_path, session_dir),
                            "after": relative_to_session(after_path, session_dir),
                            "compare": relative_to_session(compare_path, session_dir),
                        },
                    }
                )

            previous_node = {
                "tree_path": current_record["tree_path"],
                "surface": current_record["surface"],
                "abs_overview": str(overview_path),
            }

        session_data["stats"]["node_count"] = len(session_data["nodes"])
        session_data["stats"]["edge_count"] = len(session_data["edges"])
        session_data["stats"]["failure_count"] = len(session_data["blocked_items"])
        (session_dir / "session.json").write_text(
            json.dumps(session_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        write_summary(session_dir, session_data)
        return 0
    finally:
        page_session.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ChromeRuntimeError as exc:
        raise SystemExit(str(exc))
