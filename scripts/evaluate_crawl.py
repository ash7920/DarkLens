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


def wilson(k: int, n: int, z: float = 1.96) -> list[float]:
    if not n:
        return [0.0, 1.0]
    import math
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [max(0.0, (c - h) / d), min(1.0, (c + h) / d)]


def stratified_estimates(rows: list[tuple[str, int, int]], units: dict[str, float], n_boot: int = 5000,
                         seed: int = 13) -> dict:
    """Population precision/recall from a stratified sample.

    rows: (stratum, gold_dark, predicted_dark) per labelled element; units: elements per stratum in the
    crawl.  Within a stratum the prediction is constant (flagged = dark, cleared/filtered = not dark),
    so the estimate is driven by each stratum's share of truly dark elements.  Intervals come from a
    bootstrap that resamples inside each stratum."""
    import random
    by = defaultdict(list)
    for st, g, p in rows:
        by[st].append((g, p))

    def est(b):
        tp = fp = fn = 0.0
        for st, v in b.items():
            if not v:
                continue
            w = units[st] / len(v)
            tp += w * sum(1 for g, p in v if g and p)
            fp += w * sum(1 for g, p in v if not g and p)
            fn += w * sum(1 for g, p in v if g and not p)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        return prec, rec, tp, fn
    prec, rec, tp, fn = est(by)
    rng = random.Random(seed)
    P, R = [], []
    for _ in range(n_boot):
        b = {st: [rng.choice(v) for _ in v] for st, v in by.items()}
        p_, r_, _, _ = est(b)
        P.append(p_)
        R.append(r_)
    P.sort()
    R.sort()
    lo, hi = int(0.025 * n_boot), int(0.975 * n_boot) - 1
    strata = {st: {"n": len(v), "units": units[st], "gold_dark": sum(g for g, _ in v),
                   "dark_rate": sum(g for g, _ in v) / len(v), "dark_rate_ci95": wilson(sum(g for g, _ in v), len(v)),
                   "est_dark_units": units[st] * sum(g for g, _ in v) / len(v)} for st, v in by.items()}
    missed = fn or 1.0
    return {"precision": prec, "precision_ci95": [P[lo], P[hi]], "recall": rec, "recall_ci95": [R[lo], R[hi]],
            "est_found_units": tp, "est_missed_units": fn,
            "share_of_misses_from_prefilter": strata.get("filtered", {}).get("est_dark_units", 0.0) / missed,
            "strata": strata}


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
    ha = ROOT / "results/human_agreement.json"  # written by scripts/annotation_results.py
    res["human_agreement"] = (json.loads(ha.read_text(encoding="utf-8")) if ha.exists()
                              else agreement(adjudicator=a.adjudicator))
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
            # stratum sizes in the crawl (weight x labelled items of that stratum, as set by the sample)
            st_of = {p["segment_id"]: sample.get(p["segment_id"], {}).get("stratum") for _, p in pairs}
            units = {}
            for st in ("flagged", "cleared", "filtered"):
                ws = [sample[i]["weight"] for i in st_of if st_of[i] == st and i in sample]
                if ws:
                    units[st] = ws[0] * sum(1 for it in sample.values() if it.get("stratum") == st)
            rows = [(st_of[p["segment_id"]], int(g != NOT_DARK), int(p["label"] != NOT_DARK))
                    for g, p in pairs if st_of.get(p["segment_id"]) in units]
            res["evaluation"]["population"] = stratified_estimates(rows, units)
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
    (ROOT / "results/crawl_evaluation.json").write_text(json.dumps(res, indent=2, default=float, ensure_ascii=False), encoding="utf-8")
    c = res["coverage"]
    print(f"coverage: {c['attempted']} attempted, {c['crawled']} crawlable, {c['blocked']} blocked by bot protection")
    pv = res["prevalence"]
    print(f"{pv['n_sites']} sites, {pv['share_sites_with_any_pattern']:.1%} with >=1 pattern")
    for c, v in sorted(pv["by_category"].items(), key=lambda x: -x[1]):
        print(f"  {c:24s} {v:.1%}")
    if "evaluation" in res:
        b = res["evaluation"]["binary"]
        s = res["evaluation"]["binary_sample"]
        print(f"on the labelled sample ({s['n']} items): P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f} kappa={s['kappa']:.3f}")
        pop = res["evaluation"].get("population")
        if pop:
            print(f"whole crawl (weighted): precision {pop['precision']:.3f} [{pop['precision_ci95'][0]:.2f}-{pop['precision_ci95'][1]:.2f}], "
                  f"recall {pop['recall']:.3f} [{pop['recall_ci95'][0]:.2f}-{pop['recall_ci95'][1]:.2f}]")
            for st, d in pop["strata"].items():
                print(f"  {st:9s} {d['gold_dark']:3d}/{d['n']:3d} dark ({d['dark_rate']:.1%}), ~{d['est_dark_units']:.0f} of {d['units']:.0f} elements")
    print("-> results/crawl_evaluation.json")


if __name__ == "__main__":
    main()
