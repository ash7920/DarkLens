"""
Generic page-type classifier (V1.3, generalised).

Combines three weak signals — URL path, page title and page content — into a
page type.  Works on any e-commerce site (the earlier version only matched
books.toscrape URLs, which is kept as a special case for the dev site).
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .keywords import PAGE_KEYWORDS

PAGE_TYPES = ["homepage", "product", "category", "cart", "checkout",
              "subscription", "account", "info", "pagination", "other"]

_PRICE_RE = re.compile(r"(€|£|\$|eur|zł|kr)\s?\d|\d[\d.,]*\s?(€|£|eur|zł|kr)", re.I)
_ADD_TO_CART_RE = re.compile(
    r"add to (cart|basket|bag)|in den warenkorb|ajouter au panier|añadir a(l carrito| la cesta)|"
    r"aggiungi al carrello|in winkelwagen|do koszyka|adicionar ao carrinho", re.I)


def _path_type(path: str) -> str | None:
    # Dev site (books.toscrape) rules kept for backward compatibility.
    if "/catalogue/category/" in path:
        return "category"
    if "/catalogue/page-" in path or re.search(r"[?&/]page[=-]\d+", path):
        return "pagination"
    if "/catalogue/" in path and path.endswith("/index.html"):
        return "product"

    tokens = set(t for t in re.split(r"[/\-_.?=&]+", path) if t)
    for page_type in ("checkout", "cart", "subscription", "account", "info", "product", "category"):
        for kw in PAGE_KEYWORDS[page_type]:
            if "/" in kw or "-" in kw:
                if kw in path:
                    return page_type
            elif kw in tokens:
                return page_type
    return None


def classify_page(url: str, title: str = "", text: str = "", buttons: list[str] | None = None) -> str:
    """Return one of PAGE_TYPES.  Title/text/buttons are optional extra evidence."""
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    if parsed.query:
        path_q = f"{path}?{parsed.query.lower()}"
    else:
        path_q = path

    if path.endswith(("/index.html", "/index.php")) and path.count("/") <= 2 and "/catalogue/" not in path:
        return "homepage"
    if path in ("", "/", "/index.html", "/index.php") or re.fullmatch(r"/[a-z]{2}(-[a-z]{2})?/?", path):
        return "homepage"

    by_path = _path_type(path_q)
    if by_path in ("checkout", "cart", "subscription", "account", "info", "pagination"):
        return by_path

    # Content evidence: product pages have one main price + an add-to-cart button.
    btn_text = " ".join(buttons or [])
    title_l = title.lower()
    if text or btn_text:
        has_cart_button = bool(_ADD_TO_CART_RE.search(btn_text) or _ADD_TO_CART_RE.search(text[:5000]))
        n_prices = len(_PRICE_RE.findall(text[:20000]))
        if has_cart_button and n_prices <= 6:
            return "product"
        if n_prices > 6:
            return "category"
        for page_type in ("checkout", "cart"):
            if any(kw.strip("/") in title_l for kw in PAGE_KEYWORDS[page_type]):
                return page_type

    return by_path or "other"
