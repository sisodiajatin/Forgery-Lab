"""Forgery Lab — exhaustive false-alarm measurement.

Scores EVERY usable human-written paragraph of each document with Pangram (no sampling), so the false-alarm rate
rests on the whole population of real paragraphs we have, not a handful.

  python genuine_all.py samples/*.pdf --out runs/genuine_all
Writes a run folder (empty attacks) that report.py can pool with attack runs.
"""
import argparse, json, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import build_case as bc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, default=Path("runs/genuine_all"))
    ap.add_argument("--workers", type=int, default=12)
    a = ap.parse_args()
    bc.load_env()
    t0 = time.time()
    items = []
    for pdf in a.pdfs:
        text = bc.parse_reducto(pdf) if bc.os.environ.get("REDUCTO_API_KEY") else bc.parse_local(pdf)
        paras = bc.paragraphs(text)
        items += [(pdf.stem, p) for p in paras]
        bc.log("parse", f"{pdf.stem}: {len(paras)} paragraphs")

    def score(it):
        doc, p = it
        try:
            return {"doc": doc, "score": round(bc.ai_score(bc.pangram(p)), 3), "text": p}
        except Exception as e:
            return {"doc": doc, "error": str(e)[:200], "text": p}

    with ThreadPoolExecutor(a.workers) as ex:
        genuine = list(ex.map(score, items))
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "attacks.jsonl").write_text("", encoding="utf-8")
    (a.out / "genuine.json").write_text(json.dumps(genuine, indent=1), encoding="utf-8")
    (a.out / "summary.json").write_text(json.dumps({"seconds": round(time.time() - t0, 1), "rounds": None,
                                                    "kind": "exhaustive genuine scoring"}), encoding="utf-8")
    ok = [g for g in genuine if "score" in g]
    flagged = [g for g in ok if g["score"] >= 0.5]
    print(f"scored {len(ok)}/{len(genuine)} paragraphs, flagged as AI: {len(flagged)}")
    for d in sorted({g['doc'] for g in ok}):
        gs = [g for g in ok if g["doc"] == d]
        print(f"  {d:22} {sum(g['score'] >= 0.5 for g in gs)}/{len(gs)}")


if __name__ == "__main__":
    main()
