#!/usr/bin/env python3

import hashlib
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from chrome_cdp import CDPSession


def slugify(value: str, *, max_prefix: int = 80) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
    prefix = cleaned[:max_prefix] or "item"
    suffix = hashlib.sha1(value.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}-{suffix}"


def capture_overview(session: CDPSession, output_path: Path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(session.capture_screenshot(full_page=False))


def capture_detail_from_session(
    session: CDPSession,
    output_path: Path,
    *,
    canvas_rect: dict | None,
    viewport: dict | None,
    padding: int = 12,
) -> bool:
    rect = canvas_rect or {}
    viewport = viewport or {}
    if not rect or not viewport.get("innerWidth") or not viewport.get("innerHeight"):
        return False

    x = max(0.0, float(rect["x"]) - padding)
    y = max(0.0, float(rect["y"]) - padding)
    width = max(1.0, float(rect["width"]) + padding * 2)
    height = max(1.0, float(rect["height"]) + padding * 2)
    max_width = max(1.0, float(viewport["innerWidth"]) - x)
    max_height = max(1.0, float(viewport["innerHeight"]) - y)
    clip = {
        "x": x,
        "y": y,
        "width": min(width, max_width),
        "height": min(height, max_height),
        "scale": 1,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(session.capture_screenshot(full_page=False, clip=clip))
    return True


def _fallback_crop_box(image: Image.Image, *, viewport: dict | None = None) -> tuple[int, int, int, int]:
    smart_box = _content_aware_crop_box(image, viewport=viewport)
    if smart_box:
        return smart_box

    left = max(0, int(image.width * 0.12))
    top = max(0, int(image.height * 0.08))
    right = min(image.width, int(image.width * 0.78))
    bottom = min(image.height, int(image.height * 0.92))
    return left, top, right, bottom


def _content_aware_crop_box(image: Image.Image, *, viewport: dict | None = None) -> tuple[int, int, int, int] | None:
    rgb = image.convert("RGB")
    width, height = rgb.size
    viewport = viewport or {}
    if viewport.get("leftPanelRight") and viewport.get("innerWidth"):
        scale_x = width / max(float(viewport["innerWidth"]), 1.0)
        search_left = max(0, int(float(viewport["leftPanelRight"]) * scale_x) + 120)
    else:
        search_left = max(0, int(width * 0.24))
    search_top = max(0, int(height * 0.05))
    search_right = min(width, int(width * 0.78))
    search_bottom = min(height, int(height * 0.95))
    if search_right - search_left < 80 or search_bottom - search_top < 80:
        return None

    crop = rgb.crop((search_left, search_top, search_right, search_bottom))
    sample_points = [
        (5, 5),
        (crop.width - 6, 5),
        (5, crop.height - 6),
        (crop.width - 6, crop.height - 6),
    ]
    samples = [crop.getpixel(point) for point in sample_points]
    bg = tuple(int(sum(channel) / len(samples)) for channel in zip(*samples))

    bbox = None
    threshold = 24
    step = 2
    for y in range(0, crop.height, step):
        for x in range(0, crop.width, step):
            pixel = crop.getpixel((x, y))
            diff = sum(abs(pixel[i] - bg[i]) for i in range(3))
            if diff < threshold:
                continue
            if bbox is None:
                bbox = [x, y, x, y]
            else:
                bbox[0] = min(bbox[0], x)
                bbox[1] = min(bbox[1], y)
                bbox[2] = max(bbox[2], x)
                bbox[3] = max(bbox[3], y)

    if not bbox:
        return None

    left, top, right, bottom = bbox
    if right - left < 120 or bottom - top < 120:
        return None

    padding = 20
    return (
        max(0, search_left + left - padding),
        max(0, search_top + top - padding),
        min(width, search_left + right + padding),
        min(height, search_top + bottom + padding),
    )


def capture_detail(
    overview_path: Path,
    output_path: Path,
    *,
    canvas_rect: dict | None,
    viewport: dict | None,
    padding: int = 24,
):
    image = Image.open(overview_path)
    viewport = viewport or {}
    rect = canvas_rect or {}
    if rect and viewport.get("innerWidth") and viewport.get("innerHeight"):
        scale_x = image.width / max(float(viewport["innerWidth"]), 1.0)
        scale_y = image.height / max(float(viewport["innerHeight"]), 1.0)
        left = max(0, int((rect["x"] - padding) * scale_x))
        top = max(0, int((rect["y"] - padding) * scale_y))
        right = min(image.width, int((rect["x"] + rect["width"] + padding) * scale_x))
        bottom = min(image.height, int((rect["y"] + rect["height"] + padding) * scale_y))
        if right - left < 50 or bottom - top < 50:
            box = _fallback_crop_box(image, viewport=viewport)
        else:
            box = (left, top, right, bottom)
    else:
        box = _fallback_crop_box(image, viewport=viewport)
    crop = image.crop(box)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output_path)


def copy_artifact(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def build_compare_image(before_path: Path, after_path: Path, output_path: Path, *, before_label: str, after_label: str):
    before = Image.open(before_path).convert("RGB")
    after = Image.open(after_path).convert("RGB")
    max_width = 1400

    def resized(image: Image.Image) -> Image.Image:
        if image.width <= max_width:
            return image
        ratio = max_width / image.width
        return image.resize((int(image.width * ratio), int(image.height * ratio)))

    before = resized(before)
    after = resized(after)
    height = max(before.height, after.height)
    canvas = Image.new("RGB", (before.width + after.width + 60, height + 80), "white")
    canvas.paste(before, (20, 60))
    canvas.paste(after, (before.width + 40, 60))
    draw = ImageDraw.Draw(canvas)
    draw.text((20, 20), before_label, fill="black")
    draw.text((before.width + 40, 20), after_label, fill="black")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)
