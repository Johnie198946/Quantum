#!/usr/bin/env python3

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def box_dict(box):
    x, y, w, h = (int(value) for value in box)
    return {"x": x, "y": y, "width": w, "height": h}


def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    left, top = max(ax, bx), max(ay, by)
    right, bottom = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    intersection = max(0, right - left) * max(0, bottom - top)
    union = aw * ah + bw * bh - intersection
    return intersection / union if union else 0


def dedupe(boxes, threshold=0.72):
    kept = []
    for box in sorted(boxes, key=lambda item: item[2] * item[3], reverse=True):
        if any(iou(box, existing) >= threshold for existing in kept):
            continue
        kept.append(box)
    return sorted(kept, key=lambda item: (item[1], item[0]))


def locate_phone(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 45, 145)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= width * 0.72 and h >= height * 0.72 and 0.36 <= w / h <= 0.58:
            candidates.append((x, y, w, h))
    if not candidates:
        return 0, 0, width, height
    return max(candidates, key=lambda item: item[2] * item[3])


def screen_from_phone(phone, image_shape):
    x, y, w, h = phone
    inset_x = max(9, round(w * 0.038))
    inset_y = max(9, round(w * 0.038))
    image_h, image_w = image_shape[:2]
    sx = max(0, x + inset_x)
    sy = max(0, y + inset_y)
    sw = min(image_w - sx, w - inset_x * 2)
    sh = min(image_h - sy, h - inset_y * 2)
    return sx, sy, sw, sh


def shifted_text(page, screen_box):
    sx, sy, sw, sh = screen_box
    output = []
    for item in page.get("text", []):
        box = item["box"]
        x = max(0, box["x"] - sx)
        y = max(0, box["y"] - sy)
        right = min(sw, box["x"] + box["width"] - sx)
        bottom = min(sh, box["y"] + box["height"] - sy)
        if right <= x or bottom <= y:
            continue
        output.append({**item, "box": box_dict((x, y, right - x, bottom - y))})
    return output


def component_boxes(screen, page_rectangles, screen_box):
    height, width = screen.shape[:2]
    sx, sy, _, _ = screen_box
    boxes = []
    for item in page_rectangles:
        raw = item["box"]
        box = (raw["x"] - sx, raw["y"] - sy, raw["width"], raw["height"])
        x, y, w, h = box
        if x >= 0 and y >= 0 and x + w <= width and y + h <= height and w >= 44 and h >= 24:
            if w < width * 0.96 and h < height * 0.92:
                boxes.append(box)

    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 38, 125)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if w >= 52 and h >= 24 and area >= 1700 and w < width * 0.97 and h < height * 0.90:
            if h <= height * 0.58:
                boxes.append((x, y, w, h))
    return dedupe(boxes)[:24]


