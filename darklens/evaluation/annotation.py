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


def make_sample(predictions: str | Path, n_states: int = 150, neg_share: float = 0.15, seed: int = 13,
                max_per_site: int = 4) -> dict:
    rows = [json.loads(l) for l in open(predictions, encoding="utf-8")]
    by_state = defaultdict(list)
    for r in rows:
        by_state[r["state_id"]].append(r)
    rng = random.Random(seed)
    # stratify by page type, cap per site so a few big sites don't dominate
    strata = defaultdict(list)
    for sid, segs in by_state.items():
        strata[segs[0].get("page_type") or "other"].append(sid)
    for v in strata.values():
        rng.shuffle(v)
    picked, per_site = [], defaultdict(int)
    while len(picked) < n_states and any(strata.values()):
        for pt in list(strata):
            if not strata[pt]:
                continue
            sid = strata[pt].pop()
            site = by_state[sid][0].get("site")
            if per_site[site] >= max_per_site:
                continue
            per_site[site] += 1
            picked.append(sid)
            if len(picked) >= n_states:
                break
    items = []
    for sid in picked:
        for r in by_state[sid]:
            if r.get("sent") or rng.random() < neg_share:
                items.append({k: r.get(k) for k in ("segment_id", "state_id", "site", "url", "page_type", "kind",
                                                    "ui", "text", "checked", "bbox", "screenshot", "language")})
    rng.shuffle(items)
    ANN_DIR.mkdir(parents=True, exist_ok=True)
    with open(ANN_DIR / "sample.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return {"states": len(picked), "items": len(items), "sites": len(per_site)}


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
