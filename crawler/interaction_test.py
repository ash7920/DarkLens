from playwright.sync_api import sync_playwright # type: ignore

from safe_interaction import is_safe_interaction
from interaction_priority import get_interaction_priority
from url_utils import clean_url


def main():
    url = "https://books.toscrape.com/catalogue/category/books/mystery_3/index.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded")

        candidates = []
        seen_urls = set()

        for link in page.locator("a").all():
            text = link.inner_text().strip()
            href = link.get_attribute("href")
    
            cleaned_url = clean_url(page.url, href)

            if not cleaned_url:
                continue

            safe = is_safe_interaction(text, cleaned_url)

            if not safe:
                continue

            if cleaned_url in seen_urls:
                continue

            seen_urls.add(cleaned_url)

            priority = get_interaction_priority(text, cleaned_url)

            candidates.append((priority, link, text, cleaned_url))

        print("\nSAFE INTERACTIONS:")

        for priority, _, text, href in candidates:
            print(priority, "->", text, "|", href)

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)

            priority, link, text, href = candidates[0]

            print("\nSELECTED:")
            print("Priority:", priority)
            print("Text:", text)
            print("URL:", href)

            before_url = page.url
            before_title = page.title()

            link.click()

            page.wait_for_load_state("domcontentloaded")

            after_url = page.url
            after_title = page.title()

            print("\nAFTER INTERACTION:")
            print("Before URL:", before_url)
            print("After URL:", after_url)
            print("Before Title:", before_title)
            print("After Title:", after_title)

        browser.close()


if __name__ == "__main__":
    main()