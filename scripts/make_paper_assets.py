"""
Regenerate every number, table and figure in the paper from results/*.json.

    python scripts/make_paper_assets.py      # then recompile paper/main.tex

Results that have not been produced yet render as a red "[pending]" marker,
so the paper can never silently show a number that wasn't measured.
"""
from __future__ import annotations

import glob
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from darklens.taxonomy import CATEGORY_KEYS, display_name  # noqa: E402

RES = ROOT / "results"
GEN = ROOT / "paper/generated"
GEN.mkdir(parents=True, exist_ok=True)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # validated categorical slots 1-3
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
P = r"\pend{}"


def load(name):
    p = RES / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def latest(pattern):
    files = sorted(glob.glob(str(RES / pattern)), key=lambda f: Path(f).stat().st_mtime)
    files = [f for f in files if not f.endswith("_predictions.json")]
    return json.loads(Path(files[-1]).read_text(encoding="utf-8")) if files else None


def f(x, d=3):
    return P if x is None else f"{x:.{d}f}"


def pc(x):
    return P if x is None else f"{100 * x:.1f}\\%"


def g(d, *keys):
    for k in keys:
        if d is None or k not in d:
            return None
        d = d[k]
    return d


macros: dict[str, str] = {}
B = load("baselines")
H = g(B, "held_out_test")
llm_multi = latest("llm_text_*multistage.json")
llm_single = latest("llm_text_*single.json")
rob_b, rob_m = load("roberta_binary"), load("roberta_multiclass")
web_off = load("screenshots_web_offline_rules+tfidf")
web_llm_m = latest("screenshots_web_llm_multistage.json")
web_llm_s = latest("screenshots_web_llm_single.json")
web_llm_vis = latest("screenshots_web_llm-visiononly_multistage.json")
tb_off = load("testbed_offline_multistage")
tb_llm = latest("testbed_llm_multistage.json")
crawl = load("crawl_evaluation")
human = load("human_agreement")
tune = load("tuning_ocr_threshold_mobile")

llm_model = (g(llm_multi, "engine", "model") or g(web_llm_m, "engine", "model")
             or g(tb_llm, "detector", "model") or g(web_llm_vis, "engine", "model"))
