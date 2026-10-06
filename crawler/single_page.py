from playwright.sync_api import sync_playwright # type: ignore


def main():
    url = "https://example.com"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        page = browser.new_page()

        page.goto(url, wait_until="networkidle")

        print("\nURL:")
        print(page.url)

        print("\nTITLE:")
        print(page.title())

        print("\nVISIBLE TEXT:")
        print(page.locator("body").inner_text()[:2000])

        print("\nLINKS:")
        links = page.locator("a").all()

        for link in links:
            text = link.inner_text().strip()
            href = link.get_attribute("href")

            if href:
                print(text, "->", href)

        print("\nBUTTONS:")
        buttons = page.locator("button").all()

        for button in buttons:
            text = button.inner_text().strip()

            if text:
                print(text)

        page.screenshot(path="page.png", full_page=True)

        browser.close()


if __name__ == "__main__":
    main()