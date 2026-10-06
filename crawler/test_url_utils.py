from url_utils import clean_url


base_url = "https://example.com/products/"

test_links = [
    "/shoes",
    "https://example.com/about",
    "#reviews",
    "javascript:void(0)",
    "mailto:test@example.com",
    "/shoes#reviews"
]

for link in test_links:
    print(link, "->", clean_url(base_url, link))