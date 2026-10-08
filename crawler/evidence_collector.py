def collect_page_state(page, screenshot_path=None):
    state = {
        "url": page.url,
        "title": page.title(),
        "text": page.locator("body").inner_text(),
        "buttons": [
            button.inner_text().strip()
            for button in page.locator("button").all()
            if button.inner_text().strip()
        ],
        "links": [
            {
                "text": link.inner_text().strip(),
                "url": link.get_attribute("href")
            }
            for link in page.locator("a").all()
            if link.get_attribute("href")
        ]
    }

    if screenshot_path:
        page.screenshot(
            path=screenshot_path,
            full_page=True
        )

        state["screenshot"] = screenshot_path

    return state


def create_interaction_evidence(before, after, interaction):
    return {
        "interaction": interaction,
        "before": before,
        "after": after
    }

def compare_page_states(before, after):
    return {
        "url_changed": before["url"] != after["url"],
        "title_changed": before["title"] != after["title"],
        "page_type_changed": before.get("page_type") != after.get("page_type"),
        "text_changed": before["text"] != after["text"]
    }