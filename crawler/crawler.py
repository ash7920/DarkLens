import json
import heapq
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright # type: ignore

from url_utils import clean_url
from page_classifier import classify_page
from url_priority import get_priority
from safe_interaction import is_safe_interaction
from interaction_priority import (
    get_interaction_priority,
    get_interaction_type
)

from evidence_collector import (
    collect_page_state,
    create_interaction_evidence,
    compare_page_states
)


def same_domain(url, domain):
    return urlparse(url).netloc == domain


def crawl(start_url, max_pages=5, max_depth=2):
    queue = []
    counter = 0

    heapq.heappush(queue, (-get_priority(start_url), counter, start_url, 0))

    visited = set()
    pages = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        while queue and len(visited) < max_pages:
            priority, _, url, depth = heapq.heappop(queue)

            priority = -priority

            if depth > max_depth:
                continue

            if url in visited:
                continue

            if not same_domain(url, urlparse(start_url).netloc):
                continue

            print("\nCrawling:", url)
            print("Priority:", priority)
            print("Depth:", depth)

            try:
                page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                visited.add(url)

                before = collect_page_state(
                    page,
                    "before_interaction.png"
                )

                before["page_type"] = classify_page(
                    before["url"]
                )

                links = []
                interaction_candidates = []

                for link in page.locator("a").all():

                    href = link.get_attribute("href")

                    if not href:
                        continue

                    cleaned = clean_url(url, href)

                    text = link.inner_text().strip()

                    if cleaned and is_safe_interaction(
                        text,
                        cleaned
                    ):
                        interaction_priority = get_interaction_priority(
                            text,
                            cleaned
                        )

                        interaction_type = get_interaction_type(
                            text,
                            cleaned
                        )

                        interaction_candidates.append({
                            "text": text,
                            "url": cleaned,
                            "priority": interaction_priority,
                            "type": interaction_type,
                            "safe": True,
                            "action": "click"
                        })

                    if cleaned and same_domain(
                        cleaned,
                        urlparse(start_url).netloc
                    ):
                        links.append(cleaned)

                        if cleaned not in visited:
                            counter += 1

                            link_priority = get_priority(cleaned)

                            heapq.heappush(
                                queue,
                                (
                                    -link_priority,
                                    counter,
                                    cleaned,
                                    depth + 1
                                )
                            )

                if interaction_candidates:
                        interaction = max(
                            interaction_candidates,
                            key=lambda item: item["priority"]
                        )

                print(
                        "Selected interaction:",
                        interaction["text"],
                        "->",
                        interaction["url"],
                        "| Priority:",
                        interaction["priority"],
                        "| Type:",
                        interaction["type"]
                    )

                for link in page.locator("a").all():
                    href = link.get_attribute("href")

                    if not href:
                        continue

                    cleaned = clean_url(url, href)

                    if cleaned == interaction["url"]:
                        link.click()

                        page.wait_for_load_state(
                            "domcontentloaded"
                        )

                        after = collect_page_state(
                            page,
                            "after_interaction.png"
                        )

                        after["page_type"] = classify_page(
                            after["url"]
                        )

                        evidence = create_interaction_evidence(
                            before,
                            after,
                            interaction
                        )

                        evidence["changes"] = compare_page_states(
                            before,
                            after
                        )

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

                        print(
                            "Clicked interaction:",
                            page.url
                        )

                        break
                

                page_data = {
                    "url": page.url,
                    "title": page.title(),
                    "depth": depth,
                    "page_type": classify_page(page.url),
                    "priority": priority,
                    "text": page.locator("body").inner_text(),
                    "links": links,
                    "buttons": [
                        button.inner_text().strip()
                        for button in page.locator("button").all()
                        if button.inner_text().strip()
                    ]
                }

                pages.append(page_data)

            except Exception as error:
                print("Error:", error)

        browser.close()

    with open("crawl_data.json", "w", encoding="utf-8") as file:
        json.dump(pages, file, indent=4, ensure_ascii=False)

    print("\nPages crawled:", len(pages))


if __name__ == "__main__":
    crawl(
        "https://books.toscrape.com/",
        max_pages=5,
        max_depth=2
    )