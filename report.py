"""Forgery Lab — trust report / dashboard generator.

  python report.py runs/full                       # one run  -> runs/full/report.html
  python report.py runs/full runs/big --out runs/combined   # pooled runs
  python report.py runs/full --no-agent            # skip Hermes Agent (verdict + analysis from templates)

Rigor:
  * every rate carries k/n and a 95% Wilson interval
  * genuine paragraphs are de-duplicated across runs before measuring false alarms
  * Hermes Agent's verdict and analysis are grounded in measured numbers + style features, and every number it
    writes is checked against the data (unverifiable numbers are flagged in the report)
"""
import argparse, json, random, sys
from pathlib import Path

import build_case as bc
from fl_stats import THRESH, detag, mean_features, rate, unverified_numbers

DOC_LABELS = {"1709.02445v2": "Science paper", "court_romanko_2014": "Court opinion", "gov_report": "Government report",
              "speech_2015": "Policy speech", "attention": "Transformer paper"}


def load(run: Path):
    attacks = [json.loads(l) for l in (run / "attacks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    genuine = json.loads((run / "genuine.json").read_text(encoding="utf-8"))
    summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
    return attacks, genuine, summary


def load_many(runs):
    attacks, genuine, seconds, rounds = [], [], 0, set()
    for r in runs:
        a, g, s = load(r)
        for x in a:
            x["run"] = r.name
        attacks += a; genuine += g
        seconds += s.get("seconds") or 0; rounds.add(s.get("rounds"))
    seen, dedup = set(), []
    for g in genuine:                                   # same real paragraph sampled in two runs counts once
        key = detag(g.get("text", ""))[:200]
        if "score" in g and key not in seen:
            seen.add(key); dedup.append(g)
    return attacks, dedup, {"seconds": round(seconds, 1), "rounds": max([r for r in rounds if r] or [0]), "runs": [r.name for r in runs]}


def stats(attacks, genuine):
    done = [a for a in attacks if a.get("status") == "done"]
    models = sorted({a["model_label"] for a in done})
    docs = sorted({a["doc"] for a in done})
    R = lambda rs, key: rate(sum(bool(r[key]) for r in rs), len(rs))
    board = []
    for m in models:
        rs = [a for a in done if a["model_label"] == m]
        board.append({"model": m, "n": len(rs), "caught_first": R(rs, "caught_first"), "evaded": R(rs, "evaded"),
                      "errors": sum(a.get("status") == "error" and a["model_label"] == m for a in attacks),
                      "first": round(sum(r["first_score"] for r in rs) / len(rs), 3),
                      "best": round(sum(r["best_score"] for r in rs) / len(rs), 3),
                      "by_doc": {d: R([r for r in rs if r["doc"] == d], "evaded") for d in docs}})
    board.sort(key=lambda b: -(b["evaded"]["pct"] or 0))
    fa = lambda gs: rate(sum(g["score"] >= THRESH for g in gs), len(gs))
    overall = {
        "attacks": len(done), "attempted": len(attacks),
        "rejected": sum(a.get("status") == "rejected" for a in attacks),
        "errors": sum(a.get("status") == "error" for a in attacks),
        "caught_first": R(done, "caught_first"), "evaded": R(done, "evaded"),
        "false_alarms": fa(genuine),
        "by_doc": {d: {"evaded": R([a for a in done if a["doc"] == d], "evaded"),
                       "caught_first": R([a for a in done if a["doc"] == d], "caught_first"),
                       "false_alarms": fa([g for g in genuine if g["doc"] == d])} for d in docs},
    }
    return board, overall, docs, done


def facts_for_agent(board, overall, docs):
    """Compact, number-exact facts (k/n, %, CI) — what the agent is allowed to cite."""
    f = lambda r: f"{r['k']}/{r['n']} = {r['pct']}% (95% CI {r['lo']}–{r['hi']}%)"
    lines = [f"Valid attacks: {overall['attacks']} (attempted {overall['attempted']}, errors {overall['errors']}, rejected {overall['rejected']})",
             f"Caught on first try: {f(overall['caught_first'])}", f"Evaded after rewrites: {f(overall['evaded'])}",
             f"Genuine human paragraphs wrongly flagged: {f(overall['false_alarms'])}"]
    for b in board:
        lines.append(f"Forger {b['model']}: evaded {f(b['evaded'])}; caught first {f(b['caught_first'])}; "
                     f"avg AI score first {round(b['first']*100)}% -> best {round(b['best']*100)}%")
    for d in docs:
        x = overall["by_doc"][d]
        lines.append(f"Document {DOC_LABELS.get(d, d)}: evaded {f(x['evaded'])}; false alarms {f(x['false_alarms'])}")
    return "\n".join(lines)


def verdict(facts, use_agent=True):
    prompt = f"""You are writing the verdict of an AI-detector stress test for non-technical decision makers
(teachers, hiring managers, editors). Pangram (an AI-text detector) was attacked by several AI forger models that
wrote fake paragraphs in the voice of real human documents, and rewrote them after being caught.
Real human paragraphs were also scored to measure false alarms. Measured results:
{facts}

Write ONLY JSON: {{"headline": "one punchy sentence", "verdict": "SAFE AS A FIRST FILTER | USE WITH CAUTION | DO NOT RELY ON IT",
"findings": ["3-4 short findings, each citing a number exactly as written above"],
"advice": ["3 short practical rules for people using AI detectors"]}}
Copy numbers exactly from the facts; attribute each to the right model/document. Where confidence intervals overlap,
don't claim a difference. Describe models by results, not as "weak"/"strong"."""
    if use_agent:
        try:
            out = bc.hermes(prompt)
            return json.loads(out[out.find("{"):out.rfind("}") + 1]), "Hermes Agent"
        except Exception as e:
            print("hermes verdict failed:", e, file=sys.stderr)
    return {"headline": "See the measured results below.", "verdict": "USE WITH CAUTION", "findings": [], "advice": []}, "template"


def analysis(done, use_agent=True, seed=0):
    """Hermes Agent studies forgeries that fooled the detector vs ones that didn't, grounded in measured style features."""
    ev = [a for a in done if a["evaded"]]
    caught = [a for a in done if not a["evaded"]]
    feats = {"evaded (final text)": mean_features([a["final_text"] for a in ev]),
             "caught (final text)": mean_features([a["final_text"] for a in caught]),
             "evaders' first drafts": mean_features([a["rounds"][0]["text"] for a in ev if a["rounds"]])}
    out = {"features": feats, "n_evaded": len(ev), "n_caught": len(caught), "patterns": [], "summary": ""}
    if not use_agent or not ev or not caught:
        return out, "template"
    rng = random.Random(seed)
    ex = lambda rs, k: [{"model": a["model_label"], "doc": DOC_LABELS.get(a["doc"], a["doc"]),
                         "score_path": [r["score"] for r in a["rounds"]], "text": detag(a["final_text"])[:900]}
                        for a in rng.sample(rs, min(k, len(rs)))]
    prompt = f"""You are analysing an AI-detector stress test. Below are forgeries that EVADED the detector (best AI score < 50%)
and forgeries that were CAUGHT, plus measured average style features for each group.

MEASURED FEATURES (averages): {json.dumps(feats)}
EVADED EXAMPLES: {json.dumps(ex(ev, 6))}
CAUGHT EXAMPLES: {json.dumps(ex(caught, 6))}

What distinguishes forgeries that fooled the detector? Return ONLY JSON:
{{"summary": "2 sentences for a non-technical reader",
  "patterns": [{{"pattern": "short name", "explanation": "1-2 sentences", "evidence": "cite a measured feature value or quote <=12 words from an example"}}]}}
Give 3-4 patterns. Only claim feature differences that the measured numbers actually show. Be honest about uncertainty."""
    try:
        res = bc.hermes(prompt)
        j = json.loads(res[res.find("{"):res.rfind("}") + 1])
        out.update(summary=j.get("summary", ""), patterns=j.get("patterns", [])[:4])
        return out, "Hermes Agent"
    except Exception as e:
        print("hermes analysis failed:", e, file=sys.stderr)
        return out, "template"


def html(board, overall, docs, done, genuine, v, v_src, an, an_src, checks, meta):
    data = {"board": board, "overall": overall, "docs": docs, "labels": DOC_LABELS, "verdict": v, "vsrc": v_src, "meta": meta,
            "analysis": an, "asrc": an_src, "checks": checks,
            "paths": [{"m": a["model_label"], "d": a["doc"], "s": [r["score"] for r in a["rounds"]]} for a in done],
            "evasions": sorted([{"m": a["model_label"], "d": a["doc"], "topic": a["topic"], "s": [r["score"] for r in a["rounds"]],
                                 "text": detag(a["final_text"])} for a in done if a["evaded"]],
                               key=lambda x: x["s"][0] - x["s"][-1], reverse=True)[:6],
            "false": [dict(g, text=detag(g["text"])) for g in genuine if g.get("score", 0) >= THRESH]}
    tpl = (Path(__file__).parent / "game" / "report_template.html").read_text(encoding="utf-8")
    return tpl.replace("/*__DATA__*/null", json.dumps(data).replace("</", "<\\/"))


def build(runs, out_dir: Path, use_agent=True, genuine_run=None):
    attacks, genuine, meta = load_many(runs)
    if genuine_run:                                   # exhaustive, clean false-alarm population replaces sampled genuine sets
        _, genuine, gmeta = load_many([genuine_run])
        meta["genuine_source"] = genuine_run.name
    board, overall, docs, done = stats(attacks, genuine)
    facts = facts_for_agent(board, overall, docs)
    v, vsrc = verdict(facts, use_agent)
    an, asrc = analysis(done, use_agent)
    feats_text = json.dumps(an.get("features", {}))
    checks = {"verdict_unverified": [f"{c} → {x}" for c, x in unverified_numbers(v.get("findings", []) + [v.get("headline", "")], facts)],
              "analysis_unverified": [f"{p.get('evidence','')} → {x}" for p in an.get("patterns", [])
                                      for _, x in unverified_numbers([p.get("evidence", "")], facts + feats_text)]}
    meta["run"] = "+".join(meta["runs"])
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.html").write_text(html(board, overall, docs, done, genuine, v, vsrc, an, asrc, checks, meta), encoding="utf-8")
    (out_dir / "verdict.json").write_text(json.dumps({"verdict": v, "source": vsrc, "analysis": an, "analysis_source": asrc,
                                                      "checks": checks, "overall": overall, "board": board, "facts": facts}, indent=2),
                                          encoding="utf-8")
    return {"facts": facts, "verdict": v, "analysis": an, "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-agent", action="store_true")
    ap.add_argument("--genuine", type=Path, default=None, help="run folder from genuine_all.py to use for false alarms")
    a = ap.parse_args()
    bc.load_env()
    out = a.out or a.runs[0]
    res = build(a.runs, out, not a.no_agent, a.genuine)
    print(res["facts"])
    print("\nVERDICT:", res["verdict"].get("verdict"), "|", res["verdict"].get("headline"))
    print("checks:", json.dumps(res["checks"]))
    print("wrote", out / "report.html")


if __name__ == "__main__":
    main()
