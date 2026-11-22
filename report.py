"""Forgery Lab — trust report / dashboard generator.

  python report.py runs/full            # -> runs/full/report.html
  python report.py runs/full --no-agent # skip the Hermes Agent written verdict
"""
import argparse, json, sys
from pathlib import Path

import build_case as bc

THRESH = 0.5
DOC_LABELS = {"1709.02445v2": "Science paper", "court_romanko_2014": "Court opinion", "gov_report": "Government report",
              "attention": "Transformer paper"}


def load(run: Path):
    attacks = [json.loads(l) for l in (run / "attacks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    genuine = json.loads((run / "genuine.json").read_text(encoding="utf-8"))
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    return attacks, genuine, summary


def stats(attacks, genuine):
    done = [a for a in attacks if a.get("status") == "done"]
    models = sorted({a["model_label"] for a in done})
    docs = sorted({a["doc"] for a in done})
    def rate(rs, key):
        return round(100 * sum(r[key] for r in rs) / len(rs), 1) if rs else None
    board = []
    for m in models:
        rs = [a for a in done if a["model_label"] == m]
        board.append({"model": m, "n": len(rs), "caught_first": rate(rs, "caught_first"), "evaded": rate(rs, "evaded"),
                      "first": round(sum(r["first_score"] for r in rs) / len(rs), 3),
                      "best": round(sum(r["best_score"] for r in rs) / len(rs), 3),
                      "by_doc": {d: rate([r for r in rs if r["doc"] == d], "evaded") for d in docs}})
    board.sort(key=lambda b: -(b["evaded"] or 0))
    gs = [g for g in genuine if "score" in g]
    overall = {
        "attacks": len(done), "rejected": sum(a.get("status") == "rejected" for a in attacks),
        "errors": sum(a.get("status") == "error" for a in attacks),
        "caught_first": rate(done, "caught_first"), "evaded": rate(done, "evaded"),
        "genuine": len(gs), "false_alarms": sum(g["score"] >= THRESH for g in gs),
        "by_doc": {d: {"evaded": rate([a for a in done if a["doc"] == d], "evaded"),
                       "caught_first": rate([a for a in done if a["doc"] == d], "caught_first"),
                       "false_alarms": sum(g["score"] >= THRESH for g in gs if g["doc"] == d),
                       "genuine": sum(g["doc"] == d for g in gs)} for d in docs},
    }
    overall["false_alarm_pct"] = round(100 * overall["false_alarms"] / len(gs), 1) if gs else None
    return board, overall, docs, done


def verdict(board, overall, docs, use_agent=True):
    facts = json.dumps({"overall": overall, "leaderboard": board,
                        "documents": {d: DOC_LABELS.get(d, d) for d in docs}}, indent=1)
    prompt = f"""You are writing the verdict of an AI-detector stress test for non-technical decision makers
(teachers, hiring managers, editors). Pangram (an AI-text detector) was attacked by several AI forger models that
wrote fake paragraphs in the voice of real human documents, and rewrote them after being caught.
Real human paragraphs were also scored to measure false alarms. Here are the measured results (percentages):
{facts}

Write ONLY JSON: {{"headline": "one punchy sentence", "verdict": "SAFE AS A FIRST FILTER | USE WITH CAUTION | DO NOT RELY ON IT",
"findings": ["3-4 short findings, each citing a number from the data"],
"advice": ["3 short practical rules for people using AI detectors"]}}
Use only numbers that appear in the data, and attribute each number to the exact model/document it belongs to
(check the leaderboard entry before citing it). Don't call a model "weaker" or "stronger" — describe it by its results. Note sample sizes."""
    if use_agent:
        try:
            out = bc.hermes(prompt)
            return json.loads(out[out.find("{"):out.rfind("}") + 1]), "Hermes Agent"
        except Exception as e:
            print("hermes verdict failed:", e, file=sys.stderr)
    return {"headline": f"Plain AI text was caught {overall['caught_first']}% of the time; after rewrites {overall['evaded']}% slipped through.",
            "verdict": "USE WITH CAUTION", "findings": [], "advice": []}, "template"


def html(board, overall, docs, done, genuine, v, v_src, meta):
    data = {"board": board, "overall": overall, "docs": docs, "labels": DOC_LABELS, "verdict": v, "vsrc": v_src, "meta": meta,
            "paths": [{"m": a["model_label"], "d": a["doc"], "s": [r["score"] for r in a["rounds"]]} for a in done],
            "evasions": sorted([{"m": a["model_label"], "d": a["doc"], "topic": a["topic"], "s": [r["score"] for r in a["rounds"]],
                                 "text": a["final_text"]} for a in done if a["evaded"]], key=lambda x: x["s"][0] - x["s"][-1], reverse=True)[:6],
            "false": [g for g in genuine if g.get("score", 0) >= THRESH]}
    tpl = (Path(__file__).parent / "game" / "report_template.html").read_text(encoding="utf-8")
    return tpl.replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--no-agent", action="store_true")
    a = ap.parse_args()
    bc.load_env()
    attacks, genuine, summary = load(a.run)
    board, overall, docs, done = stats(attacks, genuine)
    v, src = verdict(board, overall, docs, not a.no_agent)
    meta = {"seconds": summary.get("seconds"), "rounds": summary.get("rounds"), "run": a.run.name}
    out = a.run / "report.html"
    out.write_text(html(board, overall, docs, done, genuine, v, src, meta), encoding="utf-8")
    (a.run / "verdict.json").write_text(json.dumps({"verdict": v, "source": src, "overall": overall, "board": board}, indent=2), encoding="utf-8")
    print(json.dumps({"overall": overall, "verdict_source": src, "headline": v.get("headline")}, indent=1))
    print("wrote", out)


if __name__ == "__main__":
    main()
