"""Cut the annotation sample down to a size people will actually finish.

    python scripts/shrink_annotation_sample.py              # just show how far everyone has got
    python scripts/shrink_annotation_sample.py --keep 400   # keep 400 items (plus anything already labelled)

The sample file is already in random order with the three strata mixed, and the app hands items
out in file order, so the first N items are themselves a random sample of each stratum. We keep
those, add any item someone has already labelled further down (after skips), and recompute each
stratum's weight so the evaluation still estimates precision and recall for the whole crawl.

The full sample is copied to data/annotation/sample_full.jsonl the first time, so nothing is lost.
Labels are not touched. The app picks the new sample up straight away; no restart needed.
"""
import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from darklens.evaluation import annotation  # noqa: E402

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--keep", type=int, default=0, help="items to keep (0 = only report progress)")
args = ap.parse_args()

sample_path = annotation.ANN_DIR / "sample.jsonl"
full_path = annotation.ANN_DIR / "sample_full.jsonl"
items = annotation.load_sample()
labels = annotation.load_labels()
labelled_any = set().union(*labels.values()) if labels else set()

print(f"Sample now: {len(items)} items")
for name, got in sorted(labels.items()):
    print(f"  {name}: {sum(1 for it in items if it['segment_id'] in got)} labelled")

if not args.keep:
    sys.exit(0)
if args.keep >= len(items):
    sys.exit(f"--keep {args.keep} is not smaller than the current {len(items)} items; nothing to do.")

# stratum sizes in the crawl: weight x items sampled from it (weight = units / sampled)
count = Counter(it["stratum"] for it in items)
units = {s: round(next(it["weight"] for it in items if it["stratum"] == s) * n) for s, n in count.items()}

kept = [it for i, it in enumerate(items) if i < args.keep or it["segment_id"] in labelled_any]
new_count = Counter(it["stratum"] for it in kept)
for it in kept:
    it["weight"] = units[it["stratum"]] / new_count[it["stratum"]]

if not full_path.exists():
    shutil.copyfile(sample_path, full_path)
with open(sample_path, "w", encoding="utf-8") as f:
    for it in kept:
        f.write(json.dumps(it, ensure_ascii=False) + "\n")

print(f"\nKept {len(kept)} of {len(items)} items (full sample saved as {full_path.as_posix()})")
for s in sorted(units):
    print(f"  {s:9s} {new_count.get(s, 0):4d} items standing for {units[s]} in the crawl")
for name, got in sorted(labels.items()):
    done = sum(1 for it in kept if it["segment_id"] in got)
    print(f"  {name}: {done} done, {len(kept) - done} left")
