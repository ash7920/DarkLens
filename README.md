# DarkLens

Our final year major project at Dwarkadas J. Sanghvi College of Engineering, Mumbai (B.Tech Computer
Engineering, 2026-27).

Team: Ashka Jain, Aarya Singh, Devanshi Shah, Dhruv Patel. Guide: Dr. Kranti Ghag.

DarkLens looks for dark patterns on shopping websites. These are the design tricks that push you into
doing something you didn't really mean to do, like a countdown timer that resets when you reload, a
"no thanks, I don't like saving money" button, an add-on that is already ticked in your cart, or a
subscription that takes five screens to cancel.

The project has three parts:

1. A crawler that visits EU online shops and works its way from the home page to product, cart and
   checkout pages, saving the HTML, the visible text, every button and checkbox (with its position and
   whether it was pre-ticked) and a screenshot of each page.
2. A detector that goes through everything the crawler saved. Cheap rules and a TF-IDF classifier throw
   out text that obviously isn't a dark pattern, and an LLM looks at what's left. The LLM first says
   what it thinks it found and then a second call checks that answer, which cut down a lot of false
   alarms in our tests.
3. A web app where you can upload a screenshot of any shop page and see the dark patterns boxed on it
   with a short explanation. The same app has the labelling screen we used to make our ground truth.

![Block diagram](docs/block_diagram.png)

## Categories

We use eight categories, based on Mathur et al. (2019) and the five classes in our original block
diagram: urgency, scarcity, social proof, confirmshaming, pre-selection (pre-ticked add-ons /
sneaking), obstruction (hard to cancel), interface interference and forced action. The full
definitions, with the EU rules each one might fall under, are in `darklens/taxonomy.py` and on the
Taxonomy tab of the app.

## Setting it up

You need Python 3.10 or newer. On Windows (which is what we used):

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
python scripts/train_baselines.py
python -m pytest -q
```

`train_baselines.py` trains the small offline models and makes the train/test splits. It needs the
three public datasets (Mathur et al., AidUI and the EC dark pattern corpus from Yada et al.); `scripts/download_datasets.sh`
clones them into `data/external/`. If you don't have bash, open that file and run the three
`git clone` lines yourself.

For screenshots you also need Tesseract OCR. On Windows install it from
https://github.com/UB-Mannheim/tesseract/wiki (tick German, French, Spanish, Italian and Dutch while
installing), then tell DarkLens where it is:

```
setx TESSERACT_CMD "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

and open a new terminal.

### The LLM

We used Google's Gemini API on the free tier, with `gemini-3.5-flash-lite`. The code also works with
OpenAI, Anthropic or a local model through Ollama. Set the key in the terminal you're using (don't put
it in a file or commit it):

```
$env:DARKLENS_PROVIDER="gemini"
$env:GEMINI_API_KEY="your key"
```

For other providers use `openai` / `OPENAI_API_KEY`, `anthropic` / `ANTHROPIC_API_KEY` or `ollama` /
`OLLAMA_HOST`. `DARKLENS_MODEL` picks a different model; `docs/gemini_models.md` shows how to list the
ones your key can use.

Without any key everything still runs on the offline engine (rules + TF-IDF + OCR). It's worse, but
it works.

A few things we learnt the hard way with the free tier:

- "Model overloaded" (503) happens a lot. The client waits and retries on its own. Set
  `DARKLENS_RETRIES` higher (we used 25) for long runs.
- When the daily quota runs out (429) the script stops straight away and tells you when it resets
  (midnight Pacific, about 1:30 pm in India). Every answer is cached in `data/llm_cache/`, so
  re-running the same command picks up where it stopped.
- Each model has its own daily quota, so switching models gets you more calls in a day.

## Running the app

```
uvicorn app.server:app --port 8000
```

Then open http://localhost:8000. There are four tabs: Inspect (upload or paste a screenshot, or give
a URL), Annotate (labelling), Results (all our numbers) and Taxonomy.

To let someone outside your Wi-Fi use it (we did this so the rest of the group could label from their
phones), run a Cloudflare quick tunnel in a second window:

```
cloudflared tunnel --url http://localhost:8000
```

It prints a `trycloudflare.com` link. Anyone coming in through that link only gets the offline
engine and can't use the URL inspector, so they can't use up your API quota or make your laptop open
random pages. The link changes every time you restart the tunnel.

## Running the study

These are the steps in the order we ran them. Everything writes to `results/`, and the paper's tables
are generated from those files, so nothing gets typed in by hand.

