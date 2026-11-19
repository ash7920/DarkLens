"""
Screenshot benchmark on AidUI / ContextDP (Mansur et al. 2023) — the same
analysis path the web interface uses.

    python scripts/eval_screenshots.py --split web --engine offline
    python scripts/eval_screenshots.py --split web --engine llm --mode multistage
    python scripts/eval_screenshots.py --split web --engine llm --mode single     # ablation

Image-level, multi-label scoring: an image is "dark" if it has >=1 dark
annotation; per-category P/R/F1 compare the set of categories predicted for
the image with the annotated set.  Only categories AidUI annotates are scored
per-category (urgency, scarcity, social_proof, preselection, interface_interference).

Tune thresholds on --split mobile, report on --split web (no tuning on the test set).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.detection.detector import DarkPatternDetector  # noqa: E402
from darklens.detection.llm_client import LLMError  # noqa: E402
from darklens.evaluation.metrics import multilabel_image_metrics  # noqa: E402
from darklens.preprocessing.datasets import load_aidui  # noqa: E402

AIDUI_CATS = ["urgency", "scarcity", "social_proof", "preselection", "interface_interference"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="web", choices=["web", "mobile"])
    ap.add_argument("--engine", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--mode", default="multistage", choices=["multistage", "single"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ocr-threshold", type=float, default=0.5)
    ap.add_argument("--sweep", default="", help="offline only: comma-separated thresholds to compare in one OCR pass")
    a = ap.parse_args()

    df = load_aidui(split=a.split)
    if a.limit:
        df = df.sample(n=min(a.limit, len(df)), random_state=0)
    sweep = [float(x) for x in a.sweep.split(",") if x]
    det = DarkPatternDetector(engine=a.engine, mode=a.mode, ocr_threshold=min(sweep) if sweep else a.ocr_threshold)
    raw = []
    preds, gold, rows, failed = [], [], [], []
    t0 = time.time()
    for i, r in enumerate(df.itertuples(), 1):
        try:
            res = det.analyze_screenshot(Path(r.image_path).read_bytes())
        except LLMError as exc:
            # one unusable answer must not stop the benchmark; the image is reported, not scored
            failed.append({"item_id": r.item_id, "error": str(exc)[:200]})
            print(f"  ! {r.item_id}: skipped ({exc})", flush=True)
            if "DAILY" in str(exc):
                print("Daily quota used up: re-run the same command after the reset.", flush=True)
                return
            continue
        raw.append(res["detections"])
        p = {d["label"] for d in res["detections"]}
        preds.append(p)
        gold.append(set(r.categories))
        rows.append({"item_id": r.item_id, "image": r.image_path, "gold": sorted(r.categories), "pred": sorted(p),
                     "detections": [{k: d.get(k) for k in ("label", "confidence", "evidence", "box")}
                                    for d in res["detections"]]})
        if i % 20 == 0:
            print(f"  {i}/{len(df)}  {time.time() - t0:.0f}s")
    if sweep:
        for t in sweep:
            pt = [{d["label"] for d in ds if d.get("basis") != "classifier" or d["confidence"] >= t} for ds in raw]
            mt = multilabel_image_metrics(gold, pt, AIDUI_CATS)
            print(f"threshold {t}: binary F1={mt['binary']['f1']:.3f} P={mt['binary']['precision']:.3f} "
                  f"R={mt['binary']['recall']:.3f} category macro-F1={mt['macro_f1']:.3f}")
        return
    m = multilabel_image_metrics(gold, preds, AIDUI_CATS)
    # categories outside AidUI's label set cannot be scored per category; they still count for binary
    m.update({"split": a.split, "n_images": len(gold), "n_failed": len(failed), "failed": failed,
              "engine": det.info(), "mode": a.mode,
              "seconds_per_image": round((time.time() - t0) / max(1, len(df)), 2),
              "llm_calls": det.llm.calls if det.llm else 0,
              "llm_usage": det.llm.usage if det.llm else None})
    tag = f"{a.split}_{det.engine}_{a.mode if det.llm else 'rules+tfidf'}"
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / f"results/screenshots_{tag}.json").write_text(json.dumps(m, indent=2, default=float))
    with open(ROOT / f"results/screenshots_{tag}_predictions.jsonl", "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    b = m["binary"]
    print(f"{tag}: binary P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f} | "
          f"category micro-F1={m['micro']['f1']:.3f} macro-F1={m['macro_f1']:.3f}")


if __name__ == "__main__":
    main()
