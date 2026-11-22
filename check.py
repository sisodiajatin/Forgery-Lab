"""Forgery Lab — live smoke test + integrity-check calibration (uses real APIs; ~1-2 min, a few cents).

  python check.py              # everything: endpoints, live site, upload, paraphrase-judge calibration
  python check.py --quick      # endpoints + live site only (no upload, no calibration)

Exit code 0 only if every check passes. Run it before a demo.
"""
import argparse, json, re, sys, time
from pathlib import Path

import requests

import build_case as bc
import forgers

SITE = "https://jatinsisodiausa--forgery-lab-web.us-east.modal.run"
ROOT = Path(__file__).parent
results = []


def check(name, fn):
    t = time.time()
    try:
        detail = fn()
        results.append((True, name, detail, time.time() - t))
        print(f"  PASS  {name:42} {detail}  ({time.time()-t:.1f}s)")
    except Exception as e:
        results.append((False, name, str(e)[:200], time.time() - t))
        print(f"  FAIL  {name:42} {str(e)[:200]}")


def forger_ok(n):
    def f():
        r = forgers.chat(n, [{"role": "user", "content": "Reply with exactly: forger online"}], max_tokens=400, temperature=0, fast=True)
        assert "online" in r["text"].lower(), r["text"][:60]
        return f"{r['seconds']}s"
    return f


def route(path, must=None):
    def f():
        r = requests.get(SITE + path, timeout=90)
        assert r.status_code == 200, r.status_code
        if must:
            assert must in r.text, f"missing {must!r}"
        return f"{r.status_code}, {len(r.text)//1024} KB"
    return f


def upload():
    pdf = ROOT / "samples" / "court_romanko_2014.pdf"
    t = time.time()
    jid = requests.post(SITE + "/build", files={"pdf": (pdf.name, pdf.read_bytes(), "application/pdf")}, timeout=60).json()["id"]
    while time.time() - t < 180:
        s = requests.get(f"{SITE}/status/{jid}", timeout=30).json()
        if s.get("state") == "done":
            html = requests.get(f"{SITE}/case/{jid}", timeout=60).text
            case = json.loads(re.search(r"const CASE = (\{.*?\});\n", html, re.S).group(1))
            ex = case["exhibits"]
            assert len(ex) == 9 and sum(e["forged"] for e in ex) == 3, f"{len(ex)} exhibits"
            assert all(e.get("lab") for e in ex), "missing Pangram scores"
            assert not any(re.search(r"</?(i|sup|b)>", e["text"]) for e in ex), "markup giveaway in exhibit"
            return f"9 exhibits, 3 forged, all scored, built in {time.time()-t:.0f}s"
        if s.get("state") == "error":
            raise RuntimeError(s.get("msg"))
        time.sleep(1)
    raise TimeoutError("upload took >180s")


def paraphrase_calibration():
    """Known labels: real paragraphs from the document MUST be judged 'restates'; forgeries that a human verified
    to contain only new material MUST NOT be. Reports precision on each side."""
    import attack
    text = bc.parse_local(ROOT / "samples" / "court_romanko_2014.pdf")
    paras = bc.paragraphs(text)
    doc = {"name": "court", "paras": paras}
    positives = paras[2:6]                         # real paragraphs -> restate the source by definition
    negatives = []                                 # forgeries from the published run on this doc that evaded
    for l in (ROOT / "runs" / "full" / "attacks.jsonl").read_text(encoding="utf-8").splitlines():
        a = json.loads(l)
        if a.get("status") == "done" and a["doc"] == "court_romanko_2014":
            negatives.append(a["final_text"])
        if len(negatives) == 4:
            break
    tp = sum(attack.restates_source(doc, p)[0] for p in positives)
    tn = sum(not attack.restates_source(doc, n)[0] for n in negatives)
    assert tp >= 3, f"judge missed real paragraphs: caught {tp}/{len(positives)}"
    return f"flags real text {tp}/{len(positives)}, passes novel forgeries {tn}/{len(negatives)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    bc.load_env()
    print("Forger endpoints"); [check(f"forger {n}", forger_ok(n)) for n in forgers.configured()]
    print("Live site")
    check("GET /  (report + banner)", route("/", "HUMANS vs DETECTOR"))
    check("GET /play", route("/play", "HUMAN ROUND"))
    for d in ("1709.02445v2", "court_romanko_2014", "gov_report", "speech_2015"):
        check(f"GET /play/{d}", route(f"/play/{d}", "const CASE"))
    check("GET /try  (upload button page)", route("/try", "Upload"))
    check("GET /human/stats", lambda: requests.get(SITE + "/human/stats", timeout=60).json())
    if not a.quick:
        print("End-to-end upload"); check("upload PDF -> case board", upload)
        print("Integrity-check calibration"); check("paraphrase judge", paraphrase_calibration)
    ok = sum(r[0] for r in results)
    print(f"\n{ok}/{len(results)} checks passed")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
