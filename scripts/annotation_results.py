"""
Ground truth and agreement numbers for the crawl evaluation (single trained annotator design).

    python scripts/annotation_results.py                  # annotator "ashka"
    python scripts/annotation_results.py --expert ashka --second devanshi

Reports three things and writes data/annotation/gold.jsonl from the expert's labels:
  pilot       - the first round with two student annotators (devanshi, aarya) on 400 items,
                kept as reported evidence for why the guidelines and design changed
  second      - a second annotator, trained on the same guidelines, labelling the same fixed 50
                items independently (saved as "<second>-recheck" by the app's re-check mode)
  intra-rater - the expert against her own blind re-labelling of those 50 items, if she did one
  model       - the expert against an independent LLM second opinion (model_opinion.jsonl),
                a supporting check only

Output: results/human_agreement.json (read by evaluate_crawl.py and make_paper_assets.py).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sklearn.metrics import cohen_kappa_score  # noqa: E402

from darklens.evaluation import annotation  # noqa: E402
from darklens.taxonomy import NOT_DARK  # noqa: E402

ANN = ROOT / "data/annotation"


def _read(name: str) -> dict[str, dict]:
    """{segment_id: {"label", "ts"}} keeping each item's latest label."""
    p = ANN / f"labels_{name}.jsonl"
    out = {}
    if p.exists():
        for line in open(p, encoding="utf-8"):
            r = json.loads(line)
            out[r["segment_id"]] = r
    return out


def compare(a: dict[str, str], b: dict[str, str], ids=None) -> dict:
    common = sorted((set(a) & set(b)) if ids is None else (set(a) & set(b) & set(ids)))
    if not common:
        return {"n": 0}
    la, lb = [a[i] for i in common], [b[i] for i in common]
    ba, bb = [int(x != NOT_DARK) for x in la], [int(x != NOT_DARK) for x in lb]

    def kappa(x, y):
        return float(cohen_kappa_score(x, y)) if len(set(x) | set(y)) > 1 else 1.0
    return {"n": len(common),
            "raw_agreement": sum(x == y for x, y in zip(la, lb)) / len(common),
            "raw_agreement_binary": sum(x == y for x, y in zip(ba, bb)) / len(common),
            "kappa_category": kappa(la, lb), "kappa_binary": kappa(ba, bb),
            "dark_share": [sum(ba) / len(ba), sum(bb) / len(bb)]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--expert", default="ashka")
    ap.add_argument("--pilot", nargs=2, default=["devanshi", "aarya"])
    ap.add_argument("--second", default="devanshi", help="second annotator for the 50-item overlap")
    a = ap.parse_args()

    sample = {s["segment_id"]: s for s in annotation.load_sample()}
    res: dict = {"design": "single trained annotator + blind intra-rater re-check + LLM second opinion",
                 "n_sample": len(sample)}

    p1, p2 = (_read(n) for n in a.pilot)
    if p1 and p2:
        pilot = compare({k: v["label"] for k, v in p1.items()}, {k: v["label"] for k, v in p2.items()})
        pilot["annotators"] = a.pilot
        res["pilot"] = pilot

    ex = _read(a.expert)
    exl = {k: v["label"] for k, v in ex.items() if k in sample}
    res["expert"] = {"name": a.expert, "n_labelled": len(exl),
                     "dark_share": sum(v != NOT_DARK for v in exl.values()) / max(1, len(exl))}

    sc = _read(f"{a.second}-recheck") if a.second else {}
    if sc:
        second = compare(exl, {k: v["label"] for k, v in sc.items()})
        second["annotator"] = a.second
        res["second_annotator"] = second

    rc = _read(f"{a.expert}-recheck")
    if rc:
        intra = compare(exl, {k: v["label"] for k, v in rc.items()})
        gaps = [(datetime.fromisoformat(rc[i]["ts"]) - datetime.fromisoformat(ex[i]["ts"])).total_seconds() / 3600
                for i in rc if i in ex]
        intra["hours_between_passes_median"] = median(gaps) if gaps else None
        intra["hours_between_passes_min"] = min(gaps) if gaps else None
        res["intra_rater"] = intra

    mo = ANN / "model_opinion.jsonl"
    if mo.exists():
        rows = [json.loads(l) for l in open(mo, encoding="utf-8")]
        model = compare(exl, {r["segment_id"]: r["label"] for r in rows})
        model["models"] = sorted({r["model"] for r in rows})
        res["model_second_opinion"] = model

    if exl:  # ground truth = the expert's first pass
        with open(ANN / "gold.jsonl", "w", encoding="utf-8") as f:
            for i, lab in exl.items():
                f.write(json.dumps({"segment_id": i, "label": lab, "source": "expert"}) + "\n")
        res["gold_items"] = len(exl)

    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results/human_agreement.json").write_text(json.dumps(res, indent=2), encoding="utf-8")

    def line(name, d):
        if d and d.get("n"):
            print(f"{name:28s} n={d['n']:4d}  agree {d['raw_agreement']:.0%}  "
                  f"kappa category {d['kappa_category']:.2f}  kappa dark/not {d['kappa_binary']:.2f}")
    line(f"pilot ({' vs '.join(a.pilot)})", res.get("pilot"))
    print(f"{a.expert}: {len(exl)} of {len(sample)} items labelled")
    line(f"second annotator ({a.second})", res.get("second_annotator"))
    line("intra-rater (blind re-check)", res.get("intra_rater"))
    if res.get("intra_rater", {}).get("hours_between_passes_min") is not None:
        print(f"{'':28s} {res['intra_rater']['hours_between_passes_min']:.1f} h or more between the two passes")
    line("model second opinion", res.get("model_second_opinion"))
    print("-> results/human_agreement.json, data/annotation/gold.jsonl")


if __name__ == "__main__":
    main()
