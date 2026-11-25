"""
find_rooms.py

THE actual "campus management" feature: give it a floor plan image, it gives
back a list of the rooms/classrooms on it. One command, one script -- this
is what test_ocr.py + clean_rooms.py do across two steps, combined into one.

Usage:
    venv\\Scripts\\python.exe find_rooms.py [path\\to\\floorplan.png]

(defaults to floorplan.png in this folder if no path is given)

Pipeline (see clean_rooms.py for the detail on each step):
  1. Run PaddleOCR (English, CPU) on the image -> raw text + confidence + box
     for every label it finds.
  2. Drop low-confidence / junk reads; split floor headers and room-number
     labels from room/area names.
  3. Merge room-name lines that are really one label wrapped across several
     printed lines, using each line's position.
  4. For ambiguous cases, re-crop and re-read the small area where this kind
     of floor plan prints a numbered bullet next to each legend entry, to
     confirm where one entry ends and the next begins.
  5. Fix "squished" words (two real words recognized with no space between
     them) using dictionary-based word segmentation.
"""

import json
import os
import sys

os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PIL import Image
from paddleocr import PaddleOCR

from clean_rooms import (
    CONFIDENCE_THRESHOLD,
    classify,
    group_wrapped_lines,
    read_bullet_numbers,
    apply_bullet_splits,
    fix_squished_words,
    dedup_keep_order,
)

OUTPUT_DIR = "output"


def entries_from_ocr_result(res):
    entries = []
    for text, score, box in zip(res["rec_texts"], res["rec_scores"], res["rec_boxes"]):
        text = text.strip()
        if not text or score < CONFIDENCE_THRESHOLD:
            continue
        x0, y0, x1, y1 = (int(v) for v in box)  # numpy ints from the live OCR result -> plain int, for JSON
        entries.append({"text": text, "score": score, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return entries


def _union_box(entries):
    return {
        "x0": min(e["x0"] for e in entries),
        "y0": min(e["y0"] for e in entries),
        "x1": max(e["x1"] for e in entries),
        "y1": max(e["y1"] for e in entries),
    }


def _dedup_rooms_keep_first(rooms):
    seen = set()
    out = []
    for room in rooms:
        key = room["name"].upper()
        if key not in seen:
            seen.add(key)
            out.append(room)
    return out


def find_rooms(image_path, ocr=None, verbose=True, return_groups=False):
    """Runs the full pipeline on one floor plan image and returns
    (floor_headers, rooms, number_labels), where each item in `rooms` is
    {"name": ..., "box": {"x0","y0","x1","y1"}} -- the box is where the
    room's TEXT LABEL sits on the image, in pixels. For rooms labelled
    directly on the drawing (e.g. "FITZGERALD HALL" printed inside its own
    shape) this box is roughly the room's location. For rooms that only
    appear in a numbered legend panel (most of them, e.g. "5  WILLIAMS
    HALL"), this box is the legend text's position, NOT the actual room's
    position on the floor plan -- OCR alone can't tell us where the room
    itself is outlined, only where its name is printed. Mapping legend
    entries to their real room shape would need a separate step (e.g.
    matching the legend's bullet number to the same number stamped on the
    drawing, or manually tracing room outlines)."""
    if ocr is None:
        if verbose:
            print("Loading PaddleOCR (English, CPU)...")
        ocr = PaddleOCR(
            lang="en",
            device="cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

    if verbose:
        print(f"Running OCR on {image_path} ...")
    results = list(ocr.predict(image_path))
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for res in results:
        res.save_to_img(OUTPUT_DIR)

    entries = [e for res in results for e in entries_from_ocr_result(res)]

    floor_headers, number_labels, room_name_entries = [], [], []
    for e in entries:
        kind = classify(e["text"])
        if kind == "floor_header":
            floor_headers.append(e["text"])
        elif kind == "number_label":
            number_labels.append(e["text"])
        elif kind == "junk":
            continue
        else:
            room_name_entries.append(e)

    groups = group_wrapped_lines(room_name_entries)
    needs_check = [e for g in groups if len(g) > 1 for e in g[1:]]
    readings = read_bullet_numbers(needs_check, image_path=image_path, ocr=ocr)
    groups, _ = apply_bullet_splits(groups, readings)

    rooms = [
        {"name": fix_squished_words(" ".join(e["text"] for e in g)), "box": _union_box(g), "_group": g}
        for g in groups
    ]
    rooms = _dedup_rooms_keep_first(rooms)
    floor_headers = dedup_keep_order(floor_headers)

    if return_groups:
        return floor_headers, rooms, number_labels
    for room in rooms:
        del room["_group"]
    return floor_headers, rooms, number_labels


def write_markdown(path, image_path, floor_headers, rooms):
    title = os.path.splitext(os.path.basename(image_path))[0].replace("_", " ").title()
    lines = [f"# {title} — Room List", ""]
    lines.append(f"*Generated from `{image_path}` using PaddleOCR.*")
    lines.append("")
    lines.append("## Floors")
    lines.append("")
    for t in floor_headers:
        lines.append(f"- {t}")
    lines.append("")
    lines.append(f"## Rooms / Classrooms ({len(rooms)})")
    lines.append("")
    for r in rooms:
        lines.append(f"- {r['name']}")
    lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def write_json(path, image_path, floor_headers, rooms):
    width, height = Image.open(image_path).size
    data = {
        "_note": (
            "Each room's box is where its TEXT LABEL sits on the source "
            "image (pixels), not necessarily the room's full outline on "
            "the floor plan -- see find_rooms()'s docstring."
        ),
        "source_image": image_path,
        "image_size": {"width": width, "height": height},
        "floors": floor_headers,
        "rooms": rooms,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else "floorplan.png"
    floor_headers, rooms, _ = find_rooms(image_path)

    print(f"\n=== Floors found on {image_path} ({len(floor_headers)}) ===")
    for t in floor_headers:
        print(f"  {t}")

    print(f"\n=== Rooms / classrooms found ({len(rooms)}) ===")
    for r in rooms:
        print(f"  {r['name']}")

    md_path = os.path.join(OUTPUT_DIR, "rooms.md")
    write_markdown(md_path, image_path, floor_headers, rooms)
    print(f"\nSaved to {md_path}")

    json_path = os.path.join(OUTPUT_DIR, "rooms.json")
    write_json(json_path, image_path, floor_headers, rooms)
    print(f"Saved to {json_path} (room names + their label positions, for a future clickable layout)")


if __name__ == "__main__":
    main()
