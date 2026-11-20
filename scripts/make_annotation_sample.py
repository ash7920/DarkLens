"""
Create the human-annotation sample from the crawl predictions.

    python scripts/make_annotation_sample.py

About 500 distinct elements: up to 200 the LLM flagged, 200 it cleared and 100 the pre-filter
skipped (see darklens/evaluation/annotation.py).  Then two people label them independently in the
web app (Annotate tab), and:  python scripts/agreement.py --adjudicator <third person>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from darklens.evaluation.annotation import make_sample  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pred", default="data/predictions/segments.jsonl")
ap.add_argument("--flagged", type=int, default=200, help="-1 = every distinct flagged element")
ap.add_argument("--cleared", type=int, default=200)
ap.add_argument("--filtered", type=int, default=100)
a = ap.parse_args()
print(json.dumps(make_sample(a.pred, a.flagged, a.cleared, a.filtered), indent=2))
