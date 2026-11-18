"""
Data preprocessing for crawled pages (block diagram stage 3):
HTML/text cleaning, UI extraction, standardisation into *segments*.

A segment is the unit that gets classified: one visible text block, button,
link, checkbox/radio (with its checked state) or select (with the selected
option), with its page context and visual cues.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

WS = re.compile(r"\s+")
PRICE_ONLY = re.compile(r"^[\s€£$]*[\d.,]+\s*(€|£|\$|eur|zł|kr)?\s*$", re.I)
NAV_WORDS = {"home", "menu", "search", "login", "sign in", "account", "help", "contact", "about us",
             "privacy policy", "terms", "imprint", "impressum", "faq", "next", "previous", "back",
             "close", "cart", "basket", "bag", "shop", "women", "men", "kids", "sale"}


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("​", "").replace("\xa0", " ")
    return WS.sub(" ", text).strip()


def _rgb(s: str):
    m = re.findall(r"[\d.]+", s or "")
    return tuple(float(x) for x in m[:3]) if len(m) >= 3 else None


def _is_trivial(text: str) -> bool:
    t = text.lower()
    return (len(t) < 3 or PRICE_ONLY.match(t) is not None or t in NAV_WORDS
            or len(t.split()) > 80)


def ui_descriptor(el: dict) -> str:
    """Human/LLM-readable description of an element's UI role and state."""
    kind = el.get("kind", "text")
    if kind in ("checkbox", "radio"):
        state = "PRE-TICKED" if el.get("checked") else "unticked"
        vis = "" if el.get("visible", True) else ", hidden layer"
        return f"[{kind}, {state}{vis}]"
    if kind == "select":
        return "[dropdown, default selection shown]"
    tag = {"button": "button", "link": "link"}.get(kind, "text")
    extras = []
    if el.get("in_overlay"):
        extras.append("popup/overlay")
    fs = el.get("font_size") or 0
    if fs and fs <= 11:
        extras.append(f"small {fs:.0f}px")
    elif fs >= 20:
        extras.append(f"large {fs:.0f}px")
    return f"[{tag}{', ' + ', '.join(extras) if extras else ''}]"


DECISION_PAGES = {"subscription", "checkout", "cart"}


def choice_asymmetry(elements: list[dict], page_type: str | None = None) -> list[dict]:
    """Detect choices where one option is far more prominent than the other
    (interface-interference cue).  Compares button/link areas inside a popup /
    banner, or on decision pages (cancellation, cart, checkout)."""
    on_decision_page = page_type in DECISION_PAGES
    overlay_ctrls = [e for e in elements if (e.get("in_overlay") or (on_decision_page and e.get("kind") == "button")
                                             or (on_decision_page and (e.get("font_size") or 99) <= 12))
                     and e.get("kind") in ("button", "link")
                     and e.get("visible", True) and e.get("bbox")]
    out = []
    if len(overlay_ctrls) < 2:
        return out
    areas = sorted(((e["bbox"][2] * e["bbox"][3], e) for e in overlay_ctrls), key=lambda x: -x[0])
    used = set()
    for i, (big_area, big) in enumerate(areas):
        if big.get("dl_id") in used:
            continue
        for area, small in areas[i + 1:]:
            if small.get("dl_id") in used:
                continue
            # the two choices must be near each other (same banner / dialog / form)
            if abs((small["bbox"][1] + small["bbox"][3] / 2) - (big["bbox"][1] + big["bbox"][3] / 2)) > 250:
                continue
            if bool(small.get("in_overlay")) != bool(big.get("in_overlay")):
                continue
            font_ratio = (big.get("font_size") or 0) / max(1.0, small.get("font_size") or 1.0)
            if area > 0 and (big_area / area >= 3 or (font_ratio >= 1.6 and big["kind"] != small["kind"])):
                out.append({
                    "text": f"'{big['text'][:60]}' (large, {big['bbox'][2]}x{big['bbox'][3]}px) vs "
                            f"'{small['text'][:60]}' (small, {small['bbox'][2]}x{small['bbox'][3]}px)",
                    "ratio": round(big_area / area, 1),
                    "bbox": big["bbox"],
                })
                used.update({big.get("dl_id"), small.get("dl_id")})
                break
        if len(out) >= 3:
            break
    return out


def page_segments(record: dict, min_len: int = 3) -> list[dict]:
    """Turn one crawled page state (a pages.jsonl record) into classification segments."""
    segs, seen = [], set()
    # texts that belong to a form control are represented by the control itself
    control_texts = {clean_text(e.get("text", "")).lower() for e in record.get("elements", [])
                     if e.get("kind") in ("checkbox", "radio")}
    for el in record.get("elements", []):
        if el.get("kind") == "text" and clean_text(el.get("text", "")).lower() in control_texts:
            continue
        text = clean_text(el.get("text", ""))
        if el.get("kind") not in ("checkbox", "radio", "select") and _is_trivial(text):
            continue
        if len(text) < min_len:
            continue
        key = (text.lower(), el.get("kind") in ("checkbox", "radio"), el.get("checked"))
        if key in seen:
            continue
        seen.add(key)
        segs.append({
            "segment_id": hashlib.sha1(f"{record.get('state_id')}|{el.get('dl_id')}|{text}".encode()).hexdigest()[:16],
            "state_id": record.get("state_id"),
            "site": record.get("site"),
            "url": record.get("url"),
            "page_type": record.get("page_type"),
            "state_label": record.get("label"),
            "language": record.get("language"),
            "country": record.get("country", ""),
            "sector": record.get("sector", ""),
            "kind": el.get("kind"),
            "ui": ui_descriptor(el),
            "text": text,
            "checked": el.get("checked"),
            "in_overlay": el.get("in_overlay", False),
            "bbox": el.get("bbox"),
            "screenshot": record.get("screenshot"),
        })
    for asym in choice_asymmetry(record.get("elements", []), record.get("page_type")):
        segs.append({
            "segment_id": hashlib.sha1(f"{record.get('state_id')}|asym|{asym['text']}".encode()).hexdigest()[:16],
            "state_id": record.get("state_id"), "site": record.get("site"), "url": record.get("url"),
            "page_type": record.get("page_type"), "state_label": record.get("label"),
            "language": record.get("language"), "country": record.get("country", ""),
            "sector": record.get("sector", ""), "kind": "choice_pair",
            "ui": f"[two choices in a popup, size ratio {asym['ratio']}:1]",
            "text": asym["text"], "checked": None, "in_overlay": True, "bbox": asym["bbox"],
            "screenshot": record.get("screenshot"),
        })
    return segs


def segment_as_prompt_line(seg: dict) -> str:
    return f"{seg['ui']} {seg['text']}"


def load_crawl(crawl_dir: str | Path) -> list[dict]:
    """All page-state records from a crawl output directory."""
    records = []
    for f in sorted(Path(crawl_dir).glob("*/pages.jsonl")):
        with open(f, encoding="utf-8") as fh:
            records.extend(json.loads(line) for line in fh if line.strip())
    return records
