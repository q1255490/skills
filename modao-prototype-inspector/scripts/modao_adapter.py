#!/usr/bin/env python3

import time
from typing import Any

from chrome_cdp import CDPSession


READY_EXPRESSION = r"""
(() => {
  const bodyText = (document.body && document.body.innerText) ? document.body.innerText : "";
  const hasTreeBody = !!document.querySelector('.rn-content-body');
  const hasTreeRoot = !!document.querySelector('.rn-content-body ul.styles__StyledScreenList-sc-1pj18ld-0, .rn-content-body ul');
  const hasCanvas = !!document.querySelector('.tree-node.rResCanvas');
  const loginLike = /(登录|扫码登录|继续使用|手机号登录|验证码登录)/.test(bodyText);
  return {
    title: document.title,
    url: location.href,
    bodySample: bodyText.slice(0, 400),
    hasTreeBody,
    hasTreeRoot,
    hasCanvas,
    loginLike,
    ready: hasTreeBody && hasTreeRoot
  };
})()
"""


TREE_EXPRESSION = r"""
(() => {
  const root = document.querySelector('.rn-content-body ul.styles__StyledScreenList-sc-1pj18ld-0, .rn-content-body ul');
  if (!root) return [];

  function nodeLabel(li) {
    const span = li.querySelector(':scope > .rn-list-item .editable-span');
    const item = li.querySelector(':scope > .rn-list-item');
    return (span?.innerText || item?.innerText || '').trim();
  }

  function nodeKind(li) {
    const item = li.querySelector(':scope > .rn-list-item');
    if (!item) return 'unknown';
    if (item.classList.contains('folder')) return 'folder';
    if (item.classList.contains('page')) return 'page';
    return 'unknown';
  }

  function nodeRect(li) {
    const item = li.querySelector(':scope > .rn-list-item');
    if (!item) return null;
    const rect = item.getBoundingClientRect();
    return {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      centerX: rect.x + rect.width / 2,
      centerY: rect.y + rect.height / 2
    };
  }

  function walk(ul) {
    const out = [];
    for (const child of ul.children) {
      if (!(child instanceof HTMLElement) || !child.matches('li.rn-content-item')) continue;
      const item = child.querySelector(':scope > .rn-list-item');
      if (!item) continue;
      const label = nodeLabel(child);
      if (!label) continue;
      const childUl = child.querySelector(':scope > ul.child-screens');
      out.push({
        name: label,
        kind: nodeKind(child),
        rect: nodeRect(child),
        selected: child.classList.contains('active') || item.classList.contains('active'),
        children: childUl ? walk(childUl) : []
      });
    }
    return out;
  }

  return walk(root);
})()
"""


SELECTED_PATH_EXPRESSION = r"""
(() => {
  const active = document.querySelector('.rn-list-item.active.select, .rn-list-item.active');
  if (!active) return null;

  function labelFor(li) {
    const span = li.querySelector(':scope > .rn-list-item .editable-span');
    const item = li.querySelector(':scope > .rn-list-item');
    return (span?.innerText || item?.innerText || '').trim();
  }

  let li = active.closest('li.rn-content-item');
  const path = [];
  while (li) {
    const label = labelFor(li);
    if (label) path.unshift(label);
    const parentUl = li.parentElement;
    li = parentUl ? parentUl.closest('li.rn-content-item') : null;
  }
  return path;
})()
"""


CLICK_PATH_EXPRESSION_TEMPLATE = r"""
(() => {
  const segments = __SEGMENTS__;
  const root = document.querySelector('.rn-content-body ul.styles__StyledScreenList-sc-1pj18ld-0, .rn-content-body ul');
  if (!root) return { ok: false, reason: 'tree_root_missing' };

  function labelFor(li) {
    const span = li.querySelector(':scope > .rn-list-item .editable-span');
    const item = li.querySelector(':scope > .rn-list-item');
    return (span?.innerText || item?.innerText || '').trim();
  }

  function findPath(ul, remaining) {
    if (!remaining.length) return null;
    for (const child of ul.children) {
      if (!(child instanceof HTMLElement) || !child.matches('li.rn-content-item')) continue;
      const label = labelFor(child);
      if (label !== remaining[0]) continue;
      if (remaining.length === 1) return child;
      const childUl = child.querySelector(':scope > ul.child-screens');
      if (!childUl) return null;
      return findPath(childUl, remaining.slice(1));
    }
    return null;
  }

  const li = findPath(root, segments);
  if (!li) return { ok: false, reason: 'path_not_found', segments };
  const item = li.querySelector(':scope > .rn-list-item');
  if (!item) return { ok: false, reason: 'path_item_missing', segments };

  item.scrollIntoView({ block: 'center', inline: 'nearest' });
  item.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
  const rect = item.getBoundingClientRect();
  return {
    ok: true,
    rect: {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      centerX: rect.x + rect.width / 2,
      centerY: rect.y + rect.height / 2
    }
  };
})()
"""


