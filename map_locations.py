"""
map_locations.py

Attempts to find each room's REAL physical location on the floor plan
drawing, not just where its name is printed in a legend. This floor plan
color-codes each of its 4 numbered legend panels (North Wing = pink,
Student Resource Building = green, Middle House = blue, South Wing =
orange), and stamps the SAME colored number directly on the room's shape
in the drawing -- e.g. a pink "4" on a building outline = North Wing
legend item 4 (FITZGERALD HALL).

Many of these drawing numerals are too small for a normal OCR pass over
the whole image to catch (same issue we hit with the legend bullets), so
this script finds them a different way:
  1. Build a color mask for each wing's reference color (pixels close to
     that exact RGB value).
  2. Run connected-component labelling on each mask to find distinct
     blobs, then filter out ones that are the wrong shape/size to be a
     digit (this is what separates a numeral from the much longer, thinner
     strokes of the room outlines drawn in the same color).
  3. Merge adjacent blobs (for multi-digit numbers like "14").
  4. Crop + zoom into each surviving candidate and run PaddleOCR on just
     that patch to read the actual digit.
  5. Match each wing's digits, by value, to that wing's legend list (which
     is already in 1..N order) -- digit N is legend item N.

Usage:
    venv\\Scripts\\python.exe map_locations.py [path\\to\\floorplan.png]
"""

import os
import re
import sys

os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from scipy import ndimage

from find_rooms import find_rooms, write_markdown, write_json, OUTPUT_DIR
from clean_rooms import read_bullet_numbers, BULLET_RE

WING_COLORS = {
    "North Wing": (236, 0, 140),
    "Student Resource Building": (0, 180, 119),
    "Middle House": (0, 133, 202),
    "South Wing": (247, 148, 45),
}
COLOR_MATCH_THRESHOLD = 85  # max per-pixel RGB distance to count as this wing's color

# Shape filter for "is this blob plausibly a single digit, not a wall outline":
MIN_SIZE, MAX_SIZE = 8, 32       # width and height, in pixels
MAX_ASPECT = 4.5                 # longer side / shorter side -- a lone "1" is naturally this thin
MERGE_GAP = 6                    # max horizontal gap (px) to join into one multi-digit number
MERGE_Y_OVERLAP = 0.5            # min fraction of vertical overlap to join two blobs

CROP_PADDING = 4
UPSCALE = 10
DIGIT_RE = re.compile(r"^\d{1,2}$")
DIGIT_CONFIDENCE = 0.5

DEBUG_IMAGE = os.path.join(OUTPUT_DIR, "location_debug.png")


def color_distance(a, b):
    return sum((int(x) - int(y)) ** 2 for x, y in zip(a, b)) ** 0.5


def classify_wing_by_color(rgb):
    best_wing, best_dist = None, None
    for wing, ref in WING_COLORS.items():
        dist = color_distance(rgb, ref)
        if best_dist is None or dist < best_dist:
            best_wing, best_dist = wing, dist
    return best_wing if best_dist <= COLOR_MATCH_THRESHOLD else None


def ink_color(img, box):
    x0, y0, x1, y1 = box
    crop = img.crop((max(0, x0), max(0, y0), x1, y1))
    pixels = list(crop.getdata())
    if not pixels:
        return (255, 255, 255)
    return max(pixels, key=lambda p: max(p) - min(p))


