"""
Prioritise *on-page* interactions (V3): which safe element to click first.

Clicks that reveal hidden, dark-pattern-relevant content are preferred:
cookie-settings layers (interface interference / pre-ticked consent),
popup decline buttons (confirmshaming), expanders (hidden costs, delivery
fees), variant selectors (pre-selected expensive options).
"""
from __future__ import annotations

from .keywords import CONDITIONAL_ACTIONS, REVEAL_ACTIONS

TYPE_PRIORITY = {
    "cookie_settings": 10,
    "close_popup": 9,
    "add_to_cart": 8,
    "consent_reject": 7,
    "expand": 6,
    "variant": 5,
    "other": 1,
}


def get_interaction_type(text: str = "", url: str = "") -> str:
    t = (text or "").lower().strip()
    if any(w in t for w in CONDITIONAL_ACTIONS):
        return "add_to_cart"
    for itype in ("cookie_settings", "consent_reject", "close_popup", "expand", "variant"):
        if any(w == t or (len(w) > 2 and w in t) for w in REVEAL_ACTIONS[itype]):
            return itype
    return "other"


def get_interaction_priority(text: str = "", url: str = "") -> int:
    return TYPE_PRIORITY[get_interaction_type(text, url)]
