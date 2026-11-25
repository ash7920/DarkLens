/* DarkLens front-end — no build step, no framework. */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let TAXO = [];
let current = null;

const SAMPLES = [
  { label: "Sample: product page", url: "samples/darkmart-product.png" },
  { label: "Sample: basket", url: "samples/darkmart-basket.png" },
  { label: "Sample: fair shop", url: "samples/fairmart-product.png" },
];

function toast(msg, ms = 4200) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast._t); toast._t = setTimeout(() => (t.hidden = true), ms);
}
function esc(s) { return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function pct(x) { return x == null ? "–" : `${Math.round(x * 100)}%`; }
function f3(x) { return x == null || isNaN(x) ? "–" : Number(x).toFixed(3); }
function f2(x) { return x == null || isNaN(x) ? "–" : Number(x).toFixed(2); }
function catColor(key) { return (TAXO.find(c => c.key === key) || {}).color || "#888"; }
function catName(key) { return key === "not_dark" ? "Not a dark pattern" : (TAXO.find(c => c.key === key) || {}).name || key; }

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

/* ------------------------------------------------------------ routing */
function route() {
  const v = (location.hash || "#inspect").slice(1);
  $$(".view").forEach(el => (el.hidden = el.id !== `view-${v}`));
  $$(".tabs a").forEach(a => a.setAttribute("aria-selected", a.dataset.view === v));
  if (v === "results") loadResults();
  if (v === "taxonomy") renderTaxonomy();
}
window.addEventListener("hashchange", route);

/* ------------------------------------------------------------ status */
async function loadStatus() {
  const el = $("#engineStatus");
  try {
    const s = await api("/api/status");
    const d = s.detector || {};
    if (d.engine === "llm") { el.className = "engine llm"; el.textContent = `Language model: ${d.provider} ${d.model}`; }
    else { el.className = "engine offline"; el.textContent = "Offline engine (no API key set)"; }
    if (d.engine !== "llm") $("#engine").value = "offline";
  } catch (e) { el.textContent = "Server not reachable"; }
}

/* ------------------------------------------------------------ inspect */
function showBusy(text) {
  $("#railEmpty").hidden = true; $("#report").hidden = true; $("#railBusy").hidden = false;
  $("#busyText").textContent = text;
}
function showEmpty() {
  $("#railEmpty").hidden = false; $("#report").hidden = true; $("#railBusy").hidden = true;
  $("#stage").hidden = true; $("#drop").hidden = false; $("#resetBtn").hidden = true;
}

async function analyzeFile(file) {
  if (!file) return;
  if (!/image\/(png|jpe?g|webp)/.test(file.type)) { toast("That file isn't a PNG, JPEG or WebP image."); return; }
  previewImage(URL.createObjectURL(file));
  showBusy(`Reading the screenshot with the ${$("#engine").selectedOptions[0].text.toLowerCase()} engine…`);
  const fd = new FormData();
  fd.append("file", file); fd.append("engine", $("#engine").value); fd.append("mode", $("#mode").value);
  try { render(await api("/api/analyze", { method: "POST", body: fd })); }
  catch (e) { showEmpty(); toast(e.message, 7000); }
}

async function analyzeUrl(url) {
  showBusy("Opening the page in a browser and reading it…");
  $("#drop").hidden = true;
  try {
    const res = await api("/api/analyze-url", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, engine: $("#engine").value, mode: $("#mode").value }) });
    previewImage(res.image_url); render(res);
  } catch (e) { showEmpty(); toast(e.message, 7000); }
}

function previewImage(src) {
  $("#drop").hidden = true; $("#stage").hidden = false; $("#resetBtn").hidden = false;
  $("#shot").src = src; $("#boxes").innerHTML = "";
}

