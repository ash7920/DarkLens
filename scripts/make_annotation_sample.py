"""
Create the human-annotation sample from pipeline predictions.

    python scripts/make_annotation_sample.py --pred data/predictions/segments.jsonl --states 150

Then each annotator opens the web app → Annotate tab, enters their name, and labels.
Afterwards:  python scripts/agreement.py --adjudicator <third person>
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from darklens.evaluation.annotation import make_sample  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--pred", default="data/predictions/segments.jsonl")
ap.add_argument("--states", type=int, default=150)
ap.add_argument("--neg-share", type=float, default=0.15)
a = ap.parse_args()
print(json.dumps(make_sample(a.pred, a.states, a.neg_share), indent=2))
