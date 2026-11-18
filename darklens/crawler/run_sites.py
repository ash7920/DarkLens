"""
Batch crawl a list of sites (the EU study).

    python -m darklens.crawler.run_sites --sites config/sites_eu.csv --out data/crawl --workers 3

The CSV needs a `url` column; `country`, `sector`, `language`, `name` are kept
as metadata.  Already-finished sites (summary.json present) are skipped, so the
command can be stopped and re-run safely.
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import time
from pathlib import Path

from .coverage import coverage
from .crawler import CrawlConfig, crawl_site
from .url_utils import domain_slug


def _worker(args):
    row, out, cfg_dict = args
    cfg = CrawlConfig(**cfg_dict)
    meta = {k: row.get(k, "") for k in ("name", "country", "sector", "language") if row.get(k)}
    try:
        return crawl_site(row["url"], out, cfg, site_meta=meta)
    except Exception as exc:  # one broken site must not stop the batch
        err = {"start_url": row["url"], "fatal_error": f"{type(exc).__name__}: {exc}", **meta}
        d = Path(out) / domain_slug(row["url"])
        d.mkdir(parents=True, exist_ok=True)
        (d / "summary.json").write_text(json.dumps(err, indent=2), encoding="utf-8")
        return err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sites", nargs="+", default=["config/sites_eu.csv"],
                    help="one or more site-list CSVs, e.g. config/sites_eu.csv config/sites_eu_extra.csv")
    ap.add_argument("--out", default="data/crawl")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--limit", type=int, default=0, help="only the first N sites")
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-cart", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-crawl sites that already have a summary")
    ap.add_argument("--retry-failed", action="store_true",
                    help="re-crawl only sites that were unreachable or captured a single page (never blocked ones)")
    ap.add_argument("--nav-timeout", type=int, default=0, help="page-load timeout in seconds (default 30, 60 on retry)")
    a = ap.parse_args()

    rows, seen = [], set()
    for path in a.sites:
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("url") and not r["url"].startswith("#") and domain_slug(r["url"]) not in seen:
                    seen.add(domain_slug(r["url"]))
                    rows.append(r)
    if a.limit:
        rows = rows[: a.limit]
    if a.retry_failed:
        cov = coverage(a.out)["sites"]
        todo = [r for r in rows if cov.get(domain_slug(r["url"]), {}).get("status") in ("unreachable", "empty")]
    else:
        todo = [r for r in rows if a.force or not (Path(a.out) / domain_slug(r["url"]) / "summary.json").exists()]
    print(f"{len(rows)} sites in list, {len(todo)} to crawl, {a.workers} workers")

    nav = a.nav_timeout or (60 if a.retry_failed else 30)
    cfg = CrawlConfig(max_pages=a.max_pages, max_depth=a.max_depth, delay_s=a.delay, nav_timeout_ms=nav * 1000,
                      settle_ms=4000 if a.retry_failed else 2500,
                      headless=not a.headed, allow_add_to_cart=not a.no_cart).__dict__
    t0 = time.time()
    jobs = [(r, a.out, cfg) for r in todo]
    if a.workers <= 1:
        results = [_worker(j) for j in jobs]
    else:
        with mp.get_context("spawn").Pool(a.workers) as pool:
            results = list(pool.imap_unordered(_worker, jobs))

    ok = sum(1 for r in results if "fatal_error" not in r)
    print(f"\nFinished {ok}/{len(results)} sites in {time.time() - t0:.0f}s")
    print("See which sites were crawlable:  python -m darklens.crawler.coverage")


if __name__ == "__main__":
    main()
