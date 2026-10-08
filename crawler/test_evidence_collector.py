from playwright.sync_api import sync_playwright # type: ignore

from evidence_collector import (
    collect_page_state,
    create_interaction_evidence,
    compare_page_states
)
import json


def main():
    url = "https://books.toscrape.com/"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url, wait_until="domcontentloaded")

        before = collect_page_state(page)

        page.goto(
            "https://books.toscrape.com/catalogue/sharp-objects_997/index.html",
            wait_until="domcontentloaded"
        )

        after = collect_page_state(page)

        before["page_type"] = "homepage"
        after["page_type"] = "product"

        changes = compare_page_states(before, after)

        print("\nCHANGES:")
        print(changes)

        interaction = {
            "text": "Sharp Objects",
            "url": page.url
        }

        evidence = create_interaction_evidence(
            before,
            after,
            interaction
        )

        with open("interaction_evidence.json", "w", encoding="utf-8") as file:
            json.dump(evidence, file, indent=4, ensure_ascii=False)

        print("\nINTERACTION:")
        print(evidence["interaction"])

        print("\nBEFORE:")
        print(evidence["before"]["url"])
        print(evidence["before"]["title"])

        print("\nAFTER:")
        print(evidence["after"]["url"])
        print(evidence["after"]["title"])

        browser.close()


if __name__ == "__main__":
    main()