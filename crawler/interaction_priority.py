def get_interaction_priority(text="", url=""):
    text_lower = text.lower()
    url_lower = url.lower()

    if "catalogue/" in url_lower and "category/" not in url_lower and "page-" not in url_lower:
        return 8

    if "next" in text_lower or "page-" in url_lower:
        return 5

    if "category/" in url_lower:
        return 4

    if text_lower in ["home", "books to scrape"]:
        return 1

    return 2

def get_interaction_type(text="", url=""):
    text_lower = text.lower()
    url_lower = url.lower()

    if "catalogue/" in url_lower and "category/" not in url_lower and "page-" not in url_lower:
        return "product_link"

    if "category/" in url_lower:
        return "category_link"

    if "page-" in url_lower or "next" in text_lower:
        return "pagination"

    if text_lower in ["home", "books to scrape"]:
        return "navigation"

    return "other"