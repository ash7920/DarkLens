"""
Controlled test-bed experiment: crawl DarkMart (injected patterns) and FairMart
(clean twin), run detection, and score against testbed/ground_truth.json.

    python scripts/eval_testbed.py --engine offline
    python scripts/eval_testbed.py --engine llm            # needs an API key

Reports
  - crawler coverage: which page types were reached
  - instance recall on DarkMart: share of injected instances matched by a
    predicted dark segment on the same page with the same category
  - false-positive rate on FairMart: dark predictions on a site with none
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.crawler.crawler import CrawlConfig, crawl_site  # noqa: E402
from darklens.pipeline import run  # noqa: E402

PORT = 8765


def page_key(url: str) -> str:
    return url.rstrip("/").split("/")[-1].replace(".html", "")


def match(gt: dict, preds: list[dict]) -> dict | None:
    best, best_r = None, 0.0
    for p in preds:
        if (gt["page"] != "*" and page_key(p["url"]) != gt["page"]) or p["label"] != gt["category"]:
            continue
        a, b = gt["text"].lower(), p["text"].lower()
        r = max(SequenceMatcher(None, a, b).ratio(), 1.0 if (b[:25] in a or a[:25] in b) else 0.0)
        if r > best_r:
            best, best_r = p, r
    return best if best_r >= 0.5 else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="offline", choices=["offline", "llm", "auto"])
    ap.add_argument("--mode", default="multistage", choices=["multistage", "single"])
    ap.add_argument("--recrawl", action="store_true")
    a = ap.parse_args()

    subprocess.run([sys.executable, str(ROOT / "testbed/build_testbed.py")], check=True)
    server = subprocess.Popen([sys.executable, "-m", "http.server", str(PORT), "--directory", str(ROOT / "testbed")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    out = {}
    try:
        for shop in ("darkshop", "fairshop"):
            cdir = ROOT / f"data/testbed_crawl/{shop}"
            if a.recrawl or not any(cdir.glob("*/summary.json")):
                cfg = CrawlConfig(max_pages=14, max_depth=3, delay_s=0.2, respect_robots=False, settle_ms=1500)
                crawl_site(f"http://localhost:{PORT}/{shop}/index.html", cdir, cfg)
            pred_path = ROOT / f"data/testbed_crawl/{shop}_{a.engine}_{a.mode}.jsonl"
            out[shop] = {"pipeline": run(cdir, pred_path, engine=a.engine, mode=a.mode)}
            out[shop]["crawl"] = json.loads(next(cdir.glob("*/summary.json")).read_text(encoding="utf-8"))["page_types"]
            out[shop]["preds"] = [json.loads(l) for l in open(pred_path, encoding="utf-8")]
    finally:
        server.terminate()

    gt = json.loads((ROOT / "testbed/ground_truth.json").read_text(encoding="utf-8"))
    dark_preds = [p for p in out["darkshop"]["preds"] if p["label"] != "not_dark"]
    crawled_pages = {page_key(p["url"]) for p in out["darkshop"]["preds"]}
    per_cat: dict = {}
    matched = []
    for g in gt:
        m = match(g, dark_preds)
        reachable = g["page"] == "*" or g["page"] in crawled_pages
        per_cat.setdefault(g["category"], {"total": 0, "found": 0, "reachable": 0})
        per_cat[g["category"]]["total"] += 1
        per_cat[g["category"]]["reachable"] += int(reachable)
        per_cat[g["category"]]["found"] += int(m is not None)
        matched.append({**g, "found": m is not None, "reachable": reachable,
                        "pred_text": m["text"] if m else None})
    # precision on darkshop: a dark prediction is correct if it matches some GT instance on that page
    tp_preds = sum(1 for p in dark_preds if any(
        p["label"] == g["category"] and match(g, [p]) for g in gt))
    fair_fp = [p for p in out["fairshop"]["preds"] if p["label"] != "not_dark"]
    # distinct texts, since the same banner/popup repeats on many pages
    uniq = lambda ps: len({(page_key(p["url"]), p["text"]) for p in ps})  # noqa: E731
    res = {
        "engine": a.engine, "mode": a.mode,
        "detector": out["darkshop"]["pipeline"]["detector"],
        "ground_truth_instances": len(gt),
        "crawl_coverage": {"darkshop": out["darkshop"]["crawl"], "fairshop": out["fairshop"]["crawl"],
                           "gt_instances_on_crawled_pages": sum(m["reachable"] for m in matched)},
        "instance_recall": sum(m["found"] for m in matched) / len(gt),
        "instance_recall_reachable": sum(m["found"] for m in matched) / max(1, sum(m["reachable"] for m in matched)),
        "darkshop_dark_predictions": len(dark_preds),
        "darkshop_prediction_precision": tp_preds / max(1, len(dark_preds)),
        "fairshop_false_positives": len(fair_fp),
        "fairshop_false_positive_unique": uniq(fair_fp),
        "fairshop_fp_examples": sorted({f"{p['label']}: {p['text'][:80]}" for p in fair_fp})[:20],
        "per_category": per_cat,
        "missed": [f"{m['page']} | {m['category']} | {m['text']}" for m in matched if not m["found"]],
        "prefilter_reduction": out["darkshop"]["pipeline"]["prefilter_reduction"],
    }
    Path(ROOT / "results").mkdir(exist_ok=True)
    (ROOT / f"results/testbed_{a.engine}_{a.mode}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("missed", "fairshop_fp_examples")}, indent=2))
    print("missed:", *res["missed"], sep="\n  ")
    print("fairshop FPs:", *res["fairshop_fp_examples"], sep="\n  ")


if __name__ == "__main__":
    main()
