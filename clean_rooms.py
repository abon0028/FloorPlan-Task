"""
clean_rooms.py

Turns the raw OCR output (output/floorplan_res.json) into a tidier list.

Steps:
  - drops empty / very low confidence reads
  - drops short junk (icon misreads like 'tJ', 'SAR', 'lt')
  - splits results into: floor headers, room-number labels, room/area names
  - groups room/area name lines that sit directly on top of each other
    (candidate multi-line labels)
  - for every candidate group, re-crops the small area just to the left of
    each line (where this floor plan prints a tiny numbered bullet next to
    the FIRST line of each legend entry, e.g. "4  FITZGERALD HALL") and runs
    PaddleOCR again on just that crop, zoomed in. If a bullet number is
    confidently read there, that line must be the start of a new entry, so
    the group is split at that point even if the lines looked "stacked".
    This fixes cases where two separate one-line entries happened to sit as
    close together as a real multi-line wrap (and vice versa).
  - fixes "squished" words: cases where the recognizer read two real words
    as one, with no space (e.g. 'RESOURCEOFFICE' -> 'RESOURCE OFFICE'),
    using a dictionary word-segmentation library (wordninja) to find the
    most likely place to re-insert the missing space
"""

import json
import os
import re
import sys

os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

INPUT_IMAGE = "floorplan.png"
INPUT_JSON = "output/floorplan_res.json"
CROP_DIR = "output/_bullet_crops"
CONFIDENCE_THRESHOLD = 0.6

FLOOR_RE = re.compile(r"\b(ground|\d+(st|nd|rd|th))\s*floor\b", re.IGNORECASE)
NUMBER_LABEL_RE = re.compile(r"^[A-Za-z]{0,2}\d+[.:]?$")  # '5', 'N5', '6.'...
RANGE_LABEL_RE = re.compile(r"^[A-Za-z]{0,3}\d+[\-–][A-Za-z]{0,3}\d+$")  # 'S1-8', 'M17-32'
SHORT_JUNK_WHITELIST = {"IT"}

# How close two lines of text have to be to count as "candidates for being
# the same label wrapped onto a new line" (kept generous -- the bullet
# check below is what actually decides, this just proposes candidates):
WRAP_MAX_GAP = 1
WRAP_MAX_X_SHIFT = 15

# How far to the left of a line to look for a bullet number, and how
# confident a reading of it has to be to trust it:
BULLET_LEFT_MARGIN = 45
BULLET_PADDING = 3
BULLET_UPSCALE = 8
BULLET_CONFIDENCE = 0.6
BULLET_RE = re.compile(r"^\d{1,3}[.:]?$")


