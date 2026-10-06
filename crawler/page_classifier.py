from urllib.parse import urlparse


def classify_page(url):
    path = urlparse(url).path.lower()

    if "/catalogue/category/" in path:
        return "category"

    if "/catalogue/page-" in path:
        return "pagination"

    if "/catalogue/" in path and path.endswith("/index.html"):
        return "product"

    if path in ["/", "/index.html"]:
        return "homepage"

    return "other"