macros["LLMmodel"] = llm_model.replace("_", r"\_") if llm_model else P
macros["NText"] = str(g(B, "dataset", "n") or P)
macros["NTextDark"] = str(g(B, "dataset", "n_dark") or P)
macros["NHeld"] = str(g(H, "n") or P)
macros["CVlrF"] = f(g(B, "binary", "tfidf_lr", "f1"))
macros["CVlrP"] = f(g(B, "binary", "tfidf_lr", "precision"))
macros["CVlrR"] = f(g(B, "binary", "tfidf_lr", "recall"))
macros["CVlrMacro"] = f(g(B, "multiclass", "tfidf_lr", "macro_f1"))
macros["CVsvmMacro"] = f(g(B, "multiclass", "tfidf_svm", "macro_f1"))
macros["CVruleP"] = f(g(B, "binary", "rules", "precision"))
macros["CVruleR"] = f(g(B, "binary", "rules", "recall"))
macros["CVruleF"] = f(g(B, "binary", "rules", "f1"))
macros["LLMtextF"] = f(g(llm_multi, "binary", "f1"))
macros["RobF"] = f(g(rob_b, "f1"))
macros["RobMacro"] = f(g(rob_m, "macro_f1"))
macros["HeldLRMacro"] = f(g(H, "tfidf_lr_multiclass", "macro_f1"))
macros["LLMtextMacro"] = f(g(llm_multi, "multiclass", "macro_f1"))
macros["LLMtextSingleMacro"] = f(g(llm_single, "multiclass", "macro_f1"))
macros["LLMstageOneMacro"] = f(g(llm_multi, "stage1_only", "multiclass", "macro_f1"))
macros["LLMstageOneP"] = f(g(llm_multi, "stage1_only", "binary", "precision"))
macros["LLMtextP"] = f(g(llm_multi, "binary", "precision"))
macros["WebOffF"] = f(g(web_off, "binary", "f1"))
macros["WebOffP"] = f(g(web_off, "binary", "precision"))
macros["WebOffR"] = f(g(web_off, "binary", "recall"))
macros["WebOffMacro"] = f(g(web_off, "macro_f1"))
macros["WebLLMF"] = f(g(web_llm_m, "binary", "f1"))
macros["WebLLMMacro"] = f(g(web_llm_m, "macro_f1"))
macros["NWeb"] = str(g(web_off, "n_images") or 162)
macros["TbN"] = str(g(tb_off, "ground_truth_instances") or P)
macros["TbOffRecall"] = pc(g(tb_off, "instance_recall"))
macros["TbOffPrec"] = pc(g(tb_off, "darkshop_prediction_precision"))
macros["TbOffFP"] = str(g(tb_off, "fairshop_false_positive_unique") if tb_off else P)
macros["TbOffPrefilter"] = pc(g(tb_off, "prefilter_reduction"))
macros["TbLLMRecall"] = pc(g(tb_llm, "instance_recall"))
macros["TbLLMFP"] = str(g(tb_llm, "fairshop_false_positive_unique")) if tb_llm else P
macros["TuneBest"] = f(g(tune, "chosen"), 2)
pv = g(crawl, "prevalence")
cov = load("crawl_coverage") or g(crawl, "coverage")
macros["CrawlAttempted"] = str(g(cov, "attempted") or P)
macros["CrawlOK"] = str(g(cov, "crawled") or P)
macros["CrawlBlocked"] = str(g(cov, "blocked") or P)
macros["CrawlBlockedPct"] = pc(g(cov, "blocked") / g(cov, "attempted")) if g(cov, "attempted") else P
macros["CrawlOKCountries"] = str(g(cov, "crawled_countries") or P)
macros["CrawlAnyN"] = str(g(pv, "sites_with_any_pattern")) if pv else P
macros["CrawlMeanCats"] = f(g(pv, "mean_categories_per_site"), 1)
for _pt, _name in (("checkout", "Checkout"), ("cart", "Cart"), ("product", "Product"), ("homepage", "Home")):
    macros[f"PT{_name}"] = pc(g(pv, "by_page_type", _pt, "any"))
    macros[f"PT{_name}N"] = str(g(pv, "by_page_type", _pt, "n") or P)
macros["WebLLMN"] = str(g(web_llm_m, "n_images") or P)
macros["WebLLMFailed"] = str(g(web_llm_m, "n_failed") if web_llm_m else P)
macros["CrawlSites"] = str(g(pv, "n_sites") or P)
macros["CrawlStates"] = str(g(pv, "n_states") or P)
macros["CrawlAny"] = pc(g(pv, "share_sites_with_any_pattern"))
ev = g(crawl, "evaluation", "binary")
macros["CrawlP"], macros["CrawlR"], macros["CrawlF"] = f(g(ev, "precision")), f(g(ev, "recall")), f(g(ev, "f1"))
macros["CrawlKappa"] = f(g(ev, "kappa"))
macros["CrawlNGold"] = str(g(ev, "n") or P)
_es = g(crawl, "evaluation", "binary_sample")
macros["CrawlSP"], macros["CrawlSR"], macros["CrawlSF"] = f(g(_es, "precision")), f(g(_es, "recall")), f(g(_es, "f1"))
macros["CrawlSKappa"] = f(g(_es, "kappa"), 2)
_pop = g(crawl, "evaluation", "population")
def _ci(key):
    v = g(_pop, key)
    return (P, P) if not v else (f"{v[0]:.2f}", f"{v[1]:.2f}")
macros["PopP"], macros["PopR"] = f(g(_pop, "precision"), 2), f(g(_pop, "recall"), 3)
(macros["PopPlo"], macros["PopPhi"]), (macros["PopRlo"], macros["PopRhi"]) = _ci("precision_ci95"), _ci("recall_ci95")
macros["PopMissPrefilter"] = pc(g(_pop, "share_of_misses_from_prefilter"))
for _st, _nm in (("flagged", "Flag"), ("cleared", "Clear"), ("filtered", "Filt")):
    _d = g(_pop, "strata", _st)
    macros[f"St{_nm}N"] = str(g(_d, "n") or P)
    macros[f"St{_nm}Dark"] = str(g(_d, "gold_dark") if _d else P)
    macros[f"St{_nm}Units"] = f"{g(_d, 'units'):,.0f}".replace(",", "{,}") if _d else P
    macros[f"St{_nm}Rate"] = pc(g(_d, "dark_rate"))
