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


ROW_KEYS = ("segment_id", "state_id", "site", "url", "page_type", "state_label", "language", "country", "sector",
            "kind", "ui", "text", "checked", "in_overlay", "bbox", "screenshot")


def _seg_key(s: dict) -> tuple:
    return (s["kind"], s["ui"], s["text"].strip().lower(), s.get("checked"))


def run(crawl_dir: str | Path, out_path: str | Path, engine: str = "auto", mode: str = "multistage",
        use_prefilter: bool = True, prefilter_threshold: float = 0.15, max_states: int = 0,
        batch_size: int = 80, dry_run: bool = False) -> dict:
    """Detection over a crawl, one site at a time.

    Text that repeats across a site's pages (cookie banner, menu, footer, newsletter pop-up) is
    classified ONCE per site and the answer is applied to every occurrence, so the LLM sees each
    distinct element of a shop exactly once.  Each element carries the type of the page it first
    appeared on.  `dry_run` counts the LLM calls a run needs without making any."""
    det = DarkPatternDetector(engine="offline" if dry_run else engine, mode=mode, batch_size=batch_size)
    from .crawler.coverage import crawlable_sites
    ok_sites = crawlable_sites(crawl_dir)
    all_records = load_crawl(crawl_dir)
    # blocked / unavailable sites are reported as coverage, never as "no dark patterns"
    records = [r for r in all_records if r.get("site") in ok_sites]
    if max_states:
        records = records[:max_states]
    by_site: dict[str, list] = defaultdict(list)
    for r in records:
        by_site[r.get("site")].append(r)

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    stats = defaultdict(int)
    t0 = time.time()
    fout = None if dry_run else open(out_path, "w", encoding="utf-8")
    try:
        for n_site, (site, recs) in enumerate(by_site.items(), 1):
            per_state, unique = [], {}
            for rec in recs:
                segs = page_segments(rec)
                if not segs:
                    continue
                keep = prefilter(segs, det, prefilter_threshold) if use_prefilter else [True] * len(segs)
                per_state.append((rec, segs, keep))
                stats["states"] += 1
                stats["segments"] += len(segs)
                for s, k in zip(segs, keep):
                    if not k:
                        continue
                    stats["sent_to_detector"] += 1
                    key = _seg_key(s)
                    if key not in unique:
                        unique[key] = {"id": len(unique) + 1, "text": s["text"], "kind": s["kind"],
                                       "checked": s.get("checked"),
                                       "ui": f"[{rec.get('page_type') or 'other'} page] {s['ui']}"}
            items = list(unique.values())
            stats["unique_sent"] += len(items)
            stats["infer_calls"] += -(-len(items) // batch_size)
            if dry_run:
                continue
            first = recs[0]
            ctx = {"site": site, "country": first.get("country"), "language": first.get("language"),
                   "input": "distinct elements from all crawled pages of this shop, in order of first appearance"}
            preds = {p["id"]: p for p in det.classify_segments(items, ctx)} if items else {}
            n_dark = sum(1 for p in preds.values() if p["label"] != NOT_DARK)
            print(f"[{n_site}/{len(by_site)}] {site}: {len(items)} distinct elements, {n_dark} flagged", flush=True)
            for rec, segs, keep in per_state:
                for s, k in zip(segs, keep):
                    row = {kk: s[kk] for kk in ROW_KEYS}
                    p = preds.get(unique[_seg_key(s)]["id"]) if k else None
                    if p is None:
                        row.update(label=NOT_DARK, confidence=None, evidence="",
                                   explanation="filtered out by pre-filter", engine="prefilter", sent=False)
                    else:
                        row.update({kk: p.get(kk) for kk in ("label", "confidence", "evidence", "explanation",
                                                              "engine", "stage1_label", "verify_reason")}, sent=True)
                    stats["dark_segments"] += int(row["label"] != NOT_DARK)
                    fout.write(json.dumps(row, ensure_ascii=False) + "\n")
    finally:
        if fout:
            fout.close()

    summary = {**stats, "sites": len(by_site), "sites_crawlable": len(ok_sites),
               "states_skipped_not_crawlable": len(all_records) - len(records),
               "elapsed_s": round(time.time() - t0, 1), "detector": det.info(), "batch_size": batch_size,
               "prefilter": use_prefilter, "prefilter_threshold": prefilter_threshold,
               "llm_calls": det.llm.calls if det.llm else 0,
               "llm_usage": det.llm.usage if det.llm else None, "dry_run": dry_run}
    summary["prefilter_reduction"] = round(1 - stats["sent_to_detector"] / max(1, stats["segments"]), 3)
    summary["dedup_reduction"] = round(1 - stats["unique_sent"] / max(1, stats["sent_to_detector"]), 3)
    if dry_run:
        summary["note"] = (f"needs about {stats['infer_calls']} detection calls plus verification calls for "
                           f"flagged elements (typically a further 30-60%); already-answered calls are free")
    else:
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
    ap.add_argument("--batch", type=int, default=80, help="elements per LLM call")
    ap.add_argument("--dry-run", action="store_true", help="count the LLM calls needed; uses no API quota")
    a = ap.parse_args()
    s = run(a.crawl, a.out, a.engine, a.mode, not a.no_prefilter, max_states=a.max_states,
            batch_size=a.batch, dry_run=a.dry_run)
    print(json.dumps(s, indent=2))
