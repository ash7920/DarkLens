"""
Generates the DarkLens controlled test-bed: two structurally identical shops.

  darkshop/  – every page carries known, injected dark patterns
  fairshop/  – same pages and copy with the manipulative elements removed

ground_truth.json lists every injected instance (page, category, text), so the
crawler's coverage and the detector's recall/precision can be measured on a
site where the truth is known exactly (cf. TrickyArena, Ersoy et al. 2026).

    python testbed/build_testbed.py
    python -m http.server 8765 --directory testbed     # then crawl http://localhost:8765/darkshop/
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parent

PRODUCTS = [
    ("trail-runner-shoes", "Trail Runner Shoes", 89.00),
    ("wool-winter-jacket", "Wool Winter Jacket", 149.00),
    ("ceramic-coffee-mug", "Ceramic Coffee Mug", 14.50),
    ("noise-cancelling-headphones", "Noise-Cancelling Headphones", 199.00),
    ("leather-backpack", "Leather Backpack", 120.00),
    ("smart-water-bottle", "Smart Water Bottle", 39.90),
]

GT: list[dict] = []


def gt(page: str, category: str, text: str, element: str = "text"):
    GT.append({"page": page, "category": category, "text": text, "element": element})


def layout(title: str, body: str, dark: bool, extra_head: str = "") -> str:
    cookie = ""
    if dark:
        cookie = """
<div class="banner" id="cookie-banner" role="dialog">
  <div style="flex:1">We use cookies to give you the best experience. By continuing you agree to our use of cookies.</div>
  <a href="#" class="muted" id="cookie-settings-link" onclick="document.getElementById('cookie-layer').style.display='flex';return false;">settings</a>
  <button class="btn" style="font-size:20px;padding:16px 48px" onclick="this.closest('.banner').remove()">ACCEPT ALL</button>
</div>
<div class="modal-bg" id="cookie-layer" role="dialog"><div class="modal">
  <h3>Cookie preferences</h3>
  <label><input type="checkbox" checked disabled> Necessary</label><br>
  <label><input type="checkbox" checked> Personalised advertising</label><br>
  <label><input type="checkbox" checked> Share data with partners</label><br><br>
  <button class="btn" onclick="this.closest('.modal-bg').remove()">Save</button>
</div></div>"""
    else:
        cookie = """
<div class="banner" id="cookie-banner" role="dialog">
  <div style="flex:1">We use cookies. Necessary cookies are always on; you can choose the rest.</div>
  <button class="btn secondary" onclick="this.closest('.banner').remove()">Reject all</button>
  <button class="btn secondary" onclick="document.getElementById('cookie-layer').style.display='flex'">Cookie settings</button>
  <button class="btn secondary" onclick="this.closest('.banner').remove()">Accept all</button>
</div>
<div class="modal-bg" id="cookie-layer" role="dialog"><div class="modal">
  <h3>Cookie preferences</h3>
  <label><input type="checkbox" checked disabled> Necessary</label><br>
  <label><input type="checkbox"> Personalised advertising</label><br>
  <label><input type="checkbox"> Share data with partners</label><br><br>
  <button class="btn secondary" onclick="this.closest('.modal-bg').remove()">Save</button>
</div></div>"""
    name = "DarkMart" if dark else "FairMart"
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title} | {name}</title>
<link rel="stylesheet" href="../shop.css">{extra_head}</head><body>
<header><a class="logo" href="index.html">{name}</a><a href="category-sale.html">Sale</a>
<a href="account.html">My account</a><a href="cart.html">Basket</a></header>
<main>{body}</main>{cookie}</body></html>"""


def index(dark: bool) -> str:
    cards = "".join(
        f'<div class="card"><h3>{n}</h3><div class="price">€{p:.2f}</div>'
        f'<a href="product-{s}.html">View product</a></div>' for s, n, p in PRODUCTS)
    hero = "<h1>Welcome to our shop</h1><p>Quality basics, fair prices.</p>"
    if dark:
        hero = ('<h1>Welcome to our shop</h1><div class="timer">FLASH SALE | LIMITED TIME ONLY – ends in '
                '<span class="cd">00:14:59</span></div>')
        gt("index", "urgency", "FLASH SALE | LIMITED TIME ONLY – ends in 00:14:59")
        # cookie banner + consent layer are site-wide: page "*" = every page
        gt("*", "interface_interference", "ACCEPT ALL (large) vs settings (small grey link)", "cookie_banner")
        gt("*", "preselection", "Personalised advertising (pre-ticked)", "cookie_layer_checkbox")
        gt("*", "preselection", "Share data with partners (pre-ticked)", "cookie_layer_checkbox")
    return layout("Home", hero + f'<div class="grid">{cards}</div>', dark,
                  '<script>setInterval(()=>document.querySelectorAll(".cd").forEach(e=>{let[h,m,s]=e.textContent.split(":").map(Number);let t=Math.max(0,h*3600+m*60+s-1);if(t==0)t=899;e.textContent=[t/3600|0,(t%3600)/60|0,t%60].map(x=>String(x).padStart(2,"0")).join(":")}),1000)</script>' if dark else "")


