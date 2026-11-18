"""
End-to-end detection over a crawl (block diagram stages 3 → 4):

    crawl output ─► segments (preprocessing) ─► candidate pre-filter (rules + TF-IDF)
                 ─► LLM extract→infer→verify (or offline engine) ─► predictions.jsonl

The pre-filter keeps every segment that a rule matches, that the classifier
scores above `prefilter_threshold`, that is a PRE-TICKED form control, or that
is a choice pair in a popup.  Only those reach the LLM, which cuts cost; the
fraction filtered out is reported so the trade-off can be measured.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path

from .detection.detector import DarkPatternDetector
from .preprocessing.lexicon import rule_label
from .preprocessing.segments import load_crawl, page_segments
from .taxonomy import NOT_DARK


def prefilter(segs: list[dict], detector: DarkPatternDetector, threshold: float = 0.15) -> list[bool]:
    keep = []
    scores = detector.text_clf.predict([s["text"] for s in segs]) if detector.text_clf else None
    for i, s in enumerate(segs):
        k = (rule_label(s["text"]) != NOT_DARK
             or (scores is not None and scores[i]["p_dark"] >= threshold)
             or (s["kind"] in ("checkbox", "radio") and s.get("checked"))
             or s["kind"] in ("choice_pair", "select"))
        keep.append(bool(k))
    return keep


def run(crawl_dir: str | Path, out_path: str | Path, engine: str = "auto", mode: str = "multistage",
        use_prefilter: bool = True, prefilter_threshold: float = 0.15, max_states: int = 0) -> dict:
    det = DarkPatternDetector(engine=engine, mode=mode)
    records = load_crawl(crawl_dir)
    if max_states:
        records = records[:max_states]
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = defaultdict(int)
    t0 = time.time()
    with open(out_path, "w", encoding="utf-8") as fout:
        for rec in records:
            segs = page_segments(rec)
            if not segs:
                continue
            keep = prefilter(segs, det, prefilter_threshold) if use_prefilter else [True] * len(segs)
            sent = [dict(s, id=i + 1) for i, s in enumerate(segs) if keep[i]]
            stats["segments"] += len(segs)
            stats["sent_to_detector"] += len(sent)
            ctx = {"page type": rec.get("page_type"), "url": rec.get("url"), "language": rec.get("language"),
                   "state": rec.get("label")}
            preds = {p["id"]: p for p in det.classify_segments(sent, ctx)} if sent else {}
            for i, s in enumerate(segs):
                p = preds.get(i + 1)
                row = {k: s[k] for k in ("segment_id", "state_id", "site", "url", "page_type", "state_label",
                                         "language", "country", "sector", "kind", "ui", "text", "checked",
                                         "in_overlay", "bbox", "screenshot")}
                if p is None:
                    row.update(label=NOT_DARK, confidence=None, evidence="", explanation="filtered out by pre-filter",
                               engine="prefilter", sent=False)
                else:
                    row.update({k: p.get(k) for k in ("label", "confidence", "evidence", "explanation", "engine",
                                                      "stage1_label", "verify_reason")}, sent=True)
                stats["dark_segments"] += int(row["label"] != NOT_DARK)
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            stats["states"] += 1
    summary = {**stats, "elapsed_s": round(time.time() - t0, 1), "detector": det.info(),
               "prefilter": use_prefilter, "prefilter_threshold": prefilter_threshold,
               "llm_calls": det.llm.calls if det.llm else 0,
               "llm_usage": det.llm.usage if det.llm else None}
    summary["prefilter_reduction"] = round(1 - stats["sent_to_detector"] / max(1, stats["segments"]), 3)
    Path(str(out_path) + ".summary.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run DarkLens detection over a crawl directory.")
    ap.add_argument("--crawl", default="data/crawl")
    ap.add_argument("--out", default="data/predictions/segments.jsonl")
    ap.add_argument("--engine", default="auto", choices=["auto", "llm", "offline"])
    ap.add_argument("--mode", default="multistage", choices=["multistage", "single"])
    ap.add_argument("--no-prefilter", action="store_true")
    ap.add_argument("--max-states", type=int, default=0)
    a = ap.parse_args()
    s = run(a.crawl, a.out, a.engine, a.mode, not a.no_prefilter, max_states=a.max_states)
    print(json.dumps(s, indent=2))
