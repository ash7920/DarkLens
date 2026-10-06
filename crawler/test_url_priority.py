from url_priority import get_priority


test_urls = [
    "https://example.com/",
    "https://example.com/category/shoes",
    "https://example.com/product/running-shoes",
    "https://example.com/cart",
    "https://example.com/checkout",
    "https://example.com/about"
]


for url in test_urls:
    print(get_priority(url), "->", url)