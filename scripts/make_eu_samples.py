"""
Add real EU shop pages from our crawl to the sample buttons on the Inspect tab.

    python scripts/make_eu_samples.py

Each sample is a dark pattern that DarkLens flagged AND our annotator confirmed (from the labelled
crawl sample). The script cuts a screen-sized window around it from the page screenshot, skips
blank or missing screenshots, and writes app/static/samples/eu-*.png plus samples.json, which the
app reads to show extra sample buttons. The original three test-shop samples stay as they are.
Needs the crawl screenshots in data/crawl (they are only on the machine that ran the crawl).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/static/samples"
W, H = 1366, 900

# (button label, file name, candidate texts in order of preference); the first candidate whose
# screenshot exists and is not blank around the element is used
SLOTS = [
    ("Real shop: cookie banner", "eu-cookie-banner",
     ["'Cookie Settings' (large", "'+ Essential cookies' (large", "'ALLOW ALL COOKIES' (large", "'I agree' (large"]),
    ("Real shop: low stock", "eu-low-stock",
     ["Only 1 in stock!", "ONLY 1 IN STOCK!", "10 products remaining"]),
    ("Real shop: activity badge", "eu-activity-badge",
     ["10 customers just added this", "Be quick! 12 people viewed", "Bought 359x on the previous day", "16 SOLD TODAY"]),
    ("Real shop: today only", "eu-today-only",
     ["FLASH deals Today only!", "ONLY TODAY 30%", "TODAY ONLY", "On sale today only"]),
]


def _load(path):
    return [json.loads(l) for l in open(path, encoding="utf-8")]


def main():
    sample = {s["segment_id"]: s for s in _load(ROOT / "data/annotation/sample.jsonl")}
    gold = {g["segment_id"]: g["label"] for g in _load(ROOT / "data/annotation/gold.jsonl")}
    confirmed = [sample[i] for i, lab in gold.items()
                 if lab != "not_dark" and sample.get(i, {}).get("stratum") == "flagged"]
    OUT.mkdir(parents=True, exist_ok=True)
    made = []
    for label, name, wanted in SLOTS:
        done = False
        for text in wanted:
            for it in confirmed:
                if text.lower() not in ((it.get("text") or "") + " " + (it.get("text_en") or "")).lower():
                    continue
                shot = ROOT / (it.get("screenshot") or "").replace("\\", "/")
                x, y, w, h = it.get("bbox") or [0, 0, 0, 0]
                if not shot.is_file() or w < 2 or h < 2:
                    continue
                img = Image.open(shot).convert("RGB")
                if y + h > img.height or x + w > img.width:
                    continue
                y0 = max(0, min(img.height - H, y + h // 2 - H // 2))
                crop = img.crop((0, y0, min(img.width, W), min(img.height, y0 + H)))
                if ImageStat.Stat(crop.crop((max(0, x - 40), y - y0, min(crop.width, x + w + 40),
                                             min(crop.height, y - y0 + h))).convert("L")).stddev[0] < 4:
                    continue  # blank where the element should be
                crop.save(OUT / f"{name}.png", optimize=True)
                made.append({"label": label, "url": f"samples/{name}.png", "site": it["site"]})
                print(f"  {label:28s} <- {it['site']}: {(it.get('text_en') or it['text'])[:60]}")
                done = True
                break
            if done:
                break
        if not done:
            print(f"  {label:28s}    no usable screenshot found; skipped")
    (OUT / "samples.json").write_text(json.dumps(made, indent=2), encoding="utf-8")
    print(f"{len(made)} sample(s) -> {OUT.as_posix()}/samples.json. Restart the app and look at each one before a demo.")
    return 0 if made else 1


if __name__ == "__main__":
    sys.exit(main())