def load_entries():
    with open(INPUT_JSON, encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for text, score, box in zip(data["rec_texts"], data["rec_scores"], data["rec_boxes"]):
        text = text.strip()
        if not text or score < CONFIDENCE_THRESHOLD:
            continue
        x0, y0, x1, y1 = box
        entries.append({"text": text, "score": score, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    return entries


def is_short_junk(text):
    letters_only = re.sub(r"[^A-Za-z]", "", text)
    return (
        len(text) <= 3
        and letters_only == text
        and text.upper() not in SHORT_JUNK_WHITELIST
    )


def classify(text):
    if FLOOR_RE.search(text):
        return "floor_header"
    if NUMBER_LABEL_RE.match(text) or RANGE_LABEL_RE.match(text):
        return "number_label"
    if is_short_junk(text):
        return "junk"
    return "room_name"


def _directly_stacked(a, b):
    if a["y0"] <= b["y0"]:
        upper, lower = a, b
    else:
        upper, lower = b, a
    gap = lower["y0"] - upper["y1"]
    x_shift = abs(lower["x0"] - upper["x0"])
    return gap <= WRAP_MAX_GAP and x_shift <= WRAP_MAX_X_SHIFT


def group_wrapped_lines(entries):
    """Union-find over every pair of lines (not just neighbours in reading
    order), since this floor plan has several side-by-side legend panels at
    overlapping heights. Returns a list of groups, each sorted top-to-bottom."""
    n = len(entries)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    for i in range(n):
        for j in range(i + 1, n):
            if _directly_stacked(entries[i], entries[j]):
                union(i, j)

    groups = {}
    for i, e in enumerate(entries):
        groups.setdefault(find(i), []).append(e)

    result = [sorted(g, key=lambda e: (e["y0"], e["x0"])) for g in groups.values()]
    result.sort(key=lambda g: (g[0]["y0"], g[0]["x0"]))
    return result


def read_bullet_numbers(entries_needing_check, image_path=INPUT_IMAGE, ocr=None):
    """For each entry, crop the small area just to its left, zoom in, and
    run PaddleOCR on just that patch to look for a bullet number. Returns
    {id(entry): (text, score)} for patches where something was read.

    Pass an already-created `ocr` (PaddleOCR instance) to reuse it instead of
    constructing a second one -- creating two PaddleOCR instances in the
    same process turned out to sometimes stall for several minutes on this
    machine (likely some internal resource/lock contention), so the caller
    should always pass its existing instance when it has one."""
    if not entries_needing_check:
        return {}

    from PIL import Image, ImageOps

    os.makedirs(CROP_DIR, exist_ok=True)
    img = Image.open(image_path).convert("RGB")

    crop_paths = []
    for i, e in enumerate(entries_needing_check):
        x0 = max(0, int(e["x0"]) - BULLET_LEFT_MARGIN)
        x1 = int(e["x0"]) + 2  # a little past the text start, in case the bullet sits close to it
        y0 = max(0, int(e["y0"]) - BULLET_PADDING)
        y1 = int(e["y1"]) + BULLET_PADDING
        crop = img.crop((x0, y0, x1, y1))
        crop = crop.resize((crop.width * BULLET_UPSCALE, crop.height * BULLET_UPSCALE), Image.LANCZOS)
        # Some panels print the bullet in a low-contrast colour close to the
        # panel's own background tint; boosting contrast makes it readable.
        crop = ImageOps.autocontrast(crop, cutoff=1)
        path = os.path.join(CROP_DIR, f"crop_{i}.png")
        crop.save(path)
        crop_paths.append(path)

    if ocr is None:
        print(f"Loading PaddleOCR again to read {len(crop_paths)} cropped bullet-number patches...")
        from paddleocr import PaddleOCR

        ocr = PaddleOCR(
            lang="en",
            device="cpu",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )
    else:
        print(f"Reusing the loaded PaddleOCR model to read {len(crop_paths)} cropped bullet-number patches...")

    readings = {}
    for e, path in zip(entries_needing_check, crop_paths):
        for res in ocr.predict(path):
            texts, scores = res["rec_texts"], res["rec_scores"]
            if texts:
                # longest reading on the patch (bullets are short, ignore stray noise)
                best = max(zip(texts, scores), key=lambda t: t[1])
                readings[id(e)] = best
    return readings


def apply_bullet_splits(groups, readings):
    final_groups = []
    split_log = []
    for group in groups:
        if len(group) == 1:
            final_groups.append(group)
            continue
        current = [group[0]]
        for e in group[1:]:
            reading = readings.get(id(e))
            if reading and BULLET_RE.match(reading[0]) and reading[1] >= BULLET_CONFIDENCE:
                split_log.append((e["text"], reading[0], reading[1]))
                final_groups.append(current)
                current = [e]
            else:
                current.append(e)
        final_groups.append(current)
    return final_groups, split_log


OFFICES_CODE_RE = re.compile(r"\bOFFICES([A-Z]\d[\dA-Z\-]*)\b")

# Only try to split a word if it's long enough that it's plausibly two real
# words glued together (a genuine single English word this long is rare),
# and only accept the split if every resulting piece is a real-looking
# word (>=3 letters) and there aren't too many pieces -- this is what stops
# the splitter from mangling short, already-correct (if oddly spelled)
# words like 'GALLIRY' or 'CARLOVIAN'.
SQUISH_MIN_LENGTH = 10
SQUISH_MIN_PART_LENGTH = 3
SQUISH_MAX_PARTS = 4


def fix_squished_word(token):
    """Re-insert a missing space inside a single word, if it looks like two
    (or a few) real words were run together. Keeps apostrophes in place
    (e.g. "STUDENTS'UNION" -> "STUDENTS' UNION")."""
    if not all(ch.isalpha() or ch == "'" for ch in token):
        return token  # leave numbers/ranges/punctuation-heavy tokens alone

    core_chars, core_to_orig = [], []
    for i, ch in enumerate(token):
        if ch.isalpha():
            core_chars.append(ch)
            core_to_orig.append(i)
    core = "".join(core_chars)
    if len(core) < SQUISH_MIN_LENGTH:
        return token

    import wordninja

    parts = wordninja.split(core)
    if len(parts) < 2 or len(parts) > SQUISH_MAX_PARTS:
        return token
    if any(len(p) < SQUISH_MIN_PART_LENGTH for p in parts):
        return token

    boundary_core_idx = []
    pos = 0
    for p in parts[:-1]:
        pos += len(p)
        boundary_core_idx.append(pos)
    boundary_orig_idx = {core_to_orig[b] for b in boundary_core_idx}

    out = []
    for i, ch in enumerate(token):
        if i in boundary_orig_idx:
            out.append(" ")
        out.append(ch)
    return "".join(out)


def fix_squished_words(text):
    text = OFFICES_CODE_RE.sub(r"OFFICES \1", text)
    return " ".join(fix_squished_word(tok) for tok in text.split(" "))


def dedup_keep_order(items):
    seen = set()
    out = []
    for item in items:
        key = item.upper()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def main():
    entries = load_entries()

    floor_headers, number_labels, room_name_entries, junk = [], [], [], []
    for e in entries:
        kind = classify(e["text"])
        if kind == "floor_header":
            floor_headers.append(e["text"])
        elif kind == "number_label":
            number_labels.append(e["text"])
        elif kind == "junk":
            junk.append(e["text"])
        else:
            room_name_entries.append(e)

    groups = group_wrapped_lines(room_name_entries)

    # Only the 2nd+ lines of a multi-line candidate group need checking --
    # a group of 1 is already unambiguous.
    needs_check = [e for g in groups if len(g) > 1 for e in g[1:]]
    readings = read_bullet_numbers(needs_check)
    groups, split_log = apply_bullet_splits(groups, readings)

    raw_room_names = [" ".join(e["text"] for e in g) for g in groups]
    fixed_room_names = [fix_squished_words(t) for t in raw_room_names]
    squish_log = [(r, f) for r, f in zip(raw_room_names, fixed_room_names) if r != f]

    room_names = dedup_keep_order(fixed_room_names)
    floor_headers = dedup_keep_order(floor_headers)

    print(f"\nLoaded {len(entries)} labels with confidence >= {CONFIDENCE_THRESHOLD}\n")

    if split_log:
        print(f"=== Candidate merges split apart after reading a bullet number ({len(split_log)}) ===")
        for text, digit, score in split_log:
            print(f"  '{digit}' (confidence {score:.3f}) found left of '{text}' -> starts a new entry")

    if squish_log:
        print(f"=== Squished words fixed ({len(squish_log)}) ===")
        for before, after in squish_log:
            print(f"  '{before}' -> '{after}'")

    print(f"\n=== Floor headers found ({len(floor_headers)}) ===")
    for t in floor_headers:
        print(f"  {t}")

    print(f"\n=== Room / area names, merged + deduplicated ({len(room_names)}) ===")
    for t in room_names:
        print(f"  {t}")

    print(f"\n=== Room-number labels, kept for reference ({len(number_labels)}) ===")
    print("  " + ", ".join(number_labels))

    if junk:
        print(f"\n=== Dropped as likely junk/icon misreads ({len(junk)}) ===")
        print("  " + ", ".join(junk))

    with open("output/rooms_cleaned.txt", "w", encoding="utf-8") as f:
        f.write("Floor headers:\n")
        for t in floor_headers:
            f.write(f"  {t}\n")
        f.write("\nRoom / area names:\n")
        for t in room_names:
            f.write(f"  {t}\n")

    print("\nSaved cleaned list to output/rooms_cleaned.txt")


if __name__ == "__main__":
    main()