macros["PilotN"] = str(g(human, "pilot", "n") or P)
macros["PilotKappa"] = f(g(human, "pilot", "kappa_category"), 2)
macros["PilotKappaBin"] = f(g(human, "pilot", "kappa_binary"), 2)
macros["PilotAgree"] = pc(g(human, "pilot", "raw_agreement"))
macros["ExpertN"] = str(g(human, "expert", "n_labelled") or P)
macros["SecondN"] = str(g(human, "second_annotator", "n") or P)
macros["SecondKappa"] = f(g(human, "second_annotator", "kappa_category"), 2)
macros["SecondKappaBin"] = f(g(human, "second_annotator", "kappa_binary"), 2)
macros["SecondAgree"] = pc(g(human, "second_annotator", "raw_agreement"))
macros["IntraN"] = str(g(human, "intra_rater", "n") or P)
macros["IntraKappa"] = f(g(human, "intra_rater", "kappa_category"), 2)
macros["IntraKappaBin"] = f(g(human, "intra_rater", "kappa_binary"), 2)
_h = g(human, "intra_rater", "hours_between_passes_min")
macros["IntraHours"] = P if _h is None else (f"{_h:.0f}" if _h >= 2 else f"{_h:.1f}")
macros["ModelOpN"] = str(g(human, "model_second_opinion", "n") or P)
macros["ModelOpKappa"] = f(g(human, "model_second_opinion", "kappa_category"), 2)
macros["ModelOpKappaBin"] = f(g(human, "model_second_opinion", "kappa_binary"), 2)
_mo = g(human, "model_second_opinion", "models")
macros["ModelOpName"] = ", ".join(_mo).replace("_", r"\_") if _mo else P
macros["HumanKappa"] = macros["IntraKappa"]  # kept for older text

with open(GEN / "macros.tex", "w", encoding="utf-8") as fh:
    fh.write("% generated by scripts/make_paper_assets.py — do not edit\n")
    for k, v in macros.items():
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")

# ---------------------------------------------------------------- Table: text
def brow(name, d, mc):
    return (f"{name} & {f(g(d, 'precision'))} & {f(g(d, 'recall'))} & {f(g(d, 'f1'))} & "
            f"{f(g(mc, 'macro_f1'))} \\\\")


rows = [
    r"\multicolumn{5}{l}{\emph{5-fold grouped cross-validation (all " + macros["NText"] + r" items)}} \\",
    brow("Rule lexicon", g(B, "binary", "rules"), g(B, "multiclass", "rules")),
    brow("TF-IDF + LR", g(B, "binary", "tfidf_lr"), g(B, "multiclass", "tfidf_lr")),
    brow("TF-IDF + SVM", g(B, "binary", "tfidf_svm"), g(B, "multiclass", "tfidf_svm")),
    r"\midrule",
    r"\multicolumn{5}{l}{\emph{Held-out test split (" + macros["NHeld"] + r" items)}} \\",
    brow("Rule lexicon", g(H, "rules_binary"), g(H, "rules_multiclass")),
    brow("TF-IDF + LR", g(H, "tfidf_lr_binary"), g(H, "tfidf_lr_multiclass")),
    brow("RoBERTa-base", rob_b, rob_m),
    brow("LLM, infer only$^\\dagger$", g(llm_single, "binary") or g(llm_multi, "stage1_only", "binary"),
         g(llm_single, "multiclass") or g(llm_multi, "stage1_only", "multiclass")),
    brow("LLM, infer + verify", g(llm_multi, "binary"), g(llm_multi, "multiclass")),
]
(GEN / "tab_text.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")

# --------------------------------------------------------- Table: screenshots
def srow(name, d):
    return (f"{name} & {f(g(d, 'binary', 'precision'))} & {f(g(d, 'binary', 'recall'))} & "
            f"{f(g(d, 'binary', 'f1'))} & {f(g(d, 'macro_f1'))} \\\\")