def find_digit_blobs(arr, ref_color, allow_merge=True):
    """Returns a list of (x0,y0,x1,y1) candidate boxes for single digits in
    this wing's color, after filtering out wall-outline-shaped blobs and
    merging adjacent same-row blobs into multi-digit groups.

    `allow_merge=False` skips the merge step entirely -- a wing whose
    legend never goes past 9 has no real 2-digit numbers, so two separate
    single-digit markers that just happen to sit close together (this
    floor plan prints them tightly) would otherwise get wrongly fused into
    one unreadable blob."""
    dist = np.sqrt(((arr.astype(np.int32) - np.array(ref_color)) ** 2).sum(axis=2))
    mask = dist < COLOR_MATCH_THRESHOLD

    labeled, n = ndimage.label(mask, structure=np.ones((3, 3)))
    boxes = []
    for sl in ndimage.find_objects(labeled):
        if sl is None:
            continue
        y_sl, x_sl = sl
        h = y_sl.stop - y_sl.start
        w = x_sl.stop - x_sl.start
        if not (MIN_SIZE <= h <= MAX_SIZE and 3 <= w <= MAX_SIZE):
            continue
        if max(w, h) / max(1, min(w, h)) > MAX_ASPECT:
            continue
        boxes.append([x_sl.start, y_sl.start, x_sl.stop, y_sl.stop])

    if not allow_merge:
        return [tuple(b) for b in boxes]

    # merge horizontally-adjacent boxes (multi-digit numbers)
    boxes.sort(key=lambda b: b[0])
    merged = []
    for b in boxes:
        if merged:
            last = merged[-1]
            gap = b[0] - last[2]
            overlap = min(b[3], last[3]) - max(b[1], last[1])
            min_h = min(b[3] - b[1], last[3] - last[1])
            if 0 <= gap <= MERGE_GAP and overlap >= MERGE_Y_OVERLAP * min_h:
                last[0] = min(last[0], b[0])
                last[1] = min(last[1], b[1])
                last[2] = max(last[2], b[2])
                last[3] = max(last[3], b[3])
                continue
        merged.append(list(b))
    return [tuple(b) for b in merged]


def read_digit(ocr, img, box, crop_dir):
    x0, y0, x1, y1 = box
    x0, y0 = max(0, x0 - CROP_PADDING), max(0, y0 - CROP_PADDING)
    x1, y1 = x1 + CROP_PADDING, y1 + CROP_PADDING
    crop = img.crop((x0, y0, x1, y1))
    crop = crop.resize((crop.width * UPSCALE, crop.height * UPSCALE), Image.LANCZOS)
    crop = ImageOps.autocontrast(crop, cutoff=1)
    os.makedirs(crop_dir, exist_ok=True)
    path = os.path.join(crop_dir, f"digit_{x0}_{y0}.png")
    crop.save(path)
    for res in ocr.predict(path):
        texts, scores = res["rec_texts"], res["rec_scores"]
        candidates = [(t, s) for t, s in zip(texts, scores) if DIGIT_RE.match(t)]
        if candidates:
            return max(candidates, key=lambda c: c[1])
    return None


