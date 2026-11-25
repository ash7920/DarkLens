"""
LLM vs. baselines on the held-out text test split (471 items, never used for
few-shot examples or training).

    python scripts/eval_llm_text.py --mode multistage
    python scripts/eval_llm_text.py --mode single          # ablation: no verification stage
    python scripts/eval_llm_text.py --limit 100            # quick/cheap trial

Writes results/llm_text_<provider>_<model>_<mode>.json with binary and
multi-class metrics, comparable to results/baselines.json["held_out_test"].
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.detection.detector import DarkPatternDetector  # noqa: E402
from darklens.evaluation.metrics import binary_metrics, multiclass_metrics  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="multistage", choices=["multistage", "single"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=40)
    a = ap.parse_args()

    df = pd.read_csv(ROOT / "data/splits/text_test.csv")
    if a.limit:
        df = df.sample(n=min(a.limit, len(df)), random_state=0)
    df = df.sample(frac=1.0, random_state=1).reset_index(drop=True)  # mix pages within batches
    det = DarkPatternDetector(engine="llm", mode=a.mode, batch_size=a.batch)
    items = [{"id": i + 1, "text": t, "ui": ""} for i, t in enumerate(df["text"])]
    ctx = {"input": "isolated text snippets scraped from e-commerce pages (no visual context)"}
    t0 = time.time()
    preds = det.classify_segments(items, ctx)
    secs = time.time() - t0
    y_pred = [p["label"] for p in preds]
    res = {
        "n": len(df), "mode": a.mode, "engine": det.info(), "seconds": round(secs, 1),
        "llm_calls": det.llm.calls, "llm_usage": det.llm.usage,
        "binary": binary_metrics(df["label_binary"].to_numpy(), [int(l != "not_dark") for l in y_pred]),
        "multiclass": multiclass_metrics(list(df["category"]), y_pred),
    }
    if a.mode == "multistage":
        stage1 = [p.get("stage1_label", p["label"]) for p in preds]
        res["stage1_only"] = {
            "binary": binary_metrics(df["label_binary"].to_numpy(), [int(l != "not_dark") for l in stage1]),
            "multiclass": multiclass_metrics(list(df["category"]), stage1),
        }
    tag = re.sub(r"[^a-zA-Z0-9.-]+", "-", f"{det.llm.provider}_{det.llm.model}_{a.mode}")
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / f"results/llm_text_{tag}.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    out = df.assign(pred=y_pred, confidence=[p["confidence"] for p in preds],
                    explanation=[p["explanation"] for p in preds])
    out.to_csv(ROOT / f"results/llm_text_{tag}_predictions.csv", index=False)
    b, m = res["binary"], res["multiclass"]
    print(f"{tag}: binary P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f} | "
          f"multiclass macro-F1={m['macro_f1']:.3f} acc={m['accuracy']:.3f} | {det.llm.calls} calls, {secs:.0f}s")


if __name__ == "__main__":
    main()
