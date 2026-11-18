"""
DarkLens site crawler — integrates V1 → V4.

    V1   BFS discovery                V2  priority queue (page type + anchor text)
    V1.1 depth / page limits, domain  V3  safe interaction exploration
    V1.2 tested on dev sites          V4  structured evidence (HTML, text, UI elements, screenshots)
    V1.3 page classification

Per site it writes:
    <out>/<domain>/pages.jsonl         one record per captured page *state*
    <out>/<domain>/interactions.jsonl  before/after evidence for each click
    <out>/<domain>/states/*.html|png   rendered HTML + full-page screenshots
    <out>/<domain>/summary.json        crawl statistics

Usage:
    python -m darklens.crawler.crawler https://books.toscrape.com --max-pages 5
"""
from __future__ import annotations

import argparse
import heapq
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.robotparser import RobotFileParser

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

from .evidence_collector import append_jsonl, collect_page_state, create_interaction_evidence, slim
from .interaction_priority import get_interaction_priority, get_interaction_type
from .page_classifier import classify_page
from .safe_interaction import is_safe_interaction
from .url_priority import get_priority
from .url_utils import clean_url, domain_slug, same_site

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Interaction types performed at most once per *site* (they are site-wide UI).
ONCE_PER_SITE = {"cookie_settings", "consent_reject"}


@dataclass
class CrawlConfig:
    max_pages: int = 15
    max_depth: int = 3
    max_interactions_per_page: int = 3
    allow_add_to_cart: bool = True
    headless: bool = True
    delay_s: float = 2.0            # politeness delay between page loads
    settle_ms: int = 2500           # wait for timers / popups to appear
    nav_timeout_ms: int = 30000
    site_timeout_s: int = 420       # hard budget per site
    respect_robots: bool = True
    locale: str = "en-GB"
    user_agent: str = DEFAULT_UA
    viewport: dict = field(default_factory=lambda: {"width": 1366, "height": 900})
    full_page_screenshots: bool = True


class RobotsGate:
    """robots.txt check fetched through the browser context (works behind proxies)."""

    def __init__(self, context, start_url: str, enabled: bool, user_agent: str):
        self.enabled = enabled
        self.ua = user_agent
        self.parser = RobotFileParser()
        self.loaded = False
        if not enabled:
            return
        from urllib.parse import urlparse
        u = urlparse(start_url)
        robots_url = f"{u.scheme}://{u.netloc}/robots.txt"
        try:
            resp = context.request.get(robots_url, timeout=10000)
            if resp.ok:
                self.parser.parse(resp.text().splitlines())
                self.loaded = True
        except Exception:
            pass

    def allowed(self, url: str) -> bool:
        if not self.enabled or not self.loaded:
            return True
        return self.parser.can_fetch(self.ua, url) and self.parser.can_fetch("*", url)


def _settle(page, cfg: CrawlConfig) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except PWTimeout:
        pass
    page.wait_for_timeout(cfg.settle_ms)


def _interaction_candidates(state: dict, page_type: str, cfg: CrawlConfig, done_site: set, cart_filled: bool):
    cands = []
    for el in state["elements"]:
        if el["kind"] not in ("button", "link", "summary") or not el["text"]:
            continue
        itype = get_interaction_type(el["text"], el.get("href") or "")
        if itype == "other":
            continue
        # Links that navigate away are handled by the queue, not as interactions,
        # unless they are in an overlay (cookie layers, popups use <a href="#">).
        href = (el.get("href") or "").strip()
        if el["kind"] == "link" and href and not href.startswith(("#", "javascript")) and not el["in_overlay"]:
            continue
        if itype in done_site:
            continue
        if itype == "add_to_cart" and (page_type != "product" or cart_filled):
            continue
        if not is_safe_interaction(el["text"], href, allow_add_to_cart=cfg.allow_add_to_cart):
            continue
        prio = get_interaction_priority(el["text"], href) + (2 if el["in_overlay"] else 0)
        cands.append({"dl_id": el["dl_id"], "text": el["text"][:120], "type": itype,
                      "priority": prio, "in_overlay": el["in_overlay"], "action": "click"})
    cands.sort(key=lambda c: -c["priority"])
    # one interaction of each type per page
    picked, types = [], set()
    for c in cands:
        if c["type"] in types:
            continue
        picked.append(c)
        types.add(c["type"])
        if len(picked) >= cfg.max_interactions_per_page:
            break
    return picked


