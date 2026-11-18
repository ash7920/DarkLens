"""Unit tests — run with:  python -m pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from darklens.crawler.interaction_priority import get_interaction_type  # noqa: E402
from darklens.crawler.page_classifier import classify_page  # noqa: E402
from darklens.crawler.safe_interaction import interaction_tier, is_safe_interaction  # noqa: E402
from darklens.crawler.url_priority import get_priority  # noqa: E402
from darklens.crawler.url_utils import clean_url, same_site  # noqa: E402
from darklens.evaluation.metrics import binary_metrics, fleiss_kappa, multiclass_metrics  # noqa: E402
from darklens.preprocessing.lexicon import rule_label  # noqa: E402
from darklens.preprocessing.segments import choice_asymmetry, page_segments  # noqa: E402


# ---------------------------------------------------------------- crawler
def test_clean_url():
    assert clean_url("https://shop.de/a/", "../b?utm_source=x&id=3#top") == "https://shop.de/b?id=3"
    assert clean_url("https://shop.de", "javascript:void(0)") is None
    assert clean_url("https://shop.de", "mailto:a@b.c") is None
    assert clean_url("https://shop.de", "/img/logo.png") is None


def test_same_site():
    assert same_site("https://www.zalando.de/x", "https://zalando.de")
    assert same_site("https://m.zalando.de/x", "https://www.zalando.de")
    assert not same_site("https://facebook.com/x", "https://zalando.de")


@pytest.mark.parametrize("url,expected", [
    ("https://shop.com/", "homepage"),
    ("https://shop.com/checkout/step1", "checkout"),
    ("https://shop.de/warenkorb", "cart"),
    ("https://shop.fr/panier", "cart"),
    ("https://shop.com/women/bags/", "category"),  # 'bags' must not be read as a cart
    ("https://shop.com/products/red-shoe", "product"),
    ("https://shop.com/account/subscription/cancel", "subscription"),
    ("https://shop.com/privacy-policy", "info"),
    ("https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html", "product"),
    ("https://books.toscrape.com/catalogue/category/books/travel_2/index.html", "category"),
])
def test_classify_page(url, expected):
    assert classify_page(url) == expected


def test_priority_order():
    assert get_priority("https://s.com/checkout") > get_priority("https://s.com/products/x") > \
           get_priority("https://s.com/about-us")
    assert get_priority("https://s.com/x", "View basket") > get_priority("https://s.com/x", "")


def test_safe_interaction_policy():
    assert interaction_tier("Place order") == "blocked"
    assert interaction_tier("Jetzt kaufen") == "blocked"
    assert interaction_tier("Sign up") == "blocked"
    assert interaction_tier("Add to cart") == "conditional"
    assert not is_safe_interaction("Add to cart", allow_add_to_cart=False)
    assert is_safe_interaction("Add to cart", allow_add_to_cart=True)
    assert is_safe_interaction("Show more details")
    assert not is_safe_interaction("Account", "https://s.com/logout")


def test_interaction_types():
    assert get_interaction_type("Manage cookies") == "cookie_settings"
    assert get_interaction_type("Alle ablehnen") == "consent_reject"
    assert get_interaction_type("No thanks, I prefer paying full price") == "close_popup"
    assert get_interaction_type("In den Warenkorb") == "add_to_cart"


# ------------------------------------------------------------ preprocessing
@pytest.mark.parametrize("text,label", [
    ("Only 2 left in stock!", "scarcity"),
    ("Offer ends in 00:14:59", "urgency"),
    ("Sarah from Berlin just bought this 3 minutes ago", "social_proof"),
    ("No thanks, I prefer paying full price", "confirmshaming"),
    ("To cancel your membership please call our support line", "obstruction"),
    ("Nur noch 3 Stück verfügbar", "scarcity"),
    ("Free delivery on orders over €50", "not_dark"),
    ("Write a review", "not_dark"),
])
def test_rules(text, label):
    assert rule_label(text) == label


def test_segments_and_asymmetry():
    rec = {"state_id": "s1", "site": "x", "url": "https://x/cart", "page_type": "cart", "label": "initial",
           "elements": [
               {"dl_id": 0, "kind": "checkbox", "text": "Add protection plan (+€19.99)", "checked": True,
                "bbox": [0, 0, 10, 10], "visible": True},
               {"dl_id": 1, "kind": "text", "text": "Add protection plan (+€19.99)", "bbox": [0, 0, 10, 10]},
               {"dl_id": 2, "kind": "button", "text": "ACCEPT ALL", "bbox": [0, 500, 220, 55], "in_overlay": True,
                "font_size": 20, "visible": True},
               {"dl_id": 3, "kind": "link", "text": "settings", "bbox": [300, 515, 38, 12], "in_overlay": True,
                "font_size": 11, "visible": True},
               {"dl_id": 4, "kind": "text", "text": "€19.99", "bbox": [0, 0, 5, 5]},
           ]}
    segs = page_segments(rec)
    kinds = [s["kind"] for s in segs]
    assert kinds.count("checkbox") == 1 and "text" not in kinds  # label text folded into control; price dropped
    assert any(s["kind"] == "choice_pair" for s in segs)
    assert choice_asymmetry(rec["elements"])[0]["ratio"] > 3


# ------------------------------------------------------------------ metrics
def test_metrics():
    m = binary_metrics([1, 1, 0, 0], [1, 0, 0, 1], n_boot=10)
    assert m["precision"] == 0.5 and m["recall"] == 0.5
    mc = multiclass_metrics(["urgency", "not_dark", "scarcity"], ["urgency", "not_dark", "urgency"])
    assert mc["per_class"]["urgency"]["recall"] == 1.0
    assert fleiss_kappa([["a", "a"], ["b", "b"], ["a", "a"]]) == pytest.approx(1.0)


# --------------------------------------------- LLM path with a mocked model
class FakeLLM:
    """Stands in for the provider call; returns what a well-behaved model would."""

    def __init__(self):
        self.calls = []

    def __call__(self, system, user, images, max_tokens):
        self.calls.append(user)
        if user.startswith("VERIFICATION STAGE"):
            # reject candidate 2 (a false positive), keep the rest
            ids = [int(l.split(".")[0]) for l in user.split("CANDIDATES")[1].splitlines() if l[:1].isdigit()]
            return json.dumps({"verdicts": [{"cid": i, "keep": i != 2, "label": "scarcity" if i == 1 else "urgency",
                                             "confidence": 0.9, "reason": "checked"} for i in ids]}), 10, 10
        if "OCR LINES" in user:
            return json.dumps({"page_kind": "product", "detections": [
                {"label": "Scarcity", "line_ids": ["L1"], "evidence": "Only 2 left", "confidence": 0.9,
                 "explanation": "stock pressure"},
                {"label": "preselection", "line_ids": [], "box_2d": [100, 100, 200, 300],
                 "evidence": "pre-ticked insurance box", "confidence": 0.8, "explanation": "visual"}]}), 10, 10
        return "```json\n" + json.dumps({"items": [
            {"id": 1, "label": "scarcity", "confidence": 0.95, "evidence": "Only 2 left", "explanation": "x"},
            {"id": 2, "label": "urgency", "confidence": 0.6, "evidence": "Shop now", "explanation": "x"},
            {"id": 3, "label": "not_dark", "confidence": 0.9, "evidence": "", "explanation": "x"}]}) + "\n```", 10, 10


@pytest.fixture
def llm_detector(monkeypatch, tmp_path):
    monkeypatch.setenv("DARKLENS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    from darklens.detection import llm_client
    fake = FakeLLM()
    monkeypatch.setattr(llm_client.LLMClient, "_call_gemini", lambda self, *a: fake(*a))
    from darklens.detection.detector import DarkPatternDetector
    det = DarkPatternDetector(engine="llm", model_dir=ROOT / "models")
    det.llm.cache_dir = tmp_path
    return det, fake


def test_llm_segments_multistage(llm_detector):
    det, fake = llm_detector
    items = [{"id": 1, "text": "Only 2 left"}, {"id": 2, "text": "Shop now"}, {"id": 3, "text": "Free returns"}]
    res = det.classify_segments(items, {"page type": "product"})
    assert [r["label"] for r in res] == ["scarcity", "not_dark", "not_dark"]  # verify stage removed id 2
    assert res[1]["stage1_label"] == "urgency"
    assert len(fake.calls) == 2  # infer + verify


def test_llm_single_pass(llm_detector):
    det, fake = llm_detector
    det.mode = "single"
    res = det.classify_segments([{"id": 1, "text": "Only 2 left"}, {"id": 2, "text": "Shop now"},
                                 {"id": 3, "text": "Free returns"}])
    assert [r["label"] for r in res] == ["scarcity", "urgency", "not_dark"]
    assert len(fake.calls) == 1


def test_llm_screenshot(llm_detector):
    from PIL import Image, ImageDraw
    import io
    det, fake = llm_detector
    det.mode = "single"
    img = Image.new("RGB", (800, 500), "white")
    ImageDraw.Draw(img).text((40, 40), "Only 2 left in stock", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    res = det.analyze_screenshot(buf.getvalue())
    labels = sorted(d["label"] for d in res["detections"])
    assert labels == ["preselection", "scarcity"]
    vis = next(d for d in res["detections"] if d["label"] == "preselection")
    assert vis["box"] == [80, 50, 160, 50]  # [ymin,xmin,ymax,xmax] in 0-1000 mapped to pixel [x,y,w,h]


def test_locate_prefers_evidence_and_contiguous_lines():
    from PIL import Image
    from darklens.detection.detector import DarkPatternDetector
    lines = [{"id": 1, "text": "EUR 89.00", "bbox": [10, 10, 80, 20]},
             {"id": 2, "text": "Only 2 left in stock - order soon!", "bbox": [10, 40, 240, 15]},
             {"id": 3, "text": "No thanks, I prefer paying full price", "bbox": [400, 600, 170, 12]}]
    by_id = {l["id"]: l for l in lines}
    tile = Image.new("RGB", (1000, 800))
    loc = DarkPatternDetector._locate
    # evidence quote wins over the cited ids (which would include the price line)
    assert loc({"evidence": "Only 2 left in stock"}, [1, 2], lines, by_id, tile, 0) == [10, 40, 240, 15]
    # no matching quote: cited ids, but a far-away line is not merged in
    assert loc({"evidence": "zzz"}, [2, 3], lines, by_id, tile, 0) == [10, 40, 240, 15]
    # model box in Gemini order [ymin, xmin, ymax, xmax]
    assert loc({"evidence": "", "box_2d": [500, 100, 600, 400]}, [], lines, by_id, tile, 0) == [100, 400, 300, 80]


# ------------------------------------------------------------ crawl coverage
def test_block_detection_and_site_status(tmp_path):
    from darklens.crawler.coverage import block_reason, coverage, site_status
    assert block_reason("Just a moment...").startswith("bot protection")
    assert block_reason("Access Denied").startswith("bot protection")
    assert block_reason("FNAC DARTY - Maintenance").startswith("unavailable")
    assert block_reason("Zalando | Mode online") is None
    assert site_status({"pages": 1}, {"title": "Let's confirm you are human", "text": ""})[0] == "blocked"
    assert site_status({"pages": 14}, {"title": "ABOUT YOU", "text": "x" * 5000})[0] == "crawled"
    assert site_status({"pages": 0, "robots_blocked": 1}, None)[0] == "robots"
    assert site_status({"pages": 0, "errors": ["timeout"]}, None)[0] == "unreachable"
    assert site_status({"pages": 1}, {"title": "eobuwie.pl", "text": "x" * 5000})[0] == "empty"
    # coverage over a fake crawl directory
    for name, pages, title in [("ok_shop", 9, "Shop"), ("cf_shop", 1, "Just a moment...")]:
        d = tmp_path / name
        d.mkdir()
        (d / "summary.json").write_text(json.dumps({"start_url": f"https://{name}/", "pages": pages}))
        (d / "pages.jsonl").write_text(json.dumps({"title": title, "text": "", "site": name}) + "\n")
    cov = coverage(tmp_path)
    assert (cov["attempted"], cov["crawled"], cov["blocked"]) == (2, 1, 1)