function render(res) {
  current = res;
  $("#railBusy").hidden = true; $("#railEmpty").hidden = true; $("#report").hidden = false;
  const dets = res.detections || [];
  $("#verdictKicker").textContent = res.page ? `${res.page.title || res.page.url} (${res.page.page_type} page)` : "Verdict";
  const v = $("#verdict");
  v.textContent = res.is_dark ? `${dets.length} dark pattern${dets.length > 1 ? "s" : ""} found` : "No dark patterns found";
  v.className = `verdict ${res.is_dark ? "dark" : "fair"}`;
  $("#cats").innerHTML = (res.categories || []).map(c =>
    `<span class="cat" style="--c:${c.color}">${esc(c.name)}${c.count > 1 ? ` ×${c.count}` : ""}</span>`).join("");
  $("#findings").innerHTML = dets.length ? dets.map((d, i) => findingHtml(d, i + 1)).join("")
    : `<li class="finding" style="--c:var(--fair)"><p>Nothing on this screen matched a dark-pattern definition with enough confidence.
        Patterns that only appear after clicking (pop-ups, checkout steps) need a screenshot of that step.</p></li>`;
  const low = res.low_confidence || [];
  $("#lowConf").hidden = !low.length;
  $("#lowList").innerHTML = low.map((d, i) => findingHtml(d, `${i + 1}`)).join("");
  $("#ocrText").textContent = (res.ocr_lines || []).map(l => l.text).join("\n") || "No text recognised.";
  const e = res.engine || {};
  $("#engineUsed").textContent = e.engine === "llm" ? `${e.model}, ${e.mode === "multistage" ? "detect + verify" : "single pass"}, ${res.elapsed_s}s`
    : `Offline rules + classifier, ${res.elapsed_s}s`;
  const img = $("#shot");
  const draw = () => drawBoxes(dets, res.image_size);
  if (img.complete && img.naturalWidth) draw(); else img.onload = draw;
  $$(".finding[data-i]").forEach(el => {
    el.addEventListener("mouseenter", () => hot(el.dataset.i, true));
    el.addEventListener("mouseleave", () => hot(el.dataset.i, false));
    el.addEventListener("click", () => { const b = $(`.box[data-i="${el.dataset.i}"]`); b && b.scrollIntoView({ behavior: "smooth", block: "center" }); });
  });
  loadHistory();
}

function findingHtml(d, n) {
  return `<li class="finding" data-i="${n}" style="--c:${d.color}">
    <div class="finding-top"><span class="n">${n}</span><strong>${esc(d.name)}</strong><span class="conf">${pct(d.confidence)} sure</span></div>
    <q>${esc(d.evidence)}</q>
    <p>${esc(d.explanation)}</p>
    ${d.regulation ? `<p class="law">Relevant EU rules: ${esc(d.regulation)}</p>` : ""}
  </li>`;
}

function drawBoxes(dets, size) {
  const wrap = $("#boxes"); wrap.innerHTML = "";
  const [W, H] = size || [$("#shot").naturalWidth, $("#shot").naturalHeight];
  dets.forEach((d, i) => {
    if (!d.box) return;
    const [x, y, w, h] = d.box;
    const b = document.createElement("div");
    b.className = "box"; b.dataset.i = i + 1; b.style.setProperty("--c", d.color);
    b.style.left = `${(x / W) * 100}%`; b.style.top = `${(y / H) * 100}%`;
    b.style.width = `${Math.max(1.2, (w / W) * 100)}%`; b.style.height = `${Math.max(1.2, (h / H) * 100)}%`;
    b.title = `${d.name}: ${d.evidence}`;
    b.innerHTML = `<b>${i + 1}</b>`;
    b.addEventListener("mouseenter", () => hot(i + 1, true));
    b.addEventListener("mouseleave", () => hot(i + 1, false));
    b.addEventListener("click", () => $(`.finding[data-i="${i + 1}"]`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }));
    wrap.appendChild(b);
  });
}
function hot(i, on) { $$(`[data-i="${i}"]`).forEach(el => el.classList.toggle("hot", on)); }

async function loadHistory() {
  try {
    const h = await api("/api/history");
    $("#historyWrap").hidden = !h.length;
    $("#history").innerHTML = h.map(x => `<button class="hist" data-id="${esc(x.id)}">
      <img src="${esc(x.image_url)}" alt="" loading="lazy">
      <div><div class="v ${x.is_dark ? "dark" : "fair"}">${x.is_dark ? esc(x.categories.join(", ") || "Dark pattern") : "No dark patterns"}</div>
      ${esc(x.created || "")}</div></button>`).join("");
    $$(".hist").forEach(b => b.addEventListener("click", async () => {
      const r = await api(`/api/history/${b.dataset.id}`); previewImage(r.image_url); render(r); window.scrollTo({ top: 0, behavior: "smooth" });
    }));
  } catch (e) {}
}

