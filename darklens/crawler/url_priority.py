"""
URL prioritisation (V2).  Higher score = crawled earlier.

Score = base score of the URL's likely page type + bonus from the anchor text
+ small penalty for depth.  Pages where dark patterns concentrate (checkout,
cart, product, subscription) come first.
"""
from __future__ import annotations

from .keywords import ANCHOR_HINTS
from .page_classifier import classify_page

BASE_PRIORITY = {
    "checkout": 10,
    "cart": 9,
    "subscription": 9,
    "product": 8,
    "category": 5,
    "account": 4,
    "homepage": 3,
    "pagination": 2,
    "other": 2,
    "info": 0,
}


def get_priority(url: str, anchor_text: str = "", depth: int = 0) -> float:
    page_type = classify_page(url)
    score = float(BASE_PRIORITY.get(page_type, 1))

    text = (anchor_text or "").lower()
    if text:
        for hint, words in ANCHOR_HINTS.items():
            if any(w in text for w in words):
                score += {"checkout": 3, "cart": 3, "subscription": 3, "product": 1.5, "deal": 2}[hint]
                break

    return score - 0.25 * depth
