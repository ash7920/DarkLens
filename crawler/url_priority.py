from urllib.parse import urlparse


def get_priority(url):
    path = urlparse(url).path.lower()

    if "checkout" in path:
        return 10

    if "cart" in path or "basket" in path:
        return 9

    if "/product" in path or "/catalogue/" in path:
        return 8

    if "/category/" in path:
        return 5

    if path in ["/", "/index.html"]:
        return 3

    return 1