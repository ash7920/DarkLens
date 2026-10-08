from interaction_priority import get_interaction_priority
from interaction_priority import get_interaction_priority, get_interaction_type


test_cases = [
    ("A Light in the Attic", "catalogue/a-light-in-the-attic_1000/index.html"),
    ("Next", "catalogue/page-2.html"),
    ("Mystery", "catalogue/category/books/mystery_3/index.html"),
    ("Books to Scrape", "index.html"),
    ("About", "about.html")
]


for text, url in test_cases:
    priority = get_interaction_priority(text, url)

    print(
        priority,
        "->",
        text,
        "|",
        url
    )
print(
    get_interaction_type(
        "Sharp Objects",
        "catalogue/sharp-objects_997/index.html"
    )
)

print(
    get_interaction_type(
        "Next",
        "catalogue/page-2.html"
    )
)

print(
    get_interaction_type(
        "Mystery",
        "catalogue/category/books/mystery_3/index.html"
    )
)

print(
    get_interaction_type(
        "Home",
        "index.html"
    )
)