VIEW_CONTEXT_EXPRESSION = r"""
(() => {
  const zoom = document.querySelector('.zoom-scale')?.innerText?.trim() || null;
  const zoomValue = zoom ? parseInt(zoom.replace('%', ''), 10) : null;
  const viewportNode =
    document.querySelector('main.mb-viewport, .mb-viewport') ||
    document.querySelector('section[class*="StyledArtboard"], section[class*="Artboard"]');
  const viewportRect = viewportNode
    ? viewportNode.getBoundingClientRect()
    : { x: 0, y: 48, width: window.innerWidth, height: window.innerHeight - 48 };
  const viewportLeft = viewportRect.x;
  const viewportTop = viewportRect.y;
  const viewportRight = viewportRect.x + viewportRect.width;
  const viewportBottom = viewportRect.y + viewportRect.height;
  const leftPanelRight =
    document.querySelector('.mb-left-panel')?.getBoundingClientRect().right ||
    document.querySelector('.left-panel-box')?.getBoundingClientRect().right ||
    0;
  const rightPanelLeft =
    document.querySelector('.styles__StyledRightSidePanel-sc-103a1mw-0')?.getBoundingClientRect().left ||
    window.innerWidth;

  function visibleIntersection(rect) {
    const left = Math.max(rect.x, viewportLeft);
    const top = Math.max(rect.y, viewportTop);
    const right = Math.min(rect.x + rect.width, viewportRight);
    const bottom = Math.min(rect.y + rect.height, viewportBottom);
    return {
      left,
      top,
      right,
      bottom,
      width: Math.max(0, right - left),
      height: Math.max(0, bottom - top)
    };
  }

  function rectPayload(rect, extra = {}) {
    return {
      x: rect.x,
      y: rect.y,
      width: rect.width,
      height: rect.height,
      right: rect.x + rect.width,
      bottom: rect.y + rect.height,
      area: rect.width * rect.height,
      ...extra
    };
  }

  const canvasNodes = [...document.querySelectorAll('.tree-node.rResCanvas')]
    .map(el => {
      const rect = el.getBoundingClientRect();
      const intersection = visibleIntersection(rect);
      const styleWidth = parseFloat(el.style.width || rect.width);
      const styleHeight = parseFloat(el.style.height || rect.height);
      return {
        rect: rectPayload(rect, {
          naturalWidth: Number.isFinite(styleWidth) ? styleWidth : rect.width,
          naturalHeight: Number.isFinite(styleHeight) ? styleHeight : rect.height,
          source: 'canvas'
        }),
        visibleArea: intersection.width * intersection.height,
        text: (el.innerText || '').trim().slice(0, 200),
        totalArea: rect.width * rect.height
      };
    })
    .filter(node => node.visibleArea > 120 * 120)
    .sort((a, b) => {
      if (b.visibleArea !== a.visibleArea) {
        return b.visibleArea - a.visibleArea;
      }
      return b.totalArea - a.totalArea;
    });

  const active = document.querySelector('.rn-list-item.active.select, .rn-list-item.active');
  function labelFor(li) {
    const span = li.querySelector(':scope > .rn-list-item .editable-span');
    const item = li.querySelector(':scope > .rn-list-item');
    return (span?.innerText || item?.innerText || '').trim();
  }
  let li = active ? active.closest('li.rn-content-item') : null;
  const path = [];
  while (li) {
    const label = labelFor(li);
    if (label) path.unshift(label);
    const parentUl = li.parentElement;
    li = parentUl ? parentUl.closest('li.rn-content-item') : null;
  }

  return {
    title: document.title,
    url: location.href,
    zoomPercent: zoom,
    zoomValue,
    viewport: {
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio,
      leftPanelRight,
      rightPanelLeft
    },
    viewportRect: rectPayload(viewportRect, { source: 'viewport' }),
    selectedPath: path,
    bodySample: (document.body?.innerText || '').slice(0, 400),
    canvasRect: canvasNodes[0]?.rect || null
  };
})()
"""