function setupInspect() {
  const drop = $("#drop"), file = $("#file");
  drop.addEventListener("click", e => { if (!e.target.closest(".samples")) file.click(); });
  drop.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); file.click(); } });
  file.addEventListener("change", () => analyzeFile(file.files[0]));
  ["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", e => analyzeFile(e.dataTransfer.files[0]));
  window.addEventListener("paste", e => {
    if (location.hash && location.hash !== "#inspect") return;
    const item = [...(e.clipboardData?.items || [])].find(i => i.type.startsWith("image/"));
    if (item) analyzeFile(item.getAsFile());
  });
  $("#urlForm").addEventListener("submit", e => { e.preventDefault(); const u = $("#urlInput").value.trim(); if (u) analyzeUrl(u); });
  $("#resetBtn").addEventListener("click", () => { file.value = ""; showEmpty(); });
  $("#pdfBtn").addEventListener("click", () => {
    // the browser's own "Save as PDF" print dialog, with a print-only layout (style.css @media print)
    if (!current) return;
    const when = new Date().toLocaleString();
    const src = current.page ? (current.page.url || current.page.title || "") : "uploaded screenshot";
    $("#printHead").innerHTML = `<h1>DarkLens report</h1><p>${esc(src)} · ${esc(when)}</p>`;
    const old = document.title;
    document.title = `darklens-report-${current.id || "page"}`;  // becomes the PDF's file name
    window.addEventListener("afterprint", () => { document.title = old; }, { once: true });
    $("#lowConf").open = true;
    window.print();
  });
  $("#downloadBtn").addEventListener("click", () => {
    if (!current) return;
    const blob = new Blob([JSON.stringify(current, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `darklens-report-${current.id}.json`; a.click();
  });
  drawSamples();
  // real EU shop samples, if scripts/make_eu_samples.py has made them
  fetch("samples/samples.json").then(r => r.ok ? r.json() : []).then(extra => {
    if (Array.isArray(extra) && extra.length) { SAMPLES.push(...extra.filter(x => x && x.url && x.label)); drawSamples(); }
  }).catch(() => {});
}
function drawSamples() {
  $("#samples").innerHTML = SAMPLES.map((s, i) => `<button type="button" data-i="${i}">${esc(s.label)}</button>`).join("");
  $$("#samples button").forEach(b => b.addEventListener("click", async e => {
    e.stopPropagation();
    const s = SAMPLES[b.dataset.i];
    try {
      const r = await fetch(s.url);
      if (!r.ok) throw new Error(r.status);
      const blob = await r.blob();
      analyzeFile(new File([blob], s.url.split("/").pop(), { type: "image/png" }));
    } catch (err) { toast("Sample image not found. Run scripts/make_samples.py."); }
  }));
}

/* ------------------------------------------------------------ annotate */
let annotator = "", annItem = null;
const KEYS = ["urgency", "scarcity", "social_proof", "confirmshaming", "preselection", "obstruction", "interface_interference", "forced_action"];

function setupAnnotate() {
  try { $("#annotator").value = localStorage.getItem("dl_annotator") || ""; } catch (e) {}
  $("#annotForm").addEventListener("submit", e => {
    e.preventDefault(); annotator = $("#annotator").value.trim(); if (!annotator) return;
    try { localStorage.setItem("dl_annotator", annotator); } catch (err) {}
    nextItem();
  });
  $("#labelGrid").innerHTML = KEYS.map((k, i) =>
    `<button type="button" data-label="${k}" style="--c:${catColor(k)}"><kbd>${i + 1}</kbd>${esc(catName(k))}</button>`).join("") +
    `<button type="button" class="fair-btn" data-label="not_dark" style="--c:var(--fair)"><kbd>0</kbd>Not a dark pattern</button>`;
  $$("#labelGrid button").forEach(b => b.addEventListener("click", () => saveLabel(b.dataset.label)));
  $("#skipBtn").addEventListener("click", () => skip());
  $("#undoBtn").addEventListener("click", () => undo());
  document.addEventListener("keydown", e => {
    if (location.hash !== "#annotate" || !annItem || e.target.tagName === "INPUT") return;
    if (e.key === "0") saveLabel("not_dark");
    else if (/^[1-8]$/.test(e.key)) saveLabel(KEYS[+e.key - 1]);
    else if (e.key.toLowerCase() === "s") skip();
    else if (e.key.toLowerCase() === "u") undo();
  });
  $("#agreeBox").addEventListener("toggle", async () => {
    if ($("#agreeBox").open) $("#agreeText").textContent = JSON.stringify(await api("/api/annotate/agreement"), null, 2);
  });
}
let skipped = new Set();
// a blind re-check is stored under "<name>-recheck" so it never overwrites the first pass
const who = () => $("#recheckMode").checked ? `${annotator}-recheck` : annotator;
const history = [];  // items labelled in this session, newest last (for "Undo last")
async function nextItem(again = "") {
  const adj = $("#adjMode").checked ? 1 : 0;
  const rc = $("#recheckMode").checked ? 1 : 0;
  const r = await api(`/api/annotate/next?annotator=${encodeURIComponent(who())}&skip=${[...skipped].join(",")}&adjudicate=${adj}&recheck=${rc}` +
    (again ? `&segment_id=${encodeURIComponent(again)}` : ""));
  $("#undoBtn").disabled = !history.length;
  $("#annotBody").hidden = r.done; $("#annotDone").hidden = !r.done;
  if (r.done) {
    $("#annotDone").innerHTML = (r.total && rc) ? `<h2>Re-check done: ${r.total} items.</h2><p>Now run <code>python scripts/annotation_results.py</code>.</p>`
      : (r.total && adj) ? `<h2>All ${r.total} disagreements settled.</h2><p>Now run <code>python scripts/agreement.py --annotators devanshi aarya --adjudicator ${esc(annotator.toLowerCase())}</code>.</p>`
      : r.total ? `<h2>All ${r.total} items labelled.</h2><p>Thank you, ${esc(annotator)}. After a break of a few hours, come back, tick <strong>Blind re-check</strong> and label the 50 items it gives you.</p>`
      : `<h2>Nothing to label yet</h2><p>${esc(r.message)}</p>`;
    annItem = null; return;
  }
  annItem = r.item;
  const yours = annItem.your_label;
  $("#aYours").hidden = !yours;
  $("#aYours").textContent = yours ? `You labelled this "${yours === "not_dark" ? "Not a dark pattern" : catName(yours)}". Pick the right label to replace it.` : "";
  $("#progBar").style.width = `${(100 * r.labelled) / r.total}%`;
  $("#progText").textContent = rc ? `${r.labelled} of ${r.total} re-checked` : adj ? `${r.labelled} of ${r.total} disagreements settled` : `${r.labelled} of ${r.total} labelled`;
  const earlier = Object.entries(annItem.earlier || {});
  $("#aEarlier").hidden = !earlier.length;
  $("#aEarlier").textContent = earlier.length ? "Earlier labels: " + earlier.map(([n, l]) =>
    `${n} said ${l === "not_dark" ? "not a dark pattern" : catName(l)}`).join(", ") : "";
  $("#aUi").textContent = `${annItem.kind} on a ${annItem.page_type || "unknown"} page ${annItem.ui || ""}`;
  $("#aText").textContent = annItem.text;
  const en = (annItem.text_en || "").trim();
  const showEn = en && en.toLowerCase() !== (annItem.text || "").trim().toLowerCase();
  $("#aEn").hidden = !showEn;
  $("#aEn").textContent = showEn ? `In English: ${en}` : "";
  const lang = (annItem.language || "").toLowerCase();
  const tr = $("#aTr");
  tr.hidden = !!showEn || lang === "en";
  if (!tr.hidden) tr.href = `https://translate.google.com/?sl=auto&tl=en&op=translate&text=${encodeURIComponent(annItem.text || "")}`;
  $("#aMeta").textContent = annItem.url || "";
  const live = $("#liveLink");
  live.hidden = !/^https?:\/\//.test(annItem.url || "");
  if (!live.hidden) live.href = annItem.url;
  const crop = $("#crop");
  crop.innerHTML = ""; crop.className = "crop";
  const link = $("#fullLink");
  if (annItem.screenshot) {
    const sid = encodeURIComponent(annItem.segment_id);
    crop.classList.add("loading"); crop.textContent = "Loading the page around this item...";
    const narrow = window.innerWidth < 760 ? 1 : 0;
    const want = annItem.segment_id;
    fetch(`/api/annotate/crop?segment_id=${sid}&narrow=${narrow}`).then(async (r) => {
      if (!r.ok) throw new Error(r.status);
      const shown = r.headers.get("X-Item-Shown") !== "0";
      const url = URL.createObjectURL(await r.blob());
      if (!annItem || annItem.segment_id !== want) return;  // moved on meanwhile
      const img = new Image();
      img.alt = shown ? "The part of the web page around this item, outlined" : "The top of the web page this item came from";
      img.onload = () => {
        crop.textContent = ""; crop.classList.remove("loading"); crop.appendChild(img);
        if (!shown) {
          const n = document.createElement("p"); n.className = "crop-note";
          n.textContent = "This item can't be seen in the screenshot (it was hidden, still loading, or further down than the screenshot reaches). Judge it from the text, or tap “Open the live page” to look at the real shop. The picture only shows which page it was on.";
          crop.appendChild(n);
        }
      };
      img.src = url;
    }).catch(() => {
      if (!annItem || annItem.segment_id !== want) return;
      crop.classList.remove("loading"); crop.classList.add("none"); crop.textContent = "Screenshot not available for this item";
    });
    link.href = `/api/annotate/full?segment_id=${sid}`; link.hidden = false;
  } else {
    crop.classList.add("none"); crop.textContent = "No screenshot for this item"; link.hidden = true;
  }
}
async function saveLabel(label) {
  if (!annItem) return;
  try {
    await api("/api/annotate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ annotator: who(), segment_id: annItem.segment_id, label }) });
    if (history[history.length - 1] !== annItem.segment_id) history.push(annItem.segment_id);
    nextItem();
  } catch (e) { toast(e.message); }
}
function undo() {
  const id = history.pop();
  if (!id) return toast("Nothing to undo yet.");
  $("#annotBody").hidden = false; $("#annotDone").hidden = true;
  nextItem(id);
}
function skip() { if (!annItem) return; skipped.add(annItem.segment_id); toast("Skipped. It comes back once everything else is labelled."); nextItem(); }

/* ------------------------------------------------------------ results */
function row(cells) {
  return `<tr>${cells.map(c => `<td class="${typeof c === "number" ? "num" : ""}">${typeof c === "number" ? (Number.isInteger(c) ? c : f3(c)) : esc(c)}</td>`).join("")}</tr>`;
}
async function loadResults() {
  const body = $("#resultsBody");
  let R;
  try { R = await api("/api/results"); } catch (e) { body.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  let html = `<h1>Evaluation results</h1><p class="lede">Every number here is read from the <code>results/</code> folder,
    so it updates as soon as an experiment script finishes. Missing rows mean that experiment hasn't been run yet.</p>`;
  const b = R.baselines;
  if (b) {
    html += `<div class="res-block"><h2>Text classification on the EC dataset</h2>
      <p>${b.dataset.n} snippets (${b.dataset.n_dark} dark), ${esc(b.dataset.cv)}.</p>
      <table><tr><th>Model</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th><th class="num">Macro-F1 (categories)</th></tr>
      ${["rules", "tfidf_lr", "tfidf_svm"].map(k => row([{ rules: "Rule lexicon", tfidf_lr: "TF-IDF + logistic regression", tfidf_svm: "TF-IDF + linear SVM" }[k],
        b.binary[k].precision, b.binary[k].recall, b.binary[k].f1, b.multiclass[k].macro_f1])).join("")}
      ${R.roberta_binary ? row(["RoBERTa-base", R.roberta_binary.precision, R.roberta_binary.recall, R.roberta_binary.f1, R.roberta_multiclass ? R.roberta_multiclass.macro_f1 : "–"]) : ""}
      ${Object.entries(R).filter(([k]) => k.startsWith("llm_text_")).map(([k, v]) => row([`LLM ${v.engine.model} (${v.mode})`, v.binary.precision, v.binary.recall, v.binary.f1, v.multiclass.macro_f1])).join("")}
      </table></div>`;
  }
  const tb = Object.entries(R).filter(([k]) => k.startsWith("testbed_"));
  if (tb.length) {
    html += `<div class="res-block"><h2>Controlled test-bed (DarkMart vs FairMart)</h2>
      <p>Known, injected patterns on a local shop and its clean twin. Recall is over injected instances; false positives are counted on the clean shop.</p>
      <table><tr><th>Engine</th><th class="num">Instance recall</th><th class="num">Precision</th><th class="num">Fair-shop false alarms</th></tr>
      ${tb.map(([k, v]) => row([`${v.detector.model} (${v.mode})`, v.instance_recall, v.darkshop_prediction_precision, v.fairshop_false_positive_unique])).join("")}</table></div>`;
  }
  const ss = Object.entries(R).filter(([k]) => k.startsWith("screenshots_") && !k.endsWith("_predictions"));
  if (ss.length) {
    html += `<div class="res-block"><h2>Screenshot detection on AidUI / ContextDP</h2>
      <p>Image-level scoring: does the screenshot contain a dark pattern, and which categories.</p>
      <table><tr><th>Split and engine</th><th class="num">Precision</th><th class="num">Recall</th><th class="num">F1</th><th class="num">Category macro-F1</th></tr>
      ${ss.map(([k, v]) => row([`${v.split}: ${v.engine.model}${v.engine.engine === "llm" ? ` (${v.mode}${v.engine.ocr === false ? ", image only, no OCR" : ", with OCR"})` : ""}`, v.binary.precision, v.binary.recall, v.binary.f1, v.macro_f1])).join("")}</table></div>`;
  }
  const ce = R.crawl_evaluation;
  if (ce) {
    const p = ce.prevalence, cov = ce.coverage || {};
    const ci = v => v ? `${Number(v[0]).toFixed(2)} to ${Number(v[1]).toFixed(2)}` : "–";
    html += `<div class="res-block"><h2>EU crawl: coverage</h2>
      <p>Shops that block automated browsers (Cloudflare, captchas) are recorded, never bypassed, and left out of the figures below.</p>
      <div class="stat-row">
        <div class="stat"><b>${cov.attempted ?? "–"}</b><span>shops attempted</span></div>
        <div class="stat"><b>${cov.crawled ?? "–"}</b><span>crawled (${cov.crawled_countries ?? "–"} countries)</span></div>
        <div class="stat"><b>${cov.blocked ?? "–"}</b><span>blocked by bot protection (${cov.attempted ? pct(cov.blocked / cov.attempted) : "–"})</span></div>
        <div class="stat"><b>${cov.crawled_pages ?? "–"}</b><span>pages captured</span></div>
      </div></div>`;
    html += `<div class="res-block"><h2>EU crawl: how common is each pattern?</h2>
      <p>${p.n_sites} sites, ${p.n_states} page states. ${p.sites_with_any_pattern} sites (${pct(p.share_sites_with_any_pattern)}) show at least one pattern.
        Share of sites with at least one instance of each class. These are lower bounds, because detection is conservative (see below).</p>
      <table>${Object.entries(p.by_category).sort((a, b) => b[1] - a[1]).map(([c, v]) =>
        `<tr><td>${esc(catName(c))}</td><td class="bar-cell"><div class="hbar" style="width:${v * 100}%;background:${catColor(c)}"></div></td><td class="num">${pct(v)}</td></tr>`).join("")}</table>
      </div>`;
    const ev = ce.evaluation, pop = ev && ev.population, smp = ev && ev.binary_sample;
    if (pop) {
      const st = pop.strata || {}, names = { flagged: "Flagged by the LLM", cleared: "Cleared by the LLM", filtered: "Filtered out before the LLM" };
      html += `<div class="res-block"><h2>EU crawl: accuracy against human labels</h2>
        <p>${smp ? smp.n : "–"} distinct elements labelled by a trained annotator, sampled at random from three groups and weighted by group size,
          so the numbers describe the whole crawl, not just the sample.</p>
        <div class="stat-row">
          <div class="stat"><b>${f2(pop.precision)}</b><span>precision (95% CI ${ci(pop.precision_ci95)}): when DarkLens flags something, it is almost always a real pattern</span></div>
          <div class="stat"><b>${f2(pop.recall)}</b><span>estimated recall (95% CI ${ci(pop.recall_ci95)}): it finds only a small share of all dark elements</span></div>
          ${smp ? `<div class="stat"><b>${f2(smp.f1)}</b><span>F1 on the labelled sample itself (κ ${f2(smp.kappa)}), which over-represents flagged elements</span></div>` : ""}
        </div>
        <table><tr><th>Group</th><th class="num">Labelled</th><th class="num">Dark (human)</th><th class="num">Dark share</th><th class="num">Elements in crawl</th></tr>
        ${["flagged", "cleared", "filtered"].filter(k => st[k]).map(k => `<tr><td>${names[k]}</td><td class="num">${st[k].n}</td><td class="num">${st[k].gold_dark}</td><td class="num">${pct(st[k].dark_rate)}</td><td class="num">${Math.round(st[k].units).toLocaleString()}</td></tr>`).join("")}
        </table>
        <p class="note">Why recall is low: about one in ten cleared or filtered elements is dark, and those groups are huge, so small misses add up.
          ${pct(pop.share_of_misses_from_prefilter)} of the estimated misses never reached the LLM; they were dropped by the cheap pre-filter, mostly short social-proof badges such as "Very popular".</p>
        </div>`;
    } else if (ev) {
      html += `<div class="res-block"><h2>EU crawl: accuracy against human labels</h2><p>Against human ground truth (${ev.binary.n} items): precision ${f3(ev.binary.precision)}, recall ${f3(ev.binary.recall)}. Re-run <code>python scripts/evaluate_crawl.py</code> for the weighted estimates.</p></div>`;
    } else {
      html += `<div class="res-block"><h2>EU crawl: accuracy</h2><p class="pending">Human ground truth not labelled yet.</p></div>`;
    }
    const ha = R.human_agreement;
    if (ha && (ha.pilot || ha.second_annotator || ha.model_second_opinion)) {
      const r = (label, d, note) => d && d.n ? `<tr><td>${label}</td><td class="num">${d.n}</td><td class="num">${pct(d.raw_agreement)}</td><td class="num">${f2(d.kappa_category)}</td><td class="num">${f2(d.kappa_binary)}</td><td>${note}</td></tr>` : "";
      html += `<div class="res-block"><h2>Quality of the human labels</h2>
        <p>Cohen's κ: 0.21 to 0.40 is fair, 0.61 to 0.80 substantial, above 0.80 almost perfect (Landis and Koch).</p>
        <table><tr><th>Comparison</th><th class="num">Items</th><th class="num">Agreement</th><th class="num">κ category</th><th class="num">κ dark or not</th><th></th></tr>
        ${r("Pilot: two annotators, no written guide", ha.pilot, "led us to write a labelling guide")}
        ${r("With the guide: second annotator vs ground truth", ha.second_annotator, "independent, same 50 items")}
        ${r("Independent LLM vs ground truth", ha.model_second_opinion, esc((ha.model_second_opinion?.models || []).join(", ")))}
        </table></div>`;
    }
  } else {
    html += `<div class="res-block"><h2>EU crawl</h2><p class="pending">Not run yet. See the README section "Run the EU study".</p></div>`;
  }
  body.innerHTML = html;
}

/* ------------------------------------------------------------ taxonomy */
function renderTaxonomy() {
  $("#taxoList").innerHTML = TAXO.map(c => `<article class="tx" style="--c:${c.color}"><i></i><div>
    <h2>${esc(c.name)}</h2><p>${esc(c.definition)}</p>
    <p class="ex"><b>Looks like:</b> ${c.examples.map(esc).join("; ")}</p>
    <p class="ex"><b>Fine:</b> ${c.counter_examples.map(esc).join("; ")}</p>
    <p class="ex"><b>EU pointer:</b> ${esc(c.regulation)}</p></div></article>`).join("");
}

/* ------------------------------------------------------------ boot */
(async function boot() {
  try { TAXO = await api("/api/taxonomy"); } catch (e) { TAXO = []; }
  $("#legend").innerHTML = TAXO.map(c => `<li style="--c:${c.color}"><i></i>${esc(c.name)}</li>`).join("");
  setupInspect(); setupAnnotate(); route(); loadStatus(); loadHistory();
})();
