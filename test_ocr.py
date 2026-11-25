"""
test_ocr.py

Reads floorplan.png with PaddleOCR (English, CPU only) and:
  1. Prints every text label it detects, with its confidence score.
  2. Saves a copy of the image, with boxes drawn around each detected
     label, into the output/ folder.
"""

import os
import sys

# PaddlePaddle on Windows CPU defaults to using "oneDNN" (an Intel CPU speed-up
# library). On this machine/version it hits a known bug, so we turn it off
# before importing paddleocr. This must happen before the import.
os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"

# Windows terminals sometimes can't print unusual characters that OCR
# misreads (e.g. stray Chinese characters from noisy image regions).
# Reconfigure stdout to UTF-8 so printing never crashes the script.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from paddleocr import PaddleOCR

INPUT_IMAGE = "floorplan.png"
OUTPUT_DIR = "output"


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Loading PaddleOCR (English, CPU)... the first run downloads models, so it may take a few minutes.")
    ocr = PaddleOCR(
        lang="en",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    print(f"Running OCR on {INPUT_IMAGE} ...")
    results = ocr.predict(INPUT_IMAGE)

    for res in results:
        texts = res["rec_texts"]
        scores = res["rec_scores"]

        print(f"\nFound {len(texts)} text labels:\n")
        for text, score in zip(texts, scores):
            print(f"  '{text}'  (confidence: {score:.3f})")

        # Saves an annotated image (boxes + recognized text) and a JSON
        # file with all the raw results, both into OUTPUT_DIR.
        res.save_to_img(OUTPUT_DIR)
        res.save_to_json(OUTPUT_DIR)

    print(f"\nDone. Annotated image(s) and JSON saved in '{OUTPUT_DIR}/'")


if __name__ == "__main__":
    main()