def icon_boxes(screen, text_items):
    height, width = screen.shape[:2]
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    text_mask = np.zeros_like(gray)
    for item in text_items:
        box = item["box"]
        x = max(0, box["x"] - 3)
        y = max(0, box["y"] - 3)
        right = min(width, box["x"] + box["width"] + 3)
        bottom = min(height, box["y"] + box["height"] + 3)
        cv2.rectangle(text_mask, (x, y), (right, bottom), 255, -1)
    marks = (((gray < 118) | (hsv[:, :, 1] > 105)) & (text_mask == 0)).astype(np.uint8) * 255
    marks = cv2.morphologyEx(marks, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(marks, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if y < 42 or y > height - 42:
            continue
        if 7 <= w <= 68 and 7 <= h <= 68 and w * h >= 80:
            boxes.append((max(0, x - 4), max(0, y - 4), min(width - x + 4, w + 8), min(height - y + 4, h + 8)))
    return dedupe(boxes, 0.55)[:28]


def split_dense_box(mask, box):
    x, y, w, h = box
    if w < 78 and h < 78:
        return [box]
    crop = mask[y:y + h, x:x + w]
    for axis, length, other in ((0, h, w), (1, w, h)):
        projection = np.count_nonzero(crop, axis=axis)
        limit = max(1, round(length * 0.035))
        gaps = np.where(projection <= limit)[0]
        runs = []
        if gaps.size:
            start = previous = int(gaps[0])
            for value in gaps[1:]:
                value = int(value)
                if value != previous + 1:
                    runs.append((start, previous + 1))
                    start = value
                previous = value
            runs.append((start, previous + 1))
        for start, end in sorted(runs, key=lambda item: item[1] - item[0], reverse=True):
            cut = (start + end) // 2
            if start < 3 or end > other - 3 or cut < 34 or other - cut < 34:
                continue
            if axis == 0:
                first, second = (x, y, cut, h), (x + cut, y, w - cut, h)
            else:
                first, second = (x, y, w, cut), (x, y + cut, w, h - cut)
            return split_dense_box(mask, first) + split_dense_box(mask, second)
    return [box]


def visual_asset_boxes(screen, text_items):
    height, width = screen.shape[:2]
    lab = cv2.cvtColor(screen, cv2.COLOR_BGR2LAB)
    gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mean = cv2.blur(gray, (9, 9))
    mean_square = cv2.blur(gray * gray, (9, 9))
    deviation = np.sqrt(np.maximum(mean_square - mean * mean, 0))
    hsv = cv2.cvtColor(screen, cv2.COLOR_BGR2HSV)
    saturation = hsv[:, :, 1]
    chroma = np.maximum(lab[:, :, 1], lab[:, :, 2]) - np.minimum(lab[:, :, 1], lab[:, :, 2])
    mask = (((deviation > 16) & (saturation > 14)) | ((deviation > 30) & (saturation > 5)) | ((chroma > 24) & (deviation > 10))).astype(np.uint8) * 255
    for item in text_items:
        box = item["box"]
        x = max(0, box["x"] - 3)
        y = max(0, box["y"] - 3)
        right = min(width, box["x"] + box["width"] + 3)
        bottom = min(height, box["y"] + box["height"] + 3)
        cv2.rectangle(mask, (x, y), (right, bottom), 0, -1)
    mask[:42, :] = 0
    mask[-42:, :] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=1)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    boxes = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if w >= 28 and h >= 28 and area >= 180 and w * h <= width * height * 0.5:
            ratio = w / h
            density = area / (w * h)
            if 0.24 <= ratio <= 4.2 and density >= 0.12:
                boxes.extend(split_dense_box(mask, (x, y, w, h)))
    boxes = [
        (max(0, x - 3), max(0, y - 3), min(width - x + 3, w + 6), min(height - y + 3, h + 6))
        for x, y, w, h in boxes if w >= 28 and h >= 28
    ]
    return dedupe(boxes, 0.58)[:12]


def photo_like_components(screen, boxes):
    output = []
    for x, y, w, h in boxes:
        if w < 40 or h < 40:
            continue
        crop = screen[y:y + h, x:x + w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        saturation = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 1]
        if float(gray.std()) >= 26 and float(saturation.mean()) >= 18:
            output.append((x, y, w, h))
    return output


def write_crops(screen, boxes, directory, prefix):
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for index, (x, y, w, h) in enumerate(boxes, start=1):
        filename = f"{prefix}{index:02d}.png"
        cv2.imwrite(str(directory / filename), screen[y:y + h, x:x + w])
        records.append({"file": str((directory / filename).as_posix()), "box": box_dict((x, y, w, h))})
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pages_dir", type=Path)
    parser.add_argument("vision_json", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    vision = json.loads(args.vision_json.read_text())
    page_data = {item["page"]: item for item in vision["pages"]}
    manifest = {"source": str(args.pages_dir), "pageCount": 0, "pages": []}
    inventory = ["# Quantum iOS V3-V5 逐页视觉与资产清单", ""]

    for relative in sorted(page_data):
        source = args.pages_dir / relative
        image = cv2.imread(str(source), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"cannot read {source}")
        phone = locate_phone(image)
        screen_box = screen_from_phone(phone, image.shape)
        sx, sy, sw, sh = screen_box
        screen = image[sy:sy + sh, sx:sx + sw]
        page = page_data[relative]
        texts = shifted_text(page, screen_box)
        components = component_boxes(screen, page.get("rectangles", []), screen_box)
        icons = icon_boxes(screen, texts)
        assets = dedupe(visual_asset_boxes(screen, texts) + photo_like_components(screen, components), 0.72)[:18]

        page_dir = args.output_dir / Path(relative).with_suffix("")
        page_dir.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(page_dir / "screen.png"), screen)
        component_records = write_crops(screen, components, page_dir / "components", "component-")
        icon_records = write_crops(screen, icons, page_dir / "icons", "icon-")
        asset_records = write_crops(screen, assets, page_dir / "images", "image-")

        record = {
            "page": relative,
            "source": str(source),
            "phoneBox": box_dict(phone),
            "screenBox": box_dict(screen_box),
            "screen": str((page_dir / "screen.png").as_posix()),
            "text": texts,
            "components": component_records,
            "icons": icon_records,
            "images": asset_records,
        }
        manifest["pages"].append(record)
        values = " / ".join(item["value"] for item in texts[:8]) or "未识别到可靠文字"
        inventory.extend([
            f"## `{relative}`",
            "",
            f"- 识别文字：{values}",
            f"- 切片：组件 {len(components)}，图标候选 {len(icons)}，图片/插画候选 {len(assets)}。",
            f"- 屏幕参考：`{(page_dir / 'screen.png').as_posix()}`",
            "",
        ])
        print(f"assets {len(manifest['pages'])}/{len(page_data)}: {relative}")

    manifest["pageCount"] = len(manifest["pages"])
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    (args.output_dir / "PAGE-INVENTORY.md").write_text("\n".join(inventory))


if __name__ == "__main__":
    main()
