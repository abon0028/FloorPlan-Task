"""
stress_test.py

Runs the same PaddleOCR setup from test_ocr.py against the original
floorplan.png plus three degraded copies (rotated, blurred, downscaled +
recompressed), to see how much detection quality drops as the input image
gets worse. Loads the model once and reuses it for all four images.
"""

import os
import sys

os.environ["PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"] = "False"
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from paddleocr import PaddleOCR

VARIANTS = {
    "original": "floorplan.png",
    "rotated (8 deg)": "output/stress/variant_rotated.png",
    "blurred": "output/stress/variant_blurred.png",
    "downscaled (40%, JPEG q35)": "output/stress/variant_downscaled.png",
}

OUTPUT_DIR = "output/stress"


def main():
    print("Loading PaddleOCR (English, CPU)...")
    ocr = PaddleOCR(
        lang="en",
        device="cpu",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )

    summary = []
    for label, path in VARIANTS.items():
        print(f"\nRunning OCR on [{label}] ({path}) ...")
        for res in ocr.predict(path):
            texts = res["rec_texts"]
            scores = res["rec_scores"]
            n = len(texts)
            avg_conf = sum(scores) / n if n else 0.0
            high_conf = sum(1 for s in scores if s >= 0.9)
            summary.append((label, n, avg_conf, high_conf))
            print(f"  {n} labels found, average confidence {avg_conf:.3f}, {high_conf} at >=0.90 confidence")
            res.save_to_img(OUTPUT_DIR)

    print("\n" + "=" * 70)
    print(f"{'Variant':30s} {'# labels':>10s} {'avg conf':>10s} {'# high-conf':>12s}")
    print("-" * 70)
    for label, n, avg_conf, high_conf in summary:
        print(f"{label:30s} {n:10d} {avg_conf:10.3f} {high_conf:12d}")

    print(f"\nAnnotated images for each variant saved in '{OUTPUT_DIR}/'")


if __name__ == "__main__":
    main()
