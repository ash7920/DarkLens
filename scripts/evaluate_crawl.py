"""
Evaluation + final analysis for the live EU crawl (block diagram stages 5–6).

    python scripts/evaluate_crawl.py --pred data/predictions/segments.jsonl

1. Evaluation module: LLM predictions vs. human gold (data/annotation/gold.jsonl)
   -> precision, recall, F1 (binary + per category), Cohen's kappa (LLM vs gold),
      human-human agreement, error analysis table (FP/FN with the LLM's explanation).
2. Final findings: prevalence of each pattern by site, page type, country, sector
   and language; detected examples.  Prevalence is reported as a LOWER BOUND
   (LLMs under-recall relative to humans — Nwokeji et al. 2026).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.evaluation.annotation import agreement, load_sample  # noqa: E402
from darklens.evaluation.metrics import binary_metrics, multiclass_metrics  # noqa: E402
from darklens.taxonomy import CATEGORY_KEYS, NOT_DARK  # noqa: E402


def prevalence(preds: list[dict]) -> dict:
    sites = defaultdict(set)
    meta = {}
    for p in preds:
        meta.setdefault(p["site"], {"country": p.get("country") or "unknown", "sector": p.get("sector") or "unknown",
                                    "language": p.get("language") or "unknown"})
        if p["label"] != NOT_DARK:
            sites[p["site"]].add(p["label"])
    all_sites = sorted(meta)
    n = len(all_sites)
    out = {"n_sites": n, "n_states": len({p["state_id"] for p in preds}),
           "sites_with_any_pattern": sum(1 for s in all_sites if sites[s]),
           "share_sites_with_any_pattern": sum(1 for s in all_sites if sites[s]) / max(1, n),
           "by_category": {c: sum(1 for s in all_sites if c in sites[s]) / max(1, n) for c in CATEGORY_KEYS},
           "instances_by_category": Counter(p["label"] for p in preds if p["label"] != NOT_DARK),
           "mean_categories_per_site": sum(len(sites[s]) for s in all_sites) / max(1, n)}
    # page-type level: share of page states of each type that contain each pattern
    states = defaultdict(lambda: {"type": None, "labels": set()})
    for p in preds:
        st = states[p["state_id"]]
        st["type"] = p.get("page_type") or "other"
        if p["label"] != NOT_DARK:
            st["labels"].add(p["label"])
    by_pt = defaultdict(lambda: Counter())
    pt_n = Counter()
    for st in states.values():
        pt_n[st["type"]] += 1
        by_pt[st["type"]]["any"] += int(bool(st["labels"]))
        for l in st["labels"]:
            by_pt[st["type"]][l] += 1
    out["by_page_type"] = {pt: {k: v / pt_n[pt] for k, v in c.items()} | {"n": pt_n[pt]} for pt, c in by_pt.items()}
    for dim in ("country", "sector", "language"):
        groups = defaultdict(list)
        for s in all_sites:
            groups[meta[s][dim]].append(s)
        out[f"by_{dim}"] = {g: {"n_sites": len(ss), "any": sum(1 for s in ss if sites[s]) / len(ss),
                                **{c: sum(1 for s in ss if c in sites[s]) / len(ss) for c in CATEGORY_KEYS}}
                            for g, ss in groups.items()}
    examples = defaultdict(list)
    for p in sorted(preds, key=lambda p: -(p.get("confidence") or 0)):
        if p["label"] != NOT_DARK and len(examples[p["label"]]) < 8 and p["text"] not in [e["text"] for e in examples[p["label"]]]:
            examples[p["label"]].append({"site": p["site"], "page_type": p.get("page_type"), "text": p["text"][:200],
                                         "confidence": p.get("confidence"), "explanation": p.get("explanation")})
    out["examples"] = examples
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", default="data/predictions/segments.jsonl")
    ap.add_argument("--gold", default="data/annotation/gold.jsonl")
    ap.add_argument("--adjudicator", default=None)
    a = ap.parse_args()
    preds = [json.loads(l) for l in open(ROOT / a.pred, encoding="utf-8")]
    from darklens.crawler.coverage import coverage
    cov = coverage(ROOT / "data/crawl")
    res = {"coverage": {k: v for k, v in cov.items() if k != "sites"}, "prevalence": prevalence(preds)}

    gold_path = ROOT / a.gold
    res["human_agreement"] = agreement(adjudicator=a.adjudicator)
    if gold_path.exists():
        gold = {json.loads(l)["segment_id"]: json.loads(l)["label"] for l in open(gold_path, encoding="utf-8")}
        pairs = [(gold[p["segment_id"]], p) for p in preds if p["segment_id"] in gold]
        if pairs:
            yt = [g for g, _ in pairs]
            yp = [p["label"] for _, p in pairs]
            sample = {it["segment_id"]: it for it in load_sample()}
            w = [sample.get(p["segment_id"], {}).get("weight", 1.0) for _, p in pairs]
            ytb, ypb = [int(x != NOT_DARK) for x in yt], [int(x != NOT_DARK) for x in yp]
            res["evaluation"] = {
                # population estimates: each labelled unit stands for `weight` units of its stratum
                "binary": binary_metrics(ytb, ypb, sample_weight=w),
                "multiclass": multiclass_metrics(yt, yp, sample_weight=w),
                # plain agreement on the labelled sample itself (used for kappa reporting)
                "binary_sample": binary_metrics(ytb, ypb),
                "multiclass_sample": multiclass_metrics(yt, yp),
                "by_stratum": {st: {"n": sum(1 for _, p in pairs if sample.get(p["segment_id"], {}).get("stratum") == st),
                                    "gold_dark": sum(1 for g, p in pairs if sample.get(p["segment_id"], {}).get("stratum") == st
                                                     and g != NOT_DARK)}
                               for st in ("flagged", "cleared", "filtered")},
                "prefilter_misses": sum(1 for g, p in pairs if not p.get("sent") and g != NOT_DARK),
            }
            errors = []
            for g, p in pairs:
                if g != p["label"]:
                    errors.append({"type": "FN" if p["label"] == NOT_DARK else ("FP" if g == NOT_DARK else "wrong category"),
                                   "gold": g, "pred": p["label"], "text": p["text"][:200], "site": p["site"],
                                   "page_type": p.get("page_type"), "explanation": p.get("explanation")})
            res["errors"] = errors
            res["error_counts"] = Counter(e["type"] for e in errors)
            by_lang = defaultdict(lambda: ([], []))
            for g, p in pairs:
                by_lang[p.get("language") or "unknown"][0].append(int(g != NOT_DARK))
                by_lang[p.get("language") or "unknown"][1].append(int(p["label"] != NOT_DARK))
            res["by_language"] = {l: binary_metrics(t, q, n_boot=0) for l, (t, q) in by_lang.items() if len(t) >= 20}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/crawl_evaluation.json").write_text(json.dumps(res, indent=2, default=float, ensure_ascii=False))
    c = res["coverage"]
    print(f"coverage: {c['attempted']} attempted, {c['crawled']} crawlable, {c['blocked']} blocked by bot protection")
    pv = res["prevalence"]
    print(f"{pv['n_sites']} sites, {pv['share_sites_with_any_pattern']:.1%} with >=1 pattern")
    for c, v in sorted(pv["by_category"].items(), key=lambda x: -x[1]):
        print(f"  {c:24s} {v:.1%}")
    if "evaluation" in res:
        b = res["evaluation"]["binary"]
        print(f"vs gold ({b['n']} items): P={b['precision']:.3f} R={b['recall']:.3f} F1={b['f1']:.3f} kappa={b['kappa']:.3f}")
    print("-> results/crawl_evaluation.json")


if __name__ == "__main__":
    main()
