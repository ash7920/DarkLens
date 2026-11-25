"""Render the three sample screenshots shown on the Inspect page (from the test-bed shops)."""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app/static/samples"
OUT.mkdir(parents=True, exist_ok=True)
subprocess.run([sys.executable, str(ROOT / "testbed/build_testbed.py")], check=True)
srv = subprocess.Popen([sys.executable, "-m", "http.server", "8766", "--directory", str(ROOT / "testbed")],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1)
try:
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1366, "height": 900})
        for name, path in [("darkmart-product", "darkshop/product-trail-runner-shoes.html"),
                           ("darkmart-basket", "darkshop/cart.html"),
                           ("fairmart-product", "fairshop/product-trail-runner-shoes.html")]:
            pg.goto(f"http://localhost:8766/{path}")
            pg.wait_for_timeout(800)
            pg.screenshot(path=str(OUT / f"{name}.png"))
        b.close()
finally:
    srv.terminate()
print("samples written to", OUT)