SET_CAPTURE_MODE_EXPRESSION_TEMPLATE = r"""
(() => {
  const mode = "__MODE__";
  const root = document.documentElement;
  root.dataset.codexModaoCaptureMode = mode;
  const styleId = "__codex_modao_capture_style__";
  let style = document.getElementById(styleId);
  if (!style) {
    style = document.createElement("style");
    style.id = styleId;
    document.head.appendChild(style);
  }
  style.textContent = `
    html[data-codex-modao-capture-mode="overview"] .styles__StyledRightSidePanel-sc-103a1mw-0,
    html[data-codex-modao-capture-mode="overview"] .ToggleVisibilityButtonHOC__StyledToggleWrapper-sc-10pgtyu-0:has(.styles__StyledRightSidePanel-sc-103a1mw-0),
    html[data-codex-modao-capture-mode="overview"] .widget.tree-node.wSticky,
    html[data-codex-modao-capture-mode="overview"] [class*="StyledSticky"] {
      display: none !important;
    }

    html[data-codex-modao-capture-mode="detail"] .styles__StyledRightSidePanel-sc-103a1mw-0,
    html[data-codex-modao-capture-mode="detail"] .ToggleVisibilityButtonHOC__StyledToggleWrapper-sc-10pgtyu-0:has(.styles__StyledRightSidePanel-sc-103a1mw-0),
    html[data-codex-modao-capture-mode="detail"] .styles__StyledRulerContainer-sc-73css9-0,
    html[data-codex-modao-capture-mode="detail"] .widget.tree-node.wSticky,
    html[data-codex-modao-capture-mode="detail"] [class*="StyledSticky"] {
      display: none !important;
    }

    html[data-codex-modao-capture-mode="detail"] .styles__StyledLeftPane-sc-5fx6js-0,
    html[data-codex-modao-capture-mode="detail"] .styles__StyledLeftSidePanel-sc-1i1nmxp-0,
    html[data-codex-modao-capture-mode="detail"] .mb-left-panel-container,
    html[data-codex-modao-capture-mode="detail"] .mb-left-panel,
    html[data-codex-modao-capture-mode="detail"] .list-panel,
    html[data-codex-modao-capture-mode="detail"] .ToggleVisibilityButtonHOC__StyledToggleWrapper-sc-10pgtyu-0:has(.styles__StyledLeftSidePanel-sc-1i1nmxp-0) {
      display: none !important;
    }
  `;
  return {
    mode,
    zoom: document.querySelector(".zoom-scale")?.innerText?.trim() || null
  };
})()
"""


ZOOM_CONTROL_EXPRESSION_TEMPLATE = r"""
(() => {
  const direction = "__DIRECTION__";
  const selector = direction === "out" ? ".zoom-control.zoom-out" : ".zoom-control.zoom-in";
  const control = document.querySelector(selector);
  if (!control) {
    return { ok: false, reason: "zoom_control_missing", direction };
  }
  control.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
  return {
    ok: true,
    direction,
    zoom: document.querySelector(".zoom-scale")?.innerText?.trim() || null
  };
})()
"""


def wait_for_modao_ready(session: CDPSession, timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last = {}
    while time.time() < deadline:
        last = session.evaluate(READY_EXPRESSION) or {}
        if last.get("ready"):
            return last
        if last.get("loginLike") and not last.get("hasTreeBody"):
            return last
        time.sleep(0.5)
    return last


def detect_access_mode(ready_state: dict[str, Any]) -> str:
    if ready_state.get("ready"):
        url = ready_state.get("url", "")
        if "/sharing" in url or "view_mode=read_only" in url:
            return "public"
        return "logged_in_profile"
    return "login_required"


def extract_tree(session: CDPSession) -> list[dict[str, Any]]:
    return session.evaluate(TREE_EXPRESSION) or []


def flatten_page_nodes(tree: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], ancestors: list[str]):
        name = node["name"]
        next_path = ancestors + [name]
        if node["kind"] == "page":
            flattened.append(
                {
                    "tree_path": "/".join(next_path),
                    "segments": next_path,
                    "screen_name": name,
                    "selected": bool(node.get("selected")),
                }
            )
        for child in node.get("children", []):
            walk(child, next_path)

    for root in tree:
        walk(root, [])
    return flattened


def get_selected_tree_path(session: CDPSession) -> str | None:
    path = session.evaluate(SELECTED_PATH_EXPRESSION)
    if not path:
        return None
    return "/".join(path)