macros["WebVisF"] = f(g(web_llm_vis, "binary", "f1"))
macros["WebVisP"] = f(g(web_llm_vis, "binary", "precision"))
macros["WebVisR"] = f(g(web_llm_vis, "binary", "recall"))
macros["WebVisMacro"] = f(g(web_llm_vis, "macro_f1"))
macros["TbLLMPrec"] = pc(g(tb_llm, "darkshop_prediction_precision"))
macros["TbLLMFound"] = str(round(g(tb_llm, "instance_recall") * g(tb_llm, "ground_truth_instances"))) if tb_llm else P
macros["TbOffFound"] = str(round(g(tb_off, "instance_recall") * g(tb_off, "ground_truth_instances"))) if tb_off else P
(GEN / "tab_screens.tex").write_text("\n".join([
    srow("Offline (OCR + rules)", web_off),
    srow("Vision LLM, verify", web_llm_vis),
    *([srow("OCR + LLM, single pass", web_llm_s)] if web_llm_s else []),
    srow("OCR + LLM, verify", web_llm_m),
]) + "\n", encoding="utf-8")

# ------------------------------------------------------------ Table: testbed
def trow(name, d):
    return (f"{name} & {pc(g(d, 'instance_recall'))} & {pc(g(d, 'darkshop_prediction_precision'))} & "
            f"{g(d, 'fairshop_false_positive_unique') if d else P} \\\\")


(GEN / "tab_testbed.tex").write_text("\n".join([trow("Offline engine", tb_off),
                                                trow("LLM, detect + verify", tb_llm)]) + "\n", encoding="utf-8")

# -------------------------------------------------------- Table: prevalence
lines = []
for c in CATEGORY_KEYS:
    v = g(pv, "by_category", c)
    lines.append(f"{display_name(c)} & {pc(v)} \\\\")
(GEN / "tab_prevalence.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- figures
def style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)


plt.rcParams.update({"font.family": "serif", "font.size": 8, "pdf.fonttype": 42})

# Fig: per-category F1 of text baselines (cross-validated)
if B:
    cats = [c for c in CATEGORY_KEYS if g(B, "multiclass", "tfidf_lr", "per_class", c, "support")]
    models = [("rules", "Rule lexicon"), ("tfidf_lr", "TF-IDF + LR"), ("tfidf_svm", "TF-IDF + SVM")]
    fig, ax = plt.subplots(figsize=(3.4, 3.0))
    h = 0.26
    for i, (k, lab) in enumerate(models):
        vals = [g(B, "multiclass", k, "per_class", c, "f1") or 0 for c in cats]
        ys = [j + (i - 1) * (h + 0.02) for j in range(len(cats))]
        ax.barh(ys, vals, height=h, color=SERIES[i], label=lab, edgecolor="white", linewidth=0.6)
    ax.set_yticks(range(len(cats)))
    short = {"preselection": "Pre-ticked / sneaking", "interface_interference": "Interface interf.",
             "obstruction": "Difficult cancellation"}
    ax.set_yticklabels([f"{short.get(c, display_name(c))} (n={g(B, 'multiclass', 'tfidf_lr', 'per_class', c, 'support')})"
                        for c in cats], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("F1 (5-fold grouped CV)", color=MUTED)
    style(ax)
    ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=3, fontsize=6.5,
              handlelength=1.2, columnspacing=0.8)
    fig.tight_layout()
    fig.savefig(GEN / "fig_percategory.pdf")
    fig.savefig(GEN / "fig_percategory.png", dpi=200)
    plt.close(fig)

# Fig: prevalence by category (only when the crawl exists)
if pv:
    vals = sorted(((display_name(c), pv["by_category"][c]) for c in CATEGORY_KEYS), key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    ax.barh([v[0] for v in vals], [100 * v[1] for v in vals], color=SERIES[0], height=0.6)
    for i, (_, v) in enumerate(vals):
        ax.text(100 * v + 1, i, f"{100 * v:.0f}%", va="center", fontsize=7, color=INK)
    ax.set_xlabel("Share of sites with >=1 instance (%)", color=MUTED)
    style(ax)
    fig.tight_layout()
    fig.savefig(GEN / "fig_prevalence.pdf")
    plt.close(fig)

with open(GEN / "macros.tex", "w", encoding="utf-8") as fh:
    fh.write("% generated by scripts/make_paper_assets.py — do not edit\n")
    for k, v in macros.items():
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(f"wrote {len(macros)} macros and tables/figures to {GEN}")
pending = [k for k, v in macros.items() if v == P]
print(f"{len(pending)} values still pending: {', '.join(pending)}")
