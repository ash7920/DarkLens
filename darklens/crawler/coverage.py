"""
Crawl coverage: which sites could actually be crawled, and why the others could not.

A large share of big retailers refuse automated browsers (Cloudflare "Just a moment...",
Akamai "Access Denied", captchas).  DarkLens does not try to get around these; it records
the site as not crawlable and reports the numbers.  Prevalence is then computed only over
crawlable sites, so a block page is never counted as "no dark patterns".

    python -m darklens.crawler.coverage            # table + totals, writes data/crawl/_coverage.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

# Lower-cased substrings of page titles / visible text that mean "bot protection answered,
# not the shop".  Ordered: the first match names the reason.
BLOCK_MARKERS = [
    ("just a moment", "bot protection (Cloudflare challenge)"),
    ("attention required", "bot protection (Cloudflare)"),
    ("access denied", "bot protection (access denied)"),
    ("confirm you are human", "bot protection (human check)"),
    ("verify you are human", "bot protection (human check)"),
    ("security checkpoint", "bot protection (Vercel checkpoint)"),
    ("captcha", "bot protection (captcha)"),
    ("bot detected", "bot protection (bot detected)"),
    ("are you a robot", "bot protection (human check)"),
    ("pardon our interruption", "bot protection (human check)"),
    ("request unsuccessful", "bot protection (Incapsula)"),
    ("blokada", "bot protection (blocked)"),
    ("403 forbidden", "bot protection (403 forbidden)"),
    ("invalid url", "bot protection (Akamai reference error)"),
    ("maintenance", "unavailable (maintenance page)"),
]

STATUSES = ("crawled", "blocked", "unavailable", "robots", "unreachable", "empty")


def block_reason(title: str, text: str = "") -> str | None:
    """Reason string if a page is a bot-protection / unavailable page, else None."""
    t = (title or "").lower()
    body = (text or "")[:600].lower()
    for marker, reason in BLOCK_MARKERS:
        if marker in t or (marker in body and len(text or "") < 1500):
            return reason
    return None


def site_status(summary: dict, first_page: dict | None) -> tuple[str, str]:
    """(status, detail) for one site directory."""
    if summary.get("status") in STATUSES and summary.get("status") != "crawled":
        return summary["status"], summary.get("status_detail", "")
    pages = summary.get("pages", 0) or 0
    if first_page is not None:
        reason = block_reason(first_page.get("title", ""), first_page.get("text", ""))
        if reason:
            return ("unavailable" if reason.startswith("unavailable") else "blocked"), reason
    if pages >= 2:
        return "crawled", ""
    if summary.get("fatal_error"):
        return "unreachable", summary["fatal_error"][:120]
    if pages == 0:
        if summary.get("robots_blocked"):
            return "robots", "robots.txt disallows the start page"
        errs = summary.get("errors") or []
        return "unreachable", (errs[0][:120] if errs else "no page loaded")
    return "empty", "only one page captured (slow or script-heavy site); worth a retry"


def first_page_of(site_dir: Path) -> dict | None:
    p = site_dir / "pages.jsonl"
    if not p.exists():
        return None
    with open(p, encoding="utf-8") as f:
        line = f.readline()
    return json.loads(line) if line.strip() else None


def coverage(crawl_dir: str | Path = "data/crawl") -> dict:
    sites = {}
    for s in sorted(Path(crawl_dir).glob("*/summary.json")):
        summary = json.loads(s.read_text(encoding="utf-8"))
        status, detail = site_status(summary, first_page_of(s.parent))
        sites[s.parent.name] = {"url": summary.get("start_url", ""), "status": status, "detail": detail,
                                "pages": summary.get("pages", 0), "reached_cart": summary.get("reached_cart", False),
                                "country": summary.get("country", ""), "sector": summary.get("sector", ""),
                                # retry runs are marked, or recognisable by their 60 s page timeout
                                "retried": bool(summary.get("retried")) or
                                (summary.get("config") or {}).get("nav_timeout_ms", 0) >= 60000}
    counts = Counter(v["status"] for v in sites.values())
    crawled = [v for v in sites.values() if v["status"] == "crawled"]
    out = {
        "attempted": len(sites),
        "crawled": counts.get("crawled", 0),
        "blocked": counts.get("blocked", 0),
        "unavailable": counts.get("unavailable", 0),
        "robots": counts.get("robots", 0),
        "unreachable": counts.get("unreachable", 0),
        "empty": counts.get("empty", 0),
        "crawled_reached_cart": sum(1 for v in crawled if v["reached_cart"]),
        "crawled_pages": sum(v["pages"] for v in crawled),
        "crawled_countries": len({v["country"] for v in crawled if v["country"]}),
        "block_reasons": dict(Counter(v["detail"] for v in sites.values() if v["status"] == "blocked")),
        "sites": sites,
    }
    return out


def crawlable_sites(crawl_dir: str | Path = "data/crawl") -> set[str]:
    return {k for k, v in coverage(crawl_dir)["sites"].items() if v["status"] == "crawled"}


def main():
    ap = argparse.ArgumentParser(description="Crawl coverage report")
    ap.add_argument("--crawl", default="data/crawl")
    ap.add_argument("--all", action="store_true", help="list every site, not only the ones that failed")
    a = ap.parse_args()
    cov = coverage(a.crawl)
    for name, v in sorted(cov["sites"].items(), key=lambda kv: (kv[1]["status"] != "crawled", kv[1]["status"], kv[0])):
        if a.all or v["status"] != "crawled":
            print(f"{v['status']:12s} {v['url'][:40]:40s} pages={v['pages']:<3} {v['detail']}")
    print("-" * 70)
    print(f"attempted {cov['attempted']} | crawled {cov['crawled']} ({cov['crawled_reached_cart']} reached the basket, "
          f"{cov['crawled_pages']} pages, {cov['crawled_countries']} countries) | blocked {cov['blocked']} | "
          f"unavailable {cov['unavailable']} | robots {cov['robots']} | unreachable {cov['unreachable']} | "
          f"empty {cov['empty']}")
    not_retried = [v for v in cov["sites"].values() if v["status"] in ("unreachable", "empty") and not v["retried"]]
    if not_retried:
        print(f"{len(not_retried)} unreachable/empty site(s) not retried yet. Retry once with:")
        print("  python -m darklens.crawler.run_sites --retry-failed --headed --sites config/sites_eu.csv "
              "config/sites_eu_extra.csv config/sites_eu_extra2.csv")
    out = Path(a.crawl) / "_coverage.json"
    out.write_text(json.dumps(cov, indent=2, ensure_ascii=False), encoding="utf-8")
    Path("results").mkdir(exist_ok=True)
    Path("results/crawl_coverage.json").write_text(
        json.dumps({k: v for k, v in cov.items() if k != "sites"}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
