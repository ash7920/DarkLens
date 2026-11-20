"""
Inter-annotator agreement + gold-label construction.

    python scripts/agreement.py                       # first two annotators
    python scripts/agreement.py --adjudicator dhruv   # after the third person resolves disagreements
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from darklens.evaluation.annotation import agreement  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--annotators", nargs=2, default=None)
ap.add_argument("--adjudicator", default=None)
a = ap.parse_args()
res = agreement(a.annotators, a.adjudicator)
Path("results").mkdir(exist_ok=True)
Path("results/human_agreement.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
print(json.dumps(res, indent=2))
