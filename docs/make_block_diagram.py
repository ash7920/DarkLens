"""
Render the DarkLens block diagram (docs/block_diagram.png + paper/generated/fig_architecture.png).
Same layout and style as the original project diagram, updated to the built system.

    python docs/make_block_diagram.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]

# 24x24 stroke icons
I = {
    "db": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "web": '<rect x="2" y="3" width="20" height="16" rx="2"/><path d="M2 7h20"/><circle cx="12" cy="13.5" r="4"/><path d="M8 13.5h8M12 9.5c1.5 1.2 1.5 6.8 0 8M12 9.5c-1.5 1.2-1.5 6.8 0 8"/>',
    "crawl": '<rect x="2" y="3" width="17" height="14" rx="2"/><path d="M2 7h17"/><circle cx="17" cy="17" r="3.2"/><path d="M17 12.3v1.5M17 20.2v1.5M12.3 17h1.5M20.2 17h1.5M13.7 13.7l1 1M19.3 19.3l1 1M13.7 20.3l1-1M19.3 14.7l1-1"/>',
    "code": '<path d="M8 6l-6 6 6 6M16 6l6 6-6 6M14 4l-4 16"/>',
    "doc": '<path d="M6 2h9l5 5v15H6z"/><path d="M15 2v5h5M9 12h8M9 16h8"/>',
    "check": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M6 12l2 2 4-4M14 9h4M14 13h4M6 17h12"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M3 18l6-5 4 3 3-2 5 4"/>',
    "broom": '<path d="M19 3l-7 9"/><path d="M12 12c-3-1-6 1-7 4l-2 5c3 0 7-1 9-3 2-2 2-4 0-6z"/><path d="M7 16l2 2"/>',
    "gear": '<circle cx="12" cy="12" r="3.2"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/><circle cx="12" cy="12" r="7"/>',
    "brain": '<circle cx="6" cy="7" r="2"/><circle cx="6" cy="17" r="2"/><circle cx="18" cy="12" r="2"/><circle cx="12" cy="4" r="1.6"/><circle cx="12" cy="20" r="1.6"/><circle cx="12" cy="12" r="1.8"/><path d="M8 7l2.3 4M8 17l2.3-4M13.8 12H16M7.5 5.8L10.6 4.6M7.5 18.2l3.1 1.2M13.4 5.2l3.4 5.4M13.4 18.8l3.4-5.4"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L21 21"/>',
    "tag": '<path d="M3 3h8l10 10-8 8L3 11z"/><circle cx="7.5" cy="7.5" r="1.5"/>',
    "evidence": '<path d="M5 3h10l4 4v14H5z"/><path d="M8 10h8M8 14h8M8 18h5"/>',
    "shield": '<path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
    "target": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
    "recall": '<path d="M20 12a8 8 0 1 1-2.4-5.7"/><path d="M20 3v5h-5"/><circle cx="12" cy="12" r="2"/>',
    "bars": '<path d="M5 20V12M10 20V6M15 20v-9M20 20V9M3 21h19"/>',
    "kappa": '<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M3 20c0-3 2.5-5 5-5s5 2 5 5M11 20c0-3 2.5-5 5-5s5 2 5 5"/>',
    "warn": '<path d="M12 3L2 21h20z"/><path d="M12 10v5M12 18v.5"/>',
    "pie": '<path d="M12 3a9 9 0 1 0 9 9h-9z"/><path d="M15 2.5A9 9 0 0 1 21.5 9H15z"/>',
    "list": '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 8h8M8 12h8M8 16h5"/>',
    "app": '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/><rect x="6" y="7.5" width="6" height="5" rx=".5"/><path d="M14 8.5h4M14 11.5h3"/>',
    "report": '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M8 17v-4M12 17V8M16 17v-6"/>',
    "funnel": '<path d="M3 4h18l-7 8v7l-4 2v-9z"/>',
}


def icon(name, size=22, color="#2b6f4a"):
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{I[name]}</svg>')


def badge(name, bg, size=64):
    return (f'<div class="badge" style="width:{size}px;height:{size}px;background:{bg}">'
            f'{icon(name, int(size * 0.5), "#fff")}</div>')


def tile(name, label, cls="row"):
    return f'<div class="tile {cls}">{icon(name)}<span>{label}</span></div>'


def box(x, y, w, h, inner, cls="panel"):
    return f'<div class="{cls}" style="left:{x}px;top:{y}px;width:{w}px;height:{h}px">{inner}</div>'


import json  # noqa: E402

_cov = ROOT / "results/crawl_coverage.json"
if _cov.exists():
    _c = json.loads(_cov.read_text())
    SITES_TEXT = f"{_c['attempted']} attempted<br>{_c['crawled']} crawled &amp; analysed"
else:
    SITES_TEXT = "EU retailers<br>crawlable ones analysed"

parts = []
# 1. data sources
parts.append(box(10, 92, 160, 190, f'{badge("db", "#7b4fc9")}<h3>Existing Dark<br>Pattern Datasets</h3>'
                 '<p>EC, Mathur, AidUI<br>+ DarkMart test-bed</p>', "panel center"))
parts.append(box(10, 318, 160, 176, f'{badge("web", "#2f80d1")}<h3>EU E-commerce<br>Websites</h3>'
                 '<p>' + SITES_TEXT + '</p>', "panel center"))
# 2. crawler
parts.append(box(188, 226, 132, 236, f'{badge("crawl", "#1f8a7a")}<h3>Playwright<br>Web Crawler</h3>'
                 '<p>Priority navigation<br>Safe interaction<br>Rate-limited</p>', "panel center"))
# web data collection
parts.append(box(338, 180, 198, 284, '<h2>Web Data Collection</h2><div class="grid2">'
                 + tile("code", "HTML", "sq") + tile("doc", "Visible Text", "sq")
                 + tile("check", "UI Elements", "sq") + tile("image", "Screenshots +<br>Metadata", "sq")
                 + "</div>"))
# 3. preprocessing
parts.append(box(574, 156, 186, 336, '<h2>Data Preprocessing</h2><div class="stack">'
                 + tile("broom", "HTML/Text<br>Cleaning", "big") + tile("gear", "UI Extraction<br>(with state)", "big")
                 + tile("db", "Data<br>Standardization", "big") + "</div>"))
parts.append(box(776, 258, 86, 122, f'{icon("db", 40, "#2f80d1")}<p class="small">Unified Dataset<br>+ Ground Truth</p>',
                 "panel center thin"))
# 4. LLM detection
det = ('<h2>LLM-Based Dark Pattern<br>Detection</h2>'
       '<div class="col in"><h4>Inputs</h4>' + tile("doc", "Clean Text") + tile("check", "UI Elements")
       + tile("image", "Screen-<br>shots") + tile("code", "Relevant<br>HTML") + '</div>'
       f'<div class="model">{badge("brain", "#2e8b57", 60)}<b>LLM</b><span>Infer, then<br>Verify</span>'
       f'<div class="pre">{icon("funnel", 16)}<span>Pre-filter</span></div></div>'
       '<div class="col out"><h4>Outputs</h4>' + tile("search", "Pattern<br>Detection") + tile("tag", "Category")
       + tile("evidence", "Evidence") + tile("shield", "Confidence") + '</div>'
       '<div class="taxo"><b>Dark Pattern Taxonomy</b>Urgency | Scarcity | Confirmshaming |<br>'
       'Pre-ticked Add-ons | Difficult Cancellation<br>'
       '<span>+ Social Proof | Interface Interference | Forced Action</span></div>')
parts.append(box(876, 124, 324, 412, det))
# 5. evaluation
ev = (f'{badge("report", "#2e8b57", 62)}<h3>Evaluation Module</h3>'
      '<div class="pair"><div class="tile chip">LLM<br>Predictions</div><div class="tile chip">Human<br>Ground Truth</div></div>'
      '<div class="merge"></div><div class="stack tight">'
      + tile("target", "Precision") + tile("recall", "Recall") + tile("bars", "F1-score")
      + tile("kappa", "Cohen's κ") + tile("warn", "Error Analysis") + '</div>')
parts.append(box(1216, 124, 192, 412, ev, "panel center"))
# 6. final
fin = (f'{badge("report", "#2e8b57", 62)}<h3>Final Findings &amp;<br>Analysis</h3><div class="stack tight">'
       + tile("bars", "Pattern<br>Frequency") + tile("pie", "Category-wise<br>Performance")
       + tile("list", "Detected<br>Examples") + tile("app", "DarkLens<br>Web App") + '</div>')
parts.append(box(1424, 124, 168, 412, fin, "panel center"))

chev = "".join(f'<div class="chev" style="left:{x}px;width:{w}px">{t}</div>' for x, w, t in [
    (10, 238, "1. Data Sources"), (242, 342, "2. Web Crawling &amp; Collection"), (578, 290, "3. Data Preprocessing"),
    (862, 290, "4. LLM Detection"), (1146, 228, "5. Evaluation"), (1368, 228, "6. Final Analysis")])

arrows = '''<svg class="arrows" width="1600" height="560">
<defs><marker id="a" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0L8 4L0 8z" fill="#1d3b2c"/></marker></defs>
<g stroke="#1d3b2c" stroke-width="1.8" fill="none" marker-end="url(#a)">
<path d="M170 156H552V246H572"/>
<path d="M170 356H186"/><path d="M320 330H336"/><path d="M536 330H572"/><path d="M760 318H774"/>
<path d="M862 318H874"/><path d="M1200 330H1214"/><path d="M1408 330H1422"/>
</g></svg>'''

html = f'''<!doctype html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:#fff;font-family:"Helvetica Neue",Arial,sans-serif;color:#1d2b24}}
.canvas{{position:relative;width:1600px;height:640px}}
.panel{{position:absolute;box-sizing:border-box;background:#eaf5ee;border:2px solid #a9d3b8;border-radius:10px;padding:10px}}
.center{{display:flex;flex-direction:column;align-items:center;text-align:center;justify-content:center;gap:6px}}
.thin{{padding:6px}}
.badge{{border-radius:50%;display:grid;place-items:center;flex:none}}
h2{{font-size:16px;margin:2px 0 10px;text-align:center;font-weight:700}}
h3{{font-size:15px;margin:0;font-weight:700;line-height:1.2}}
h4{{font-size:12px;margin:0 0 6px;text-align:center}}
p{{font-size:12px;margin:0;color:#3b4a42;line-height:1.5}}
p.small{{font-size:10.5px;line-height:1.3;color:#1d2b24}}
.tile{{background:#fff;border:1.5px solid #bfdfcb;border-radius:7px;display:flex;align-items:center;gap:8px;font-size:11.5px;box-sizing:border-box}}
.tile.row{{padding:6px 8px;min-height:44px}}
.tile.sq{{flex-direction:column;justify-content:center;text-align:center;height:100px;font-size:12px;gap:10px}}
.tile.sq svg{{width:34px;height:34px}}
.tile.big{{padding:8px 12px;height:82px;font-size:12.5px;gap:14px}}
.tile.big svg{{width:30px;height:30px}}
.tile.chip{{justify-content:center;text-align:center;padding:6px 4px;font-size:11px;width:84px;height:44px}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.stack{{display:flex;flex-direction:column;gap:12px}}
.stack.tight{{gap:6px;width:100%}}
.stack.tight .tile{{min-height:44px;padding:5px 10px}}
.col{{position:absolute;top:66px;width:100px;background:#f3faf6;border:1.5px solid #bfdfcb;border-radius:8px;padding:6px;box-sizing:border-box;display:flex;flex-direction:column;gap:6px}}
.col.in{{left:8px}} .col.out{{right:8px}}
.col .tile{{font-size:10.5px;gap:6px;padding:5px 6px;min-height:40px}}
.col .tile svg{{width:18px;height:18px;flex:none}}
.model{{position:absolute;left:112px;width:96px;top:118px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:4px}}
.model b{{font-size:13px}} .model span{{font-size:11px;color:#3b4a42;line-height:1.25}}
.pre{{margin-top:6px;display:flex;gap:4px;align-items:center;background:#fff;border:1.5px solid #bfdfcb;border-radius:6px;padding:3px 6px}}
.pre span{{font-size:10px;color:#1d2b24}}
.taxo{{position:absolute;left:8px;right:8px;bottom:8px;background:#fff;border:1.5px solid #bfdfcb;border-radius:8px;padding:7px;text-align:center;font-size:11.5px;line-height:1.55}}
.taxo b{{display:block;font-size:12px}} .taxo span{{font-size:10.5px;color:#4b5d54}}
.pair{{display:flex;gap:8px;margin-top:4px}}
.merge{{width:96px;height:10px;border:1.8px solid #1d3b2c;border-top:none;margin:-2px 0 12px;position:relative}}.merge::after{{content:'';position:absolute;left:50%;top:9px;transform:translateX(-50%);border:6px solid transparent;border-top:8px solid #1d3b2c}}.merge::before{{content:'';position:absolute;left:50%;top:8px;width:1.8px;height:4px;background:#1d3b2c}}
.chev{{position:absolute;top:572px;height:48px;background:#bfe3cc;display:grid;place-items:center;font-weight:700;font-size:14.5px;
  clip-path:polygon(0 0,93% 0,100% 50%,93% 100%,0 100%,4% 50%)}}
.arrows{{position:absolute;left:0;top:0;pointer-events:none}}
</style></head><body><div class="canvas">{arrows}{"".join(parts)}{chev}</div></body></html>'''

out_html = ROOT / "docs/block_diagram.html"
out_html.write_text(html, encoding="utf-8")
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1600, "height": 640}, device_scale_factor=2)
    pg.goto(out_html.as_uri())
    pg.wait_for_timeout(300)
    pg.locator(".canvas").screenshot(path=str(ROOT / "docs/block_diagram.png"))
    # vector PDF for the paper (IEEE prefers vector graphics with embedded fonts)
    pg.pdf(path=str(ROOT / "paper/generated/fig_architecture.pdf"), width="1600px", height="640px",
           print_background=True, page_ranges="1")
    b.close()
(ROOT / "paper/generated/fig_architecture.png").write_bytes((ROOT / "docs/block_diagram.png").read_bytes())
print("wrote docs/block_diagram.png and paper/generated/fig_architecture.png")
