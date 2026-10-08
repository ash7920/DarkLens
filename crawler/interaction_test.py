from playwright.sync_api import sync_playwright # type: ignore

from safe_interaction import is_safe_interaction
from interaction_priority import get_interaction_priority, get_interaction_type
from url_utils import clean_url
from page_classifier import classify_page
from evidence_collector import (
    collect_page_state,
    create_interaction_evidence,
    compare_page_states
)
import json

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

            before = collect_page_state(
                page,
                "before_interaction.png"
            )

            before["page_type"] = classify_page(before["url"])

            interaction = {
                "text": text,
                "url": href,
                "priority": priority,
                "safe": True,
                "type": get_interaction_type(text, href),
                "action": "click"
            }

            link.click()

            page.wait_for_load_state("domcontentloaded")

            after = collect_page_state(
                page,
                "after_interaction.png"
            )

            after["page_type"] = classify_page(after["url"])

            evidence = create_interaction_evidence(
            before,
            after,
            interaction
            )

            changes = compare_page_states(
                before,
                after
            )

            evidence["changes"] = changes

            with open(
                "interaction_evidence.json",
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    evidence,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

    print("\nAFTER INTERACTION:")
    print("Before URL:", before["url"])
    print("After URL:", after["url"])
    print("Before Title:", before["title"])
    print("After Title:", after["title"])


if __name__ == "__main__":
    main()