def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else "floorplan.png"

    from paddleocr import PaddleOCR
    print("Loading PaddleOCR (English, CPU)...")
    ocr = PaddleOCR(
        lang="en", device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    floor_headers, rooms, _ = find_rooms(image_path, ocr=ocr, return_groups=True)

    img = Image.open(image_path).convert("RGB")
    arr = np.array(img)

    # 1. Tag each room with its wing, by the color of its own label text.
    for room in rooms:
        room["wing"] = classify_wing_by_color(ink_color(img, (room["box"]["x0"], room["box"]["y0"], room["box"]["x1"], room["box"]["y1"])))

    by_wing = {}
    for room in rooms:
        if room["wing"]:
            by_wing.setdefault(room["wing"], []).append(room)

    print("\n=== Rooms tagged by wing (via legend text color) ===")
    for wing, members in by_wing.items():
        print(f"  {wing}: {len(members)} rooms -> {[r['name'] for r in members]}")

    # 1b. Read each wing-tagged room's OWN legend bullet number directly --
    # do NOT assume position order. Some same-colored text (floor headers
    # like "OFFICES S1-8", the wing's own title, or halls named directly on
    # the map like "COBDEN HALL") has no bullet at all, and would throw off
    # a simple position-based count if we just numbered members 1, 2, 3...
    #
    # Only even ATTEMPT a bullet read for rooms sitting in that wing's
    # legend column (its members' most common left edge, x0) -- a hall
    # named directly on the map (e.g. "CARLOVIAN DINING HALL") sits at a
    # very different x0 and has no real bullet next to it; cropping "to its
    # left" there just grabs whatever stray digit happens to be nearby and
    # produces a confidently-wrong reading, not a missing one.
    # Some same-colored text is categorically never a bulleted legend entry
    # in this document -- the wing's own title, and the "OFFICES <range>"
    # floor-level labels (which describe a whole floor, not one room).
    NEVER_BULLETED = set(WING_COLORS.keys()) | {"NORTH WING", "SOUTH WING", "MIDDLE HOUSE", "STUDENT RESOURCE BUILDING"}

    def is_never_bulleted(name):
        return name.upper() in NEVER_BULLETED or name.upper().startswith("OFFICES")

    from collections import Counter

    in_column, out_of_column = [], []
    for members in by_wing.values():
        candidates = [m for m in members if not is_never_bulleted(m["name"])]
        x0_counts = Counter(round(m["_group"][0]["x0"] / 10) * 10 for m in candidates)
        # a real legend column has more than one entry at (roughly) the same
        # left edge -- this floor plan's Middle House legend happens to be
        # split across TWO side-by-side text blocks, so there can be more
        # than one valid column per wing.
        valid_cols = {x0 for x0, count in x0_counts.items() if count >= 2}
        for room in candidates:
            entry_x0 = round(room["_group"][0]["x0"] / 10) * 10
            (in_column if entry_x0 in valid_cols else out_of_column).append(room)
        out_of_column.extend(m for m in members if is_never_bulleted(m["name"]))

    first_line_entries = [room["_group"][0] for room in in_column]
    first_lines = {id(room["_group"][0]): room for room in in_column}
    bullet_readings = read_bullet_numbers(first_line_entries, image_path=image_path, ocr=ocr)

    print(f"\n({len(out_of_column)} room(s) sit outside their wing's legend column -- skipped bullet check: "
          f"{[r['name'] for r in out_of_column]})")

    room_bullet_value = {}
    for first_entry_id, room in first_lines.items():
        reading = bullet_readings.get(first_entry_id)
        if reading and BULLET_RE.match(reading[0]) and reading[1] >= 0.6:
            room_bullet_value[id(room)] = int(reading[0].rstrip(".:"))

    # Two specific bullets where no crop margin we tried gives a reliable
    # answer: every margin either returns a confidently WRONG digit, or an
    # empty read -- there's no automatic way to tell "confident" from
    # "confidently wrong" here. Verified by direct visual inspection of the
    # source image (both numerals are perfectly legible to the eye): "11"
    # for IT ROOM, "7" for TEACHING PLACEMENT OFFICE (both Middle House).
    MANUAL_BULLET_OVERRIDES = {
        "IT ROOM": 11,
        "TEACHING PLACEMENT OFFICE": 7,
    }
    for room in rooms:
        if room["name"] in MANUAL_BULLET_OVERRIDES:
            room_bullet_value[id(room)] = MANUAL_BULLET_OVERRIDES[room["name"]]

    print("\n=== Legend bullet numbers read directly from each room's own line ===")
    for members in by_wing.values():
        for room in members:
            v = room_bullet_value.get(id(room))
            print(f"  {'#' + str(v) if v is not None else '(no bullet)'}: {room['name']}")

    for room in rooms:
        del room["_group"]

    # 2. Find and read digit blobs drawn on the map, per wing.
    crop_dir = os.path.join(OUTPUT_DIR, "_digit_crops")
    digit_matches = {}  # wing -> {value: [box, ...]}
    for wing, ref_color in WING_COLORS.items():
        allow_merge = len(by_wing.get(wing, [])) > 9  # only Middle House's legend reaches double digits
        candidates = find_digit_blobs(arr, ref_color, allow_merge=allow_merge)
        print(f"\n{wing}: {len(candidates)} candidate blob(s) after shape filtering")
        readings = []
        for box in candidates:
            reading = read_digit(ocr, img, box, crop_dir)
            if reading and reading[1] >= DIGIT_CONFIDENCE:
                readings.append((box, int(reading[0]), reading[1]))
                print(f"  box={box} -> '{reading[0]}' (confidence {reading[1]:.3f})")

        # A lone single digit sitting right next to a multi-digit reading
        # that starts with that same digit (e.g. a '1' a few px from a '10')
        # is very likely a fragment of that same number -- our box-merging
        # didn't join them, and OCR then mis-split it into two "numbers".
        # Drop the lone digit in that case rather than treat it as real.
        dropped = set()
        for i, (box, value, _) in enumerate(readings):
            if value > 9:
                continue  # only single digits can be a fragment of another
            for j, (other_box, other_value, _) in enumerate(readings):
                if i == j or other_value <= 9:
                    continue
                gap = max(other_box[0] - box[2], box[0] - other_box[2])
                if gap <= 10 and str(other_value).startswith(str(value)):
                    dropped.add(i)
        if dropped:
            print(f"  (dropping {len(dropped)} lone digit(s) that look like fragments of a nearby multi-digit number)")

        values = {}
        for i, (box, value, conf) in enumerate(readings):
            if i in dropped:
                continue
            values.setdefault(value, []).append((box, conf))
        # highest-confidence reading first -- a stray non-digit blob that
        # happens to OCR as a digit tends to score lower than a real one
        for value in values:
            values[value].sort(key=lambda t: -t[1])
            values[value] = [b for b, _ in values[value]]
        digit_matches[wing] = values

    # 3. Match each room's OWN bullet number (read in step 1b) to a digit
    # blob of the same value, found on the drawing in that same wing's color.
    for wing, members in by_wing.items():
        values = digit_matches.get(wing, {})
        for room in members:
            v = room_bullet_value.get(id(room))
            if v is None:
                continue
            boxes = values.get(v)
            if boxes:
                bx = boxes[0]
                room["location_box"] = {"x0": bx[0], "y0": bx[1], "x1": bx[2], "y1": bx[3]}
                if len(boxes) > 1:
                    room["location_box_alt"] = [
                        {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]} for b in boxes[1:]
                    ]

    # 4. Some rooms are named directly on the drawing itself, not through a
    # numbered legend (e.g. "COBDEN HALL" printed right on its own shape).
    # For those, the room's own text-label box already IS a reasonable
    # stand-in for its location -- no legend/digit matching needed.
    #
    # Crucially, this must NEVER apply to a legend member (anything in
    # `in_column`): its own box sits inside the side legend panel, not on
    # the drawing, so if its bullet match failed, falling back to that box
    # would silently label it with the wrong kind of location entirely
    # (legend text position passed off as a real room location).
    in_column_ids = {id(room) for room in in_column}
    NOT_A_ROOM = NEVER_BULLETED | {"CAMPUS", "SMOKING", "MAN ENTRANCE"}
    # The crest/logo text is 3-4 OCR lines stacked vertically ("CARLOW",
    # "COLLEGE", "ST.PATRICK'S", "Third Level Education"); depending on
    # exactly how the merge step groups them, it can come out as one block
    # or split across a couple -- match by prefix so either way is caught.
    NOT_A_ROOM_PREFIXES = ("CARLOW COLLEGE", "ST.PATRICK'S")
    direct_label_count = 0
    for room in rooms:
        if "location_box" in room or id(room) in in_column_ids:
            continue
        name_upper = room["name"].upper()
        if (
            name_upper in NOT_A_ROOM
            or name_upper.startswith("OFFICES")
            or name_upper.startswith(NOT_A_ROOM_PREFIXES)
        ):
            continue
        room["location_box"] = dict(room["box"])
        direct_label_count += 1
    print(f"\n{direct_label_count} more room(s) matched using their own on-map label position "
          f"(named directly on the drawing, not through a numbered legend)")

    matched = sum(1 for r in rooms if "location_box" in r)
    print(f"\n=== {matched} / {len(rooms)} rooms matched to a real drawing location ===")
    for r in rooms:
        tag = "OK " if "location_box" in r else "-- "
        print(f"  [{tag}] ({r.get('wing','?')}) {r['name']}")

    # Debug image: draw the matched location boxes directly on the floor plan.
    debug_img = img.copy()
    draw = ImageDraw.Draw(debug_img)
    for r in rooms:
        if "location_box" in r:
            b = r["location_box"]
            draw.rectangle((b["x0"] - 2, b["y0"] - 2, b["x1"] + 2, b["y1"] + 2), outline=(255, 0, 0), width=2)
    debug_img.save(DEBUG_IMAGE)
    print(f"\nSaved {DEBUG_IMAGE} (red boxes = matched room locations, for visual verification)")

    write_markdown(os.path.join(OUTPUT_DIR, "rooms.md"), image_path, floor_headers, rooms)
    write_json(os.path.join(OUTPUT_DIR, "rooms.json"), image_path, floor_headers, rooms)
    print(f"Updated rooms.md and rooms.json with location data")


if __name__ == "__main__":
    main()
