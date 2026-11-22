"""Forgery Lab — human round. Turns a benchmark run into playable case boards.

Each board mixes real paragraphs with the run's forgeries for one document — preferring the ones that fooled
Pangram — so players face exactly what the detector faced.

  python case_from_run.py runs/full            # -> runs/full/human_<doc>.html
"""
import argparse, json, random, sys
from pathlib import Path

import build_case as bc
from report import DOC_LABELS, load


def lab(score):
    return {"headline": "AI Detected" if score >= 0.5 else "Human Written", "fraction_ai": score,
            "fraction_ai_assisted": 0.0, "fraction_human": 1 - score, "windows": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--fakes", type=int, default=3)
    ap.add_argument("--real", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    attacks, genuine, _ = load(a.run)
    done = [x for x in attacks if x.get("status") == "done"]
    for doc in sorted({x["doc"] for x in done}):
        fs = [x for x in done if x["doc"] == doc]
        # hardest first: forgeries that evaded, then lowest best score; one per model where possible
        fs.sort(key=lambda x: (not x["evaded"], x["best_score"]))
        picked, seen = [], set()
        for x in fs:
            if x["model_label"] not in seen:
                picked.append(x); seen.add(x["model_label"])
            if len(picked) == a.fakes: break
        for x in fs:
            if len(picked) >= a.fakes: break
            if x not in picked: picked.append(x)
        reals = [g for g in genuine if g["doc"] == doc and "score" in g]
        reals = rng.sample(reals, min(a.real, len(reals)))
        if len(reals) < 3 or not picked:
            print("skip", doc); continue
        exhibits = ([{"text": g["text"], "forged": False, "lab": lab(g["score"])} for g in reals] +
                    [{"text": bc.re.sub(r"</?[a-zA-Z][^>]*>", "", x["final_text"]), "forged": True, "lab": lab(x["best_score"]),
                      "topic": f"{x['model_label']} — {x['topic']}", "evasion": [r["score"] for r in x["rounds"]]} for x in picked])
        rng.shuffle(exhibits)
        name = DOC_LABELS.get(doc, doc)
        case = {"case_title": f"The {name} Job", "document_name": name,
                "briefing": f"These paragraphs come from a real {name.lower()}, written by people years before AI writing tools. "
                            f"{len(picked)} of them were planted by AI forgers who rewrote their work until a professional detector "
                            f"stopped catching them. The detector got fooled. Will you?",
                "exhibits": exhibits, "source": doc, "built": bc.time.strftime("%Y-%m-%d %H:%M"),
                "provenance": {"parser": "Reducto", "director": "Hermes Agent", "forger": ", ".join(sorted(seen)),
                               "lab": "Pangram (best score after rewrites)", "mode": f"human round from benchmark '{a.run.name}'"}}
        out = a.run / f"human_{doc}.html"
        out.write_text(bc.render(case), encoding="utf-8")
        print("wrote", out, "| forgeries evaded:", sum(x["evaded"] for x in picked), "/", len(picked))


if __name__ == "__main__":
    main()
