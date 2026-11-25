import json
from playwright.sync_api import sync_playwright # type: ignore


def main():
    url = "https://example.com"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url, wait_until="networkidle")

        links = []

        for link in page.locator("a").all():
            text = link.inner_text().strip()
            href = link.get_attribute("href")

            if href:
                links.append({
                    "text": text,
                    "url": href
                })

        buttons = []

        for button in page.locator("button").all():
            text = button.inner_text().strip()

            if text:
                buttons.append(text)

        page_data = {
            "url": page.url,
            "title": page.title(),
            "text": page.locator("body").inner_text(),
            "links": links,
            "buttons": buttons
        }

        with open("page_data.json", "w", encoding="utf-8") as file:
            json.dump(page_data, file, indent=4, ensure_ascii=False)

        page.screenshot(path="page.png", full_page=True)

        browser.close()


if __name__ == "__main__":
    main()