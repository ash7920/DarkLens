"""
Safe interaction policy (V3).

Three tiers:
  BLOCKED      – could spend money, submit personal data or change account
                 state (pay, place order, sign up, delete, log out ...).  Never.
  CONDITIONAL  – add-to-cart.  Reversible, and needed to see cart/checkout
                 patterns (Mathur et al. 2019 did the same).  Only when
                 allow_add_to_cart=True.
  SAFE         – everything else that is a click on a link/button.

Form submission and typing personal information are never performed.
"""
from __future__ import annotations

from .keywords import BLOCKED_ACTIONS, CONDITIONAL_ACTIONS

BLOCKED_URL_PARTS = [
    "logout", "signout", "sign-out", "delete", "remove-account", "/pay", "payment",
    "place-order", "placeorder", "confirm-order", "/order/submit",
]


def interaction_tier(text: str = "", url: str = "") -> str:
    t = (text or "").lower().strip()
    u = (url or "").lower()
    if any(p in u for p in BLOCKED_URL_PARTS):
        return "blocked"
    if any(w in t for w in CONDITIONAL_ACTIONS):
        return "conditional"
    if any(w in t for w in BLOCKED_ACTIONS):
        return "blocked"
    return "safe"


def is_safe_interaction(text: str = "", url: str = "", allow_add_to_cart: bool = False) -> bool:
    tier = interaction_tier(text, url)
    if tier == "blocked":
        return False
    if tier == "conditional":
        return allow_add_to_cart
    return True
