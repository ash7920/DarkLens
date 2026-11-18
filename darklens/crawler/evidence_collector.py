"""
Evidence collection (V4).

For every page *state* (initial load, after each safe interaction) we store:
  - url, title, detected language, timestamp
  - full rendered HTML (file)            -> "Relevant HTML" input in the diagram
  - full visible text                    -> "Clean Text"
  - full-page screenshot (file)          -> "Screenshots + Metadata"
  - structured UI elements with bounding
    boxes, font size, colours, checkbox
    state, overlay/dialog membership     -> "UI Elements"
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

try:
    from langdetect import DetectorFactory, detect

    DetectorFactory.seed = 0
except Exception:  # langdetect optional
    detect = None

# Runs inside the page.  Returns visible, text-bearing leaf-ish elements plus
# every form control, with geometry and the style cues that matter for
# interface interference (size, colour, contrast, weight).
EXTRACT_UI_JS = r"""
(maxElements) => {
  const out = [];
  const seen = new Set();
  const vw = window.innerWidth, vh = window.innerHeight;

  function visible(el) {
    const s = getComputedStyle(el);
    if (s.visibility === 'hidden' || s.display === 'none' || parseFloat(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  }
  function inOverlay(el) {
    let n = el;
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      const role = (n.getAttribute && n.getAttribute('role')) || '';
      if (role === 'dialog' || role === 'alertdialog' || n.tagName === 'DIALOG') return true;
      if ((s.position === 'fixed' || s.position === 'sticky') && parseInt(s.zIndex || '0') >= 10) return true;
      n = n.parentElement;
    }
    return false;
  }
  function labelFor(el) {
    if (el.id) {
      const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (l) return l.innerText.trim();
    }
    const p = el.closest('label');
    if (p) return p.innerText.trim();
    const sib = el.parentElement ? el.parentElement.innerText.trim() : '';
    return sib.slice(0, 200);
  }
  function rec(el, kind, text) {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const key = kind + '|' + text + '|' + Math.round(r.left) + '|' + Math.round(r.top + window.scrollY);
    if (seen.has(key)) return;
    seen.add(key);
    const dlId = out.length;
    try { el.setAttribute('data-dl-id', String(dlId)); } catch (e) {}
    out.push({
      dl_id: dlId,
      kind,
      tag: el.tagName.toLowerCase(),
      text: text.slice(0, 500),
      bbox: [Math.round(r.left + window.scrollX), Math.round(r.top + window.scrollY), Math.round(r.width), Math.round(r.height)],
      in_viewport: r.top < vh && r.bottom > 0 && r.left < vw && r.right > 0,
      font_size: parseFloat(s.fontSize),
      font_weight: s.fontWeight,
      color: s.color,
      background: s.backgroundColor,
      in_overlay: inOverlay(el),
      visible: visible(el),
      checked: (el.type === 'checkbox' || el.type === 'radio') ? !!el.checked : null,
      input_type: el.type || null,
      href: el.getAttribute ? (el.getAttribute('href') || null) : null,
      aria_expanded: el.getAttribute ? el.getAttribute('aria-expanded') : null,
    });
  }

  // 1) form controls (checkbox/radio state is key for pre-selection)
  document.querySelectorAll('input[type=checkbox], input[type=radio], select').forEach(el => {
    if (out.length >= maxElements) return;
    const r = el.getBoundingClientRect();
    if (r.width < 1 && r.height < 1 && !el.closest('label')) return;
    let text = labelFor(el);
    if (el.tagName === 'SELECT') text = (el.options[el.selectedIndex] || {}).text || '';
    rec(el, el.tagName === 'SELECT' ? 'select' : el.type, text || '(no label)');
  });

  // 2) buttons and links
  document.querySelectorAll('button, a, [role=button], input[type=submit], input[type=button], summary').forEach(el => {
    if (out.length >= maxElements || !visible(el)) return;
    const text = (el.innerText || el.value || el.getAttribute('aria-label') || '').trim().replace(/\s+/g, ' ');
    if (!text) return;
    rec(el, el.tagName === 'A' ? 'link' : 'button', text);
  });

  // 3) text blocks: elements whose own text (not children's) is non-empty
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
  let node;
  while ((node = walker.nextNode()) && out.length < maxElements) {
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'SVG', 'BUTTON', 'A', 'OPTION'].includes(node.tagName)) continue;
    let own = '';
    node.childNodes.forEach(c => { if (c.nodeType === 3) own += c.textContent; });
    own = own.trim().replace(/\s+/g, ' ');
    if (own.length < 2 || !visible(node)) continue;
    const text = node.innerText.trim().replace(/\s+/g, ' ');
    if (!text || text.length > 400) continue;
    rec(node, 'text', text);
  }
  return out;
}
"""


def detect_language(text: str) -> str:
    if not detect or not text or len(text) < 30:
        return "unknown"
    try:
        return detect(text[:3000])
    except Exception:
        return "unknown"


def state_id(url: str, label: str) -> str:
    return hashlib.sha1(f"{url}|{label}|{time.time_ns()}".encode()).hexdigest()[:12]


def collect_page_state(page, out_dir: Path | str | None = None, label: str = "initial",
                       max_elements: int = 1500, full_page: bool = True) -> dict:
    """Capture one page state.  If out_dir is given, HTML + screenshot are written there."""
    text = page.locator("body").inner_text(timeout=10000) if page.locator("body").count() else ""
    try:
        elements = page.evaluate(EXTRACT_UI_JS, max_elements)
    except Exception as exc:  # pages that block evaluate, detached frames, etc.
        elements = []
        print("  ! UI extraction failed:", exc)

    state = {
        "state_id": state_id(page.url, label),
        "label": label,
        "url": page.url,
        "title": page.title(),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "language": detect_language(text),
        "text": text,
        "buttons": [e["text"] for e in elements if e["kind"] == "button"],
        "links": [{"text": e["text"], "url": e["href"]} for e in elements if e["kind"] == "link"],
        "elements": elements,
        "viewport": page.viewport_size,
    }

    if out_dir is not None:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        html_path = out / f"{state['state_id']}.html"
        shot_path = out / f"{state['state_id']}.png"
        html_path.write_text(page.content(), encoding="utf-8")
        try:
            page.screenshot(path=str(shot_path), full_page=full_page, timeout=20000)
        except Exception:
            page.screenshot(path=str(shot_path), full_page=False)
        state["html_path"] = str(html_path)
        state["screenshot"] = str(shot_path)
    return state


def compare_page_states(before: dict, after: dict) -> dict:
    """What changed after an interaction — the 'newly revealed' text is what
    usually carries the dark pattern (popup copy, cookie layer options...)."""
    before_lines = {l.strip() for l in before["text"].splitlines() if l.strip()}
    new_lines = [l.strip() for l in after["text"].splitlines() if l.strip() and l.strip() not in before_lines]
    before_checks = {(e["text"], e["checked"]) for e in before["elements"] if e["checked"] is not None}
    new_checks = [e for e in after["elements"] if e["checked"] is not None and (e["text"], e["checked"]) not in before_checks]
    return {
        "url_changed": before["url"] != after["url"],
        "title_changed": before["title"] != after["title"],
        "page_type_changed": before.get("page_type") != after.get("page_type"),
        "text_changed": before["text"] != after["text"],
        "new_text": new_lines[:200],
        "new_form_controls": new_checks[:50],
    }


def create_interaction_evidence(before: dict, after: dict, interaction: dict) -> dict:
    return {
        "interaction": interaction,
        "before_state": before["state_id"],
        "after_state": after["state_id"],
        "changes": compare_page_states(before, after),
    }


def slim(state: dict) -> dict:
    """State without the bulky fields, for logs."""
    return {k: v for k, v in state.items() if k not in ("text", "elements", "links", "buttons")}


def append_jsonl(path: Path | str, record: dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
