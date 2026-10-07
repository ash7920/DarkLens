from urllib.parse import urlparse


UNSAFE_WORDS = [
    "checkout",
    "payment",
    "delete",
    "remove-account",
    "logout",
    "add to basket",
    "add to cart",
    "place order"
]


def is_safe_interaction(text="", url=""):
    combined = f"{text} {url}".lower()

    for word in UNSAFE_WORDS:
        if word in combined:
            return False

    return True