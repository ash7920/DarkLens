"""
Human ground truth (block diagram: Evaluation Module → Human Ground Truth).

Protocol (follows Nwokeji et al. 2026 / Mansur et al. 2023 at our scale):
  1. make_sample():  stratified sample of crawled page states (by page type and
     site), plus every segment on them that reached the detector and a random
     share of filtered-out segments (to measure what the pre-filter misses).
  2. Two annotators label every item independently in the web app (Annotate tab)
     — blind to the model's prediction.
  3. agreement():   Cohen's kappa between annotators; disagreements exported for a
     third annotator (adjudicator); final gold = agreed label or adjudicated label.

Files
  data/annotation/sample.jsonl               items to label
  data/annotation/labels_<annotator>.jsonl   one line per labelled item (append-only)
  data/annotation/adjudication.csv           disagreements to resolve
  data/annotation/gold.jsonl                 final ground truth
"""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from .metrics import fleiss_kappa

ANN_DIR = Path("data/annotation")


def make_sample(predictions: str | Path, n_flagged: int = 200, n_cleared: int = 200, n_filtered: int = 100,
                seed: int = 13) -> dict:
    """Stratified sample of DISTINCT elements for human labelling.

    The unit is a distinct element of a shop (same text, kind and checkbox state), because the
    detector also classifies each distinct element once per site.  Three strata:
      flagged  - the LLM labelled it a dark pattern   (measures precision)
      cleared  - sent to the LLM, labelled not dark    (measures LLM misses)
      filtered - never sent: dropped by the pre-filter (measures pre-filter misses)
    Each sampled unit carries weight = units in its stratum / units sampled from it, so the
    evaluation can estimate precision and recall for the whole crawl.  The stratum is stored for
    the evaluation only; the annotation tool never shows it or the model's answer."""
    units: dict[tuple, dict] = {}
    for line in open(predictions, encoding="utf-8"):
        r = json.loads(line)
        key = (r["site"], r["kind"], (r["text"] or "").strip().lower(), r.get("checked"))
        u = units.get(key)
        if u is None:
            stratum = "filtered" if not r.get("sent") else ("cleared" if r["label"] == "not_dark" else "flagged")
            units[key] = {"rep": r, "stratum": stratum, "occurrences": 1}
        else:
            u["occurrences"] += 1
    rng = random.Random(seed)
    by_stratum = defaultdict(list)
    for u in units.values():
        by_stratum[u["stratum"]].append(u)
    wanted = {"flagged": n_flagged, "cleared": n_cleared, "filtered": n_filtered}
    items, report = [], {}
    for stratum, pool in sorted(by_stratum.items()):
        pool.sort(key=lambda u: u["rep"]["segment_id"])  # deterministic before shuffling
        rng.shuffle(pool)
        take = pool if wanted[stratum] < 0 else pool[: wanted[stratum]]  # -1 = every unit
        weight = len(pool) / max(1, len(take))
        report[stratum] = {"units": len(pool), "sampled": len(take), "weight": round(weight, 3)}
        for u in take:
            r = u["rep"]
            items.append({**{k: r.get(k) for k in ("segment_id", "state_id", "site", "url", "page_type", "kind",
                                                    "ui", "text", "checked", "bbox", "screenshot", "language")},
                          "stratum": stratum, "weight": weight, "occurrences": u["occurrences"]})
    rng.shuffle(items)  # annotators see the strata mixed together
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANN_DIR / "sample.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return {"items": len(items), "sites": len({i["site"] for i in items}), "strata": report}


def load_sample() -> list[dict]:
    p = ANN_DIR / "sample.jsonl"
    return [json.loads(l) for l in open(p, encoding="utf-8")] if p.exists() else []


def save_label(annotator: str, segment_id: str, label: str, note: str = "") -> None:
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    safe = "".join(c for c in annotator.lower() if c.isalnum() or c in "-_")[:40] or "anon"
    with open(ANN_DIR / f"labels_{safe}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"segment_id": segment_id, "label": label, "note": note,
                            "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}, ensure_ascii=False) + "\n")


def load_labels() -> dict[str, dict[str, str]]:
    """{annotator: {segment_id: latest label}}"""
    out = {}
    for f in ANN_DIR.glob("labels_*.jsonl"):
        name = f.stem[len("labels_"):]
        d = {}
        for line in open(f, encoding="utf-8"):
            r = json.loads(line)
            d[r["segment_id"]] = r["label"]
        out[name] = d
    return out


def agreement(annotators: list[str] | None = None, adjudicator: str | None = None) -> dict:
    labels = load_labels()
    names = annotators or sorted(n for n in labels if n != adjudicator)[:2]
    if len(names) < 2:
        return {"error": "need labels from two annotators", "annotators": list(labels)}
    a, b = labels[names[0]], labels[names[1]]
    common = sorted(set(a) & set(b))
    if not common:
        return {"error": "no overlapping items yet", "annotators": names}
    la, lb = [a[i] for i in common], [b[i] for i in common]
    bin_a = [int(x != "not_dark") for x in la]
    bin_b = [int(x != "not_dark") for x in lb]
    res = {
        "annotators": names, "n_overlap": len(common),
        "raw_agreement": sum(x == y for x, y in zip(la, lb)) / len(common),
        "cohen_kappa_category": float(cohen_kappa_score(la, lb)),
        "cohen_kappa_binary": float(cohen_kappa_score(bin_a, bin_b)) if len(set(bin_a + bin_b)) > 1 else 1.0,
    }
    others = [n for n in labels if n not in names and n != adjudicator]
    if others:  # Fleiss over all annotators on items everyone labelled
        all_names = names + others
        shared = set.intersection(*(set(labels[n]) for n in all_names))
        if shared:
            res["fleiss_kappa_all"] = fleiss_kappa([[labels[n][i] for n in all_names] for i in sorted(shared)])
            res["fleiss_annotators"] = all_names
    sample = {s["segment_id"]: s for s in load_sample()}
    disagreements = [i for i in common if a[i] != b[i]]
    adj = labels.get(adjudicator, {}) if adjudicator else {}
    gold = []
    for i in common:
        if a[i] == b[i]:
            gold.append({"segment_id": i, "label": a[i], "source": "agreed"})
        elif i in adj:
            gold.append({"segment_id": i, "label": adj[i], "source": "adjudicated"})
    with open(ANN_DIR / "adjudication.csv", "w", encoding="utf-8") as f:
        f.write("segment_id,annotator_1,annotator_2,text,url\n")
        for i in disagreements:
            t = sample.get(i, {}).get("text", "").replace('"', "'")
            f.write(f'{i},{a[i]},{b[i]},"{t}",{sample.get(i, {}).get("url", "")}\n')
    with open(ANN_DIR / "gold.jsonl", "w", encoding="utf-8") as f:
        for g in gold:
            f.write(json.dumps(g) + "\n")
    res.update({"disagreements": len(disagreements), "adjudicated": sum(1 for g in gold if g["source"] == "adjudicated"),
                "gold_items": len(gold)})
    return res
