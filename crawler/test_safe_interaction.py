from safe_interaction import is_safe_interaction


test_cases = [
    ("A Light in the Attic", "catalogue/a-light-in-the-attic_1000/index.html"),
    ("Next", "catalogue/page-2.html"),
    ("Mystery", "catalogue/category/books/mystery_3/index.html"),
    ("Add to basket", ""),
    ("Checkout", "/checkout"),
    ("Place order", "/order"),
    ("Delete account", "/delete-account")
]


for text, url in test_cases:
    print(
        is_safe_interaction(text, url),
        "->",
        text,
        "|",
        url
    )