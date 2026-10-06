from page_classifier import classify_page


test_urls = [
    "https://books.toscrape.com/",
    "https://books.toscrape.com/index.html",
    "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html",
    "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
    "https://books.toscrape.com/catalogue/page-2.html"
]


for url in test_urls:
    print(classify_page(url), "->", url)