def click_tree_path(session: CDPSession, segments: list[str]) -> dict[str, Any]:
    expression = CLICK_PATH_EXPRESSION_TEMPLATE.replace(
        "__SEGMENTS__",
        str(segments).replace("'", '"'),
    )
    return session.evaluate(expression) or {"ok": False, "reason": "empty_result"}


def get_view_context(session: CDPSession) -> dict[str, Any]:
    return session.evaluate(VIEW_CONTEXT_EXPRESSION) or {}


def set_capture_mode(session: CDPSession, mode: str) -> dict[str, Any]:
    expression = SET_CAPTURE_MODE_EXPRESSION_TEMPLATE.replace("__MODE__", mode)
    result = session.evaluate(expression) or {}
    time.sleep(0.25)
    return result


def click_zoom_control(session: CDPSession, direction: str) -> dict[str, Any]:
    expression = ZOOM_CONTROL_EXPRESSION_TEMPLATE.replace("__DIRECTION__", direction)
    return session.evaluate(expression) or {"ok": False, "reason": "empty_result", "direction": direction}


def _canvas_fit_metrics(context: dict[str, Any], margin: int = 16) -> tuple[bool, float]:
    canvas = context.get("canvasRect") or {}
    viewport = context.get("viewportRect") or {}
    if not canvas or not viewport:
        return False, 0.0

    safe_width = max(float(viewport["width"]) - margin * 2, 1.0)
    safe_height = max(float(viewport["height"]) - margin * 2, 1.0)
    fits = (
        float(canvas["x"]) >= float(viewport["x"]) + margin
        and float(canvas["y"]) >= float(viewport["y"]) + margin
        and float(canvas["right"]) <= float(viewport["right"]) - margin
        and float(canvas["bottom"]) <= float(viewport["bottom"]) - margin
    )
    fill = max(float(canvas["width"]) / safe_width, float(canvas["height"]) / safe_height)
    return fits, fill


def fit_canvas_to_viewport(
    session: CDPSession,
    *,
    min_fill: float,
    max_iterations: int = 12,
) -> dict[str, Any]:
    context = get_view_context(session)

    for _ in range(max_iterations):
        fits, _fill = _canvas_fit_metrics(context)
        if fits:
            break
        previous_zoom = context.get("zoomValue")
        result = click_zoom_control(session, "out")
        if not result.get("ok"):
            return context
        time.sleep(0.35)
        context = get_view_context(session)
        if context.get("zoomValue") == previous_zoom:
            break

    best_context = context
    for _ in range(max_iterations):
        fits, fill = _canvas_fit_metrics(best_context)
        if not fits:
            return best_context
        if fill >= min_fill:
            return best_context

        previous_zoom = best_context.get("zoomValue")
        result = click_zoom_control(session, "in")
        if not result.get("ok"):
            return best_context
        time.sleep(0.35)
        candidate = get_view_context(session)
        candidate_fits, candidate_fill = _canvas_fit_metrics(candidate)
        if not candidate_fits:
            click_zoom_control(session, "out")
            time.sleep(0.35)
            return get_view_context(session)
        if candidate.get("zoomValue") == previous_zoom:
            return candidate
        best_context = candidate
        if candidate_fill >= min_fill:
            return best_context

    return best_context


def wait_for_selected_path(session: CDPSession, target_path: str, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    stable_count = 0
    previous_signature = None
    while time.time() < deadline:
        context = get_view_context(session)
        selected_path = "/".join(context.get("selectedPath") or [])
        signature = (
            selected_path,
            context.get("zoomPercent"),
            (context.get("canvasRect") or {}).get("text"),
            (context.get("canvasRect") or {}).get("width"),
            (context.get("canvasRect") or {}).get("height"),
        )
        if selected_path == target_path and signature == previous_signature:
            stable_count += 1
            if stable_count >= 2:
                return True
        else:
            stable_count = 0
        previous_signature = signature
        time.sleep(0.5)
    return False


def infer_surface(tree_path: str) -> str:
    first = tree_path.split("/", 1)[0]
    if first == "运营端":
        return "运营端"
    if "商家版" in tree_path:
        return "商家版"
    if "游客版" in tree_path:
        return "游客版"
    if first == "移动端":
        return "移动端"
    return "unknown"


def infer_state(screen_name: str) -> str:
    if "失败" in screen_name:
        return "failure"
    if "成功" in screen_name:
        return "success"
    if any(keyword in screen_name for keyword in ["提示", "确认", "弹窗", "弹层", "弹框"]):
        return "modal"
    return "default"
