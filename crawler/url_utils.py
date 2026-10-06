from urllib.parse import urljoin, urlparse


def clean_url(base_url, link):
    if not link:
        return None

    absolute_url = urljoin(base_url, link)

    parsed = urlparse(absolute_url)

    if parsed.scheme not in ["http", "https"]:
        return None

    return absolute_url.split("#")[0]