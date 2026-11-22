"""Offline unit tests — no network, no API keys.  Run:  python -m pytest -q"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fl_stats import detag, mean_features, overlap, rate, style_features, unverified_numbers, wilson  # noqa: E402


# ---------------------------------------------------------------- statistics
def test_wilson_known_values():
    lo, hi = wilson(18, 22)
    assert lo == pytest.approx(61.5, abs=0.1) and hi == pytest.approx(92.7, abs=0.1)


def test_wilson_edges():
    assert wilson(0, 0) == (None, None)
    lo, hi = wilson(0, 30)
    assert lo == 0.0 and 10 < hi < 12          # 0/30 is NOT "0% for sure"
    lo, hi = wilson(30, 30)
    assert hi == 100.0 and 88 < lo < 90


def test_rate_carries_counts():
    r = rate(4, 30)
    assert r["k"] == 4 and r["n"] == 30 and r["pct"] == 13.3 and r["lo"] < 13.3 < r["hi"]


# ---------------------------------------------------------------- integrity checks
SOURCE = ("we propose a new simple network architecture the transformer based solely on attention mechanisms "
          "dispensing with recurrence and convolutions entirely experiments on two machine translation tasks")


def test_overlap_flags_copies_and_passes_originals():
    copied = "We propose a new simple network architecture the Transformer based solely on attention mechanisms today."
    fresh = "Our approach trades recurrence for parallel attention, and the savings on modern accelerators are large."
    assert overlap(copied, SOURCE) > 0.5
    assert overlap(fresh, SOURCE) == 0.0


def test_detag_removes_giveaway_markup():
    t = "In <i>State v. Bova</i>, the court<sup>3</sup> held <b>firmly</b>."
    assert detag(t) == "In State v. Bova, the court held firmly."


# ---------------------------------------------------------------- analysis grounding
def test_style_features_measure_burstiness_and_specifics():
    even = "The cat sat on the mat. The dog sat on the rug. The cow sat on the hay."
    bursty = "Stop. The committee reviewed 14 cases in 2013 and found that three had been mishandled badly. Why?"
    fe, fb = style_features(even), style_features(bursty)
    assert fb["sentence_len_sd"] > fe["sentence_len_sd"]
    assert fb["digits_per_100w"] > 0 and fe["digits_per_100w"] == 0
    assert mean_features([even, bursty])["words"] == pytest.approx((fe["words"] + fb["words"]) / 2, abs=0.1)


def test_unverified_numbers_catches_hallucinated_stats():
    facts = "Evaded after rewrites: 38/112 = 33.9% (95% CI 25.8–43.1%)"
    good = ["After rewrites 33.9% evaded (38 of 112)."]
    bad = ["After rewrites 41.2% evaded."]
    assert unverified_numbers(good, facts) == []
    assert unverified_numbers(bad, facts) and unverified_numbers(bad, facts)[0][1] == 41.2
    quoted = ['citations 33.9 vs 25.8; quote: "State v. Cormier, 46 Conn. App. 640"']
    assert unverified_numbers(quoted, facts) == []              # numbers inside quotes are example text, not stats
    assert unverified_numbers(["nearly 34% slipped through"], facts) == []     # whole-number rounding of 33.9 is fine
    assert unverified_numbers(["37% slipped through"], facts)                   # but 37 is not near any measured value


# ---------------------------------------------------------------- report pipeline (pure parts)
def _fake_run(tmp: Path):
    attacks = []
    for i, (m, ev) in enumerate([("A", True), ("A", False), ("B", False), ("B", False)]):
        rounds = [{"score": 1.0, "text": f"draft {i} sentence one. sentence two."}] + ([{"score": 0.1, "text": f"final {i}."}] if ev else [])
        attacks.append({"model": m, "model_label": m, "doc": "d1", "topic": "t", "status": "done", "rounds": rounds,
                        "first_score": 1.0, "best_score": 0.1 if ev else 1.0, "caught_first": True, "evaded": ev,
                        "final_text": rounds[-1]["text"]})
    attacks.append({"model": "B", "model_label": "B", "doc": "d1", "status": "error", "error": "422"})
    genuine = [{"doc": "d1", "score": 0.0, "text": "real one"}, {"doc": "d1", "score": 0.9, "text": "real two"},
               {"doc": "d1", "score": 0.0, "text": "real one"}]          # duplicate on purpose
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "attacks.jsonl").write_text("\n".join(json.dumps(a) for a in attacks), encoding="utf-8")
    (tmp / "genuine.json").write_text(json.dumps(genuine), encoding="utf-8")
    (tmp / "summary.json").write_text(json.dumps({"seconds": 1, "rounds": 3}), encoding="utf-8")


def test_report_stats_dedup_and_counts(tmp_path):
    import report
    _fake_run(tmp_path / "r1")
    attacks, genuine, meta = report.load_many([tmp_path / "r1"])
    assert len(genuine) == 2                                   # duplicate genuine paragraph removed
    board, overall, docs, done = report.stats(attacks, genuine)
    assert overall["attacks"] == 4 and overall["errors"] == 1
    assert overall["evaded"]["k"] == 1 and overall["evaded"]["n"] == 4
    assert overall["false_alarms"]["k"] == 1 and overall["false_alarms"]["n"] == 2
    assert board[0]["model"] == "A"                            # sorted by evasion rate
    assert "1/4 = 25.0%" in report.facts_for_agent(board, overall, docs)


def test_report_renders_without_agent(tmp_path):
    import report
    _fake_run(tmp_path / "r1")
    res = report.build([tmp_path / "r1"], tmp_path / "out", use_agent=False)
    html = (tmp_path / "out" / "report.html").read_text(encoding="utf-8")
    assert "/*__DATA__*/" not in html and '"attacks": 4' in html
    assert res["checks"]["verdict_unverified"] == []


def test_published_run_is_consistent():
    """The committed benchmark must add up: valid + errors + rejected == attempted, and the leaderboard sums to the total."""
    import report
    run = ROOT / "runs" / "big"
    if not run.exists():
        pytest.skip("no published run")
    attacks, genuine, _ = report.load_many([run])
    board, overall, _, _ = report.stats(attacks, genuine)
    assert overall["attacks"] + overall["errors"] + overall["rejected"] == overall["attempted"]
    assert sum(b["n"] for b in board) == overall["attacks"]
    assert sum(b["evaded"]["k"] for b in board) == overall["evaded"]["k"]