```
# test shop with known dark patterns (DarkMart) and a clean twin (FairMart)
python scripts/eval_testbed.py --engine offline
python scripts/eval_testbed.py --engine llm

# LLM on the held-out text set, with and without the verify step
python scripts/eval_llm_text.py --mode multistage
python scripts/eval_llm_text.py --mode single

# RoBERTa baseline: run on a Colab GPU, instructions at the top of the file
scripts/train_roberta.py

# screenshots from AidUI
python scripts/eval_screenshots.py --split web --engine llm --mode multistage

# the crawl (resumable, just run it again if it stops)
python -m darklens.crawler.run_sites --workers 2 --sites config/sites_eu.csv config/sites_eu_extra.csv config/sites_eu_extra2.csv
python -m darklens.crawler.run_sites --retry-failed --sites config/sites_eu.csv config/sites_eu_extra.csv config/sites_eu_extra2.csv
python -m darklens.crawler.coverage

# detection over everything the crawl saved
python -m darklens.pipeline --engine llm

# human labels
python scripts/make_annotation_sample.py --flagged -1 --cleared 400 --filtered 200
python scripts/translate_sample.py
#   two people label in the Annotate tab, then:
python scripts/agreement.py --annotators devanshi aarya
#   a third person labels the disagreements, then:
python scripts/agreement.py --annotators devanshi aarya --adjudicator ashka
python scripts/evaluate_crawl.py

# rebuild the paper's numbers, tables and figures
python scripts/make_paper_assets.py
```

The paper itself is `paper/main.tex` (IEEE conference format). Anything we haven't measured yet
shows up in red as [pending].

## Results so far

| What | Result |
|---|---|
| Text classification, held-out test set (471 items) | Gemini infer + verify F1 0.952, RoBERTa F1 0.966, TF-IDF + LR F1 0.966, rules only F1 0.698 |
| Category accuracy on the same set (macro F1) | Gemini 0.677, RoBERTa 0.624, TF-IDF + LR 0.619, rules 0.301 |
| DarkMart test shop (43 planted patterns) | LLM found 41 of 43 with 1 false alarm on FairMart; offline engine found all 43 but with 9 false alarms |
| AidUI web screenshots (161-162) | LLM F1 0.805, offline engine F1 0.673 |
| EU crawl | 195 shops tried, 108 crawled (1,583 pages, 16 countries), 67 blocked by bot protection |
| Prevalence | at least one dark pattern found on 78 of the 108 crawled shops (72%), before human checking |

The precision and recall on the real crawl are still waiting on the human labels.

On the binary yes/no question the fine-tuned models are about as good as the LLM, but they need a
labelled dataset for training. Where the LLM helps is in naming the right category, reading
screenshots and explaining why something counts.

## Ethics

We only crawl public pages. The crawler follows `robots.txt`, waits between requests, and never buys
anything, signs up, logs in or types in personal details (see `darklens/crawler/safe_interaction.py`
for exactly what it is and isn't allowed to click). When a site shows a bot check (Cloudflare,
captcha, "Access denied") the crawler stops and writes it down as blocked. We don't try to get around
those, so the bigger retailers are under-represented, and we say so in the paper.

The legal references in the app are there as a starting point for someone auditing a site. They
aren't legal advice.

## Folders

```
darklens/crawler/        the crawler: page classifier, link priority, safe clicking, evidence capture
darklens/preprocessing/  turning saved pages into text segments, dataset loaders, rule lexicon
darklens/detection/      LLM client, prompts, the detector, OCR, baseline models
darklens/evaluation/     metrics, kappa, annotation sample and agreement
darklens/pipeline.py     runs detection over a crawl
app/                     FastAPI server and the web interface (plain HTML/JS, no build step)
testbed/                 DarkMart and FairMart plus their ground truth
config/                  the lists of shops we crawled
scripts/                 one script per experiment
results/                 every measured number, as JSON
paper/                   the IEEE paper
legacy/                  our first single-page scripts from the start of the project
```

## References

- A. Mathur et al., "Dark Patterns at Scale: Findings from a Crawl of 11K Shopping Websites," Proc.
  ACM Hum.-Comput. Interact., vol. 3, CSCW, 2019.
- S. M. H. Mansur et al., "AidUI: Toward Automated Recognition of Dark Patterns in User Interfaces,"
  ICSE 2023.
- The full list is in `paper/refs.bib`.