def crawl_site(start_url: str, out_root: str | Path = "data/crawl", cfg: CrawlConfig | None = None,
               site_meta: dict | None = None, browser=None) -> dict:
    cfg = cfg or CrawlConfig()
    site_meta = site_meta or {}
    site_dir = Path(out_root) / domain_slug(start_url)
    states_dir = site_dir / "states"
    site_dir.mkdir(parents=True, exist_ok=True)
    pages_file, inter_file = site_dir / "pages.jsonl", site_dir / "interactions.jsonl"
    for f in (pages_file, inter_file):
        if f.exists():
            f.unlink()

    t0 = time.time()
    stats = {"start_url": start_url, "pages": 0, "states": 0, "interactions": 0, "errors": [],
             "page_types": {}, "robots_blocked": 0, "config": asdict(cfg), **site_meta}

    own_pw = browser is None
    pw = sync_playwright().start() if own_pw else None
    if own_pw:
        browser = pw.chromium.launch(headless=cfg.headless)
    context = browser.new_context(viewport=cfg.viewport, locale=cfg.locale, user_agent=cfg.user_agent)
    page = context.new_page()
    page.set_default_timeout(cfg.nav_timeout_ms)
    robots = RobotsGate(context, start_url, cfg.respect_robots, cfg.user_agent)
    stats["robots_loaded"] = robots.loaded

    queue: list = []
    counter = 0
    heapq.heappush(queue, (-get_priority(start_url), counter, start_url, 0, "start"))
    visited: set[str] = set()
    done_site: set[str] = set()
    cart_filled = False

    try:
        while queue and stats["pages"] < cfg.max_pages:
            if time.time() - t0 > cfg.site_timeout_s:
                stats["errors"].append("site_timeout")
                break
            neg_prio, _, url, depth, anchor = heapq.heappop(queue)
            if url in visited or depth > cfg.max_depth:
                continue
            if not robots.allowed(url):
                stats["robots_blocked"] += 1
                visited.add(url)
                continue
            visited.add(url)
            print(f"[{domain_slug(start_url)}] p={-neg_prio:.1f} d={depth} {url}")

            try:
                page.goto(url, wait_until="domcontentloaded")
                _settle(page, cfg)
                visited.add(page.url)

                state = collect_page_state(page, states_dir, "initial", full_page=cfg.full_page_screenshots)
                page_type = classify_page(state["url"], state["title"], state["text"], state["buttons"])
                record = {**state, "page_type": page_type, "depth": depth, "priority": -neg_prio,
                          "anchor_text": anchor, "site": domain_slug(start_url), **site_meta}
                append_jsonl(pages_file, record)
                stats["pages"] += 1
                stats["states"] += 1
                stats["page_types"][page_type] = stats["page_types"].get(page_type, 0) + 1

                # ---- V2: enqueue discovered links by priority -------------------------
                for link in state["links"]:
                    nxt = clean_url(page.url, link["url"])
                    if nxt and nxt not in visited and same_site(nxt, start_url):
                        counter += 1
                        heapq.heappush(queue, (-get_priority(nxt, link["text"], depth + 1),
                                               counter, nxt, depth + 1, link["text"][:80]))

                # ---- V3: safe interactions ---------------------------------------------
                for inter in _interaction_candidates(state, page_type, cfg, done_site, cart_filled):
                    if time.time() - t0 > cfg.site_timeout_s:
                        break
                    loc = page.locator(f'[data-dl-id="{inter["dl_id"]}"]')
                    if loc.count() == 0:
                        continue
                    before = state
                    try:
                        loc.first.scroll_into_view_if_needed(timeout=5000)
                        loc.first.click(timeout=8000)
                    except Exception as exc:
                        inter["error"] = str(exc)[:200]
                        continue
                    _settle(page, cfg)
                    after = collect_page_state(page, states_dir, f"after_{inter['type']}",
                                               full_page=cfg.full_page_screenshots)
                    after_type = classify_page(after["url"], after["title"], after["text"], after["buttons"])
                    before = {**before, "page_type": page_type}
                    after = {**after, "page_type": after_type}
                    evidence = create_interaction_evidence(before, after, inter)
                    evidence.update({"site": domain_slug(start_url), "page_url": url})
                    append_jsonl(inter_file, evidence)
                    append_jsonl(pages_file, {**after, "depth": depth, "priority": -neg_prio,
                                              "anchor_text": inter["text"], "parent_state": before["state_id"],
                                              "site": domain_slug(start_url), **site_meta})
                    stats["interactions"] += 1
                    stats["states"] += 1
                    if inter["type"] in ONCE_PER_SITE:
                        done_site.add(inter["type"])
                    if inter["type"] == "add_to_cart":
                        cart_filled = True
                    # newly revealed links (e.g. "view basket" in a mini-cart) go into the queue
                    for link in after["links"]:
                        nxt = clean_url(page.url, link["url"])
                        if nxt and nxt not in visited and same_site(nxt, start_url):
                            counter += 1
                            heapq.heappush(queue, (-get_priority(nxt, link["text"], depth + 1),
                                                   counter, nxt, depth + 1, link["text"][:80]))
                    # if the click navigated away, return to the page before the next click
                    if after["url"] != before["url"]:
                        page.goto(url, wait_until="domcontentloaded")
                        _settle(page, cfg)
                        state = collect_page_state(page, None, "reload")
                    else:
                        state = after

            except Exception as exc:
                msg = f"{url}: {type(exc).__name__}: {str(exc)[:200]}"
                print("  ! error", msg)
                stats["errors"].append(msg)
            time.sleep(cfg.delay_s)
    finally:
        context.close()
        if own_pw:
            browser.close()
            pw.stop()

    stats["elapsed_s"] = round(time.time() - t0, 1)
    stats["reached_cart"] = stats["page_types"].get("cart", 0) > 0
    stats["reached_checkout"] = stats["page_types"].get("checkout", 0) > 0
    (site_dir / "summary.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[{domain_slug(start_url)}] done: {stats['pages']} pages, {stats['interactions']} interactions, "
          f"{stats['elapsed_s']}s")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Crawl one site with DarkLens.")
    ap.add_argument("url")
    ap.add_argument("--out", default="data/crawl")
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--max-depth", type=int, default=3)
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--no-cart", action="store_true", help="never click add-to-cart")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--no-robots", action="store_true", help="ignore robots.txt (only for local test sites)")
    a = ap.parse_args()
    cfg = CrawlConfig(max_pages=a.max_pages, max_depth=a.max_depth, headless=not a.headed,
                      allow_add_to_cart=not a.no_cart, delay_s=a.delay, respect_robots=not a.no_robots)
    crawl_site(a.url, a.out, cfg)


if __name__ == "__main__":
    main()
