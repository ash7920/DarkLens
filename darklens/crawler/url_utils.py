"""URL normalisation and same-site checks."""
from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

# Query parameters that only track marketing; dropping them avoids crawling the
# same page many times under different URLs.
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "ref", "ref_", "_ga",
    "srsltid", "trk", "cmp", "affid",
}

SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".pdf", ".zip",
    ".mp4", ".mp3", ".avi", ".mov", ".css", ".js", ".xml", ".json", ".woff",
    ".woff2", ".ttf", ".doc", ".docx", ".xls", ".xlsx", ".rss",
)


def clean_url(base_url: str, link: str | None) -> str | None:
    """Turn a raw href into an absolute, normalised http(s) URL, or None."""
    if not link:
        return None
    link = link.strip()
    if link.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
        return None

    parsed = urlparse(urljoin(base_url, link))
    if parsed.scheme not in ("http", "https"):
        return None
    if parsed.path.lower().endswith(SKIP_EXTENSIONS):
        return None

    query = urlencode(
        [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
         if k.lower() not in TRACKING_PARAMS]
    )
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    return urlunparse((parsed.scheme, netloc, path, "", query, ""))


def site_key(url: str) -> str:
    """Host without a leading 'www.' — used for same-site checks."""
    host = urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def same_site(url: str, start_url: str) -> bool:
    """True if `url` is on the same site (allowing www./sub-domains of it)."""
    a, b = site_key(url), site_key(start_url)
    return a == b or a.endswith("." + b)


def domain_slug(url: str) -> str:
    return site_key(url).replace(".", "_").replace(":", "_")