def category(dark: bool) -> str:
    cards = ""
    for i, (s, n, p) in enumerate(PRODUCTS):
        badge = ""
        if dark and i in (0, 3):
            badge = '<div class="stock">Selling fast!</div>'
        cards += f'<div class="card"><h3>{n}</h3>{badge}<div class="price">€{p:.2f}</div><a href="product-{s}.html">View product</a></div>'
    if dark:
        gt("category-sale", "scarcity", "Selling fast!")
    return layout("Sale", f'<h1>Sale</h1><div class="grid">{cards}</div>', dark)


def product(slug: str, name: str, price: float, idx: int, dark: bool) -> str:
    page = f"product-{slug}"
    extras = ""
    popup = ""
    if dark:
        if idx % 2 == 0:
            extras += '<p class="stock">Only 2 left in stock – order soon!</p>'
            gt(page, "scarcity", "Only 2 left in stock – order soon!")
        if idx % 3 == 0:
            extras += '<div class="timer">Deal ends in <span class="cd">01:59:12</span></div>'
            gt(page, "urgency", "Deal ends in 01:59:12")
        extras += f'<p><b>{14 + idx * 3} people</b> are viewing this right now</p>'
        gt(page, "social_proof", f"{14 + idx * 3} people are viewing this right now")
        extras += '<div class="toast" id="toast">Anna from Munich just bought this 4 minutes ago</div>'
        gt(page, "social_proof", "Anna from Munich just bought this 4 minutes ago")
        popup = """
<div class="modal-bg" id="newsletter" role="dialog" style="display:flex"><div class="modal">
 <h2>Get 10% off your first order</h2><p>Join our newsletter for exclusive deals.</p>
 <input placeholder="Email address" style="padding:10px;width:100%"><br><br>
 <button class="btn">Get my 10% off</button><br><br>
 <a href="#" class="muted" onclick="document.getElementById('newsletter').remove();return false;">No thanks, I prefer paying full price</a>
</div></div>"""
        gt(page, "confirmshaming", "No thanks, I prefer paying full price")
        sizes = '<select><option>Standard</option><option selected>Premium bundle (+€25.00)</option></select>'
        gt(page, "preselection", "Premium bundle (+€25.00) pre-selected")
    else:
        extras += '<p>In stock</p>'
        sizes = '<select><option selected>Standard</option><option>Premium bundle (+€25.00)</option></select>'
    body = f"""<div class="card"><h1>{name}</h1><div class="price">€{price:.2f}</div>{extras}
<p>Option: {sizes}</p>
<button class="btn" onclick="localStorage.setItem('cart','{slug}');location.href='cart.html'">Add to basket</button>
<details><summary>Delivery &amp; returns</summary><p>Standard delivery 3–5 working days. 30-day returns.</p></details>
</div>{popup}"""
    return layout(name, body, dark,
                  '<script>setInterval(()=>document.querySelectorAll(".cd").forEach(e=>{let[h,m,s]=e.textContent.split(":").map(Number);let t=Math.max(0,h*3600+m*60+s-1);if(t==0)t=7199;e.textContent=[t/3600|0,(t%3600)/60|0,t%60].map(x=>String(x).padStart(2,"0")).join(":")}),1000)</script>' if dark else "")


def cart(dark: bool) -> str:
    if dark:
        rows = """<tr><td>Your item</td><td>€89.00</td></tr>
<tr><td><label><input type="checkbox" checked> Add 2-year protection plan (+€19.99)</label></td><td>€19.99</td></tr>
<tr><td><label><input type="checkbox" checked> Donate €2 to our tree-planting partner</label></td><td>€2.00</td></tr>"""
        gt("cart", "preselection", "Add 2-year protection plan (+€19.99) pre-ticked", "checkbox")
        gt("cart", "preselection", "Donate €2 to our tree-planting partner pre-ticked", "checkbox")
        note = '<p class="stock">Items in your basket are reserved for 10:00 minutes</p>'
        gt("cart", "urgency", "Items in your basket are reserved for 10:00 minutes")
    else:
        rows = """<tr><td>Your item</td><td>€89.00</td></tr>
<tr><td><label><input type="checkbox"> Add 2-year protection plan (+€19.99)</label></td><td></td></tr>"""
        note = ""
    body = f"""<h1>Your basket</h1>{note}<table>{rows}</table><br>
<a class="btn" href="checkout.html" style="text-decoration:none">Go to checkout</a>"""
    return layout("Basket", body, dark)


def checkout(dark: bool) -> str:
    if dark:
        body = """<h1>Checkout</h1><p><b>Create an account to continue.</b> Guest checkout is not available.</p>
<table><tr><td>Subtotal</td><td>€89.00</td></tr><tr><td>Service &amp; handling fee</td><td>€4.95</td></tr>
<tr><td>Total</td><td>€93.95</td></tr></table>
<label><input type="checkbox" checked> Yes, send me offers and share my details with partners</label>
<p><button class="btn" disabled>Place order</button></p>"""
        gt("checkout", "forced_action", "Create an account to continue. Guest checkout is not available.")
        gt("checkout", "preselection", "Service & handling fee €4.95 (only shown at checkout)")
        gt("checkout", "preselection", "Yes, send me offers and share my details with partners (pre-ticked)", "checkbox")
    else:
        body = """<h1>Checkout</h1><p>Continue as guest or log in.</p>
<table><tr><td>Subtotal</td><td>€89.00</td></tr><tr><td>Delivery</td><td>€0.00</td></tr>
<tr><td>Total</td><td>€89.00</td></tr></table>
<label><input type="checkbox"> Send me offers by email</label>
<p><button class="btn" disabled>Place order</button></p>"""
    return layout("Checkout", body, dark)


def account(dark: bool) -> str:
    if dark:
        body = """<h1>My account</h1><div class="card"><h3>DarkMart Plus membership</h3>
<p>€7.99 / month, renews automatically.</p><a href="subscription-cancel.html" class="muted">manage membership</a></div>"""
    else:
        body = """<h1>My account</h1><div class="card"><h3>FairMart Plus membership</h3>
<p>€7.99 / month, renews automatically.</p><a href="subscription-cancel.html">Cancel membership</a></div>"""
    return layout("Account", body, dark)


def cancel(dark: bool) -> str:
    if dark:
        body = """<h1>Manage membership</h1>
<p>We're sad to see you go! If you cancel you will lose ALL your benefits forever.</p>
<p>To cancel your membership please call our customer service line (Mon–Fri, 9:00–11:00).</p>
<button class="btn" style="font-size:20px">Keep my benefits</button>
<p><a href="#" class="muted">No, I don't care about saving money</a></p>"""
        gt("subscription-cancel", "obstruction", "To cancel your membership please call our customer service line (Mon–Fri, 9:00–11:00).")
        gt("subscription-cancel", "confirmshaming", "No, I don't care about saving money")
        gt("subscription-cancel", "interface_interference", "Keep my benefits (large) vs decline (small grey link)", "button")
    else:
        body = """<h1>Cancel membership</h1><p>Your membership will end at the close of the current billing period.</p>
<button class="btn secondary">Cancel membership</button> <button class="btn secondary">Keep membership</button>"""
    return layout("Membership", body, dark)


def build():
    for dark in (True, False):
        d = ROOT / ("darkshop" if dark else "fairshop")
        d.mkdir(exist_ok=True)
        (d / "index.html").write_text(index(dark), encoding="utf-8")
        (d / "category-sale.html").write_text(category(dark), encoding="utf-8")
        for i, (s, n, p) in enumerate(PRODUCTS):
            (d / f"product-{s}.html").write_text(product(s, n, p, i, dark), encoding="utf-8")
        (d / "cart.html").write_text(cart(dark), encoding="utf-8")
        (d / "checkout.html").write_text(checkout(dark), encoding="utf-8")
        (d / "account.html").write_text(account(dark), encoding="utf-8")
        (d / "subscription-cancel.html").write_text(cancel(dark), encoding="utf-8")
    (ROOT / "ground_truth.json").write_text(json.dumps(GT, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"testbed built: {len(GT)} injected dark-pattern instances in darkshop, 0 in fairshop")


if __name__ == "__main__":
    build()
