"""Forgery Lab — the attack runner (detector stress test).

Every forger model attacks the same genuine documents. Each attack:
  1. forger writes a paragraph in the author's voice on a topic the document does NOT cover
  2. reject it if it copies the source (>10% verbatim 8-word sequences)
  3. Pangram scores it
  4. if caught (AI score >= 0.5) the SAME forger sees the flagged spans and rewrites, up to R rounds
Genuine paragraphs are also scored, to measure false alarms.

  python attack.py samples/attention.pdf --per-model 3 --rounds 2          # small test
  python attack.py samples/*.pdf --per-model 10 --rounds 3 --out runs/full  # benchmark
"""
import argparse, json, random, re, time, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import build_case as bc
import forgers

SYSTEM = ("You are a master literary forger. You write a NEW paragraph that could be slipped into a real document "
          "unnoticed: same voice, terminology, sentence rhythm, citation habits and length. Never copy or paraphrase "
          "its sentences. Plain text only, no markdown or LaTeX. Output only the paragraph.")
THRESH = 0.5


def clean(t):
    t = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", t)).strip().strip('"')
    return re.sub(r"\\\(|\\\)|\\([a-zA-Z]+)", r"\1", t)


def call_forger(model, prompt):
    if model == "HERMES3":
        import modal
        F = modal.Cls.from_name("forgery-lab-forger", "Forger")
        return F().chat.remote([SYSTEM + "\n\n" + prompt], 600)[0]
    return forgers.forge(model, SYSTEM, prompt)


def label(model):
    return "Hermes-3 8B (own Modal GPU)" if model == "HERMES3" else forgers.FORGERS[model][0]


def attack(model, doc, context, topic, words, rounds):
    rec = {"model": model, "model_label": label(model), "doc": doc["name"], "topic": topic, "rounds": [], "t0": time.time()}
    base = (f"Real paragraphs from the document:\n\n" + "\n\n".join(context) +
            f"\n\nWrite one new paragraph (~{words} words) for this document about: {topic}")
    text = clean(call_forger(model, base))
    ov = bc.overlap(text, doc["source"])
    if ov > 0.10:
        text = clean(call_forger(model, base + "\nUse entirely original wording."))
        ov = bc.overlap(text, doc["source"])
    if len(text.split()) < 30:
        text = clean(call_forger(model, base))
        ov = bc.overlap(text, doc["source"])
    rec["overlap"] = round(ov, 3)
    if ov <= 0.10 and len(text.split()) >= 30:
        same, why = restates_source(doc, text)
        if same:
            text = clean(call_forger(model, base + "\nWrite genuinely NEW material; do not restate anything the document says."))
            ov = bc.overlap(text, doc["source"])
            same, why = restates_source(doc, text)
        if same:
            rec.update(status="rejected", reason=f"paraphrases source: {why}", text=text)
            return rec
    if ov > 0.10 or len(text.split()) < 30:
        rec.update(status="rejected", reason=f"overlap {ov:.0%}" if ov > 0.10 else "too short", text=text)
        return rec
    try:
        lab = bc.pangram(text)
    except Exception as e:                       # e.g. Pangram 422 on odd output: re-forge once, then give up cleanly
        bc.log("pangram", f"{model}: {str(e)[:60]} — re-forging once")
        text = clean(call_forger(model, base + "\nWrite plain prose sentences only."))
        rec["retried"] = True
        try:
            lab = bc.pangram(text)
        except Exception as e2:
            rec.update(status="error", error=str(e2)[:300], text=text, words=len(text.split()))
            return rec
    rec["rounds"].append({"score": round(bc.ai_score(lab), 3), "text": text, "headline": lab.get("headline")})
    for _ in range(rounds):
        if bc.ai_score(lab) < THRESH:
            break
        flagged = [text[w["start"]:w["end"]] for w in lab.get("windows", []) if (w.get("score") or 0) > THRESH][:3]
        new = clean(call_forger(model, base + f"\n\nYour previous attempt was flagged by an AI detector as "
                    f"{round(100*bc.ai_score(lab))}% AI. Flagged passages: {json.dumps(flagged)}\n"
                    f"Previous attempt:\n{text}\n\nRewrite it so it reads like the human author: vary sentence length, "
                    f"use concrete specifics and the author's quirks, avoid smooth generic transitions."))
        if len(new.split()) < 30 or bc.overlap(new, doc["source"]) > 0.10 or restates_source(doc, new)[0]:
            continue
        try:
            nl = bc.pangram(new)
        except Exception as e:
            bc.log("pangram", f"rewrite skipped: {str(e)[:80]}"); continue
        rec["rounds"].append({"score": round(bc.ai_score(nl), 3), "text": new, "headline": nl.get("headline")})
        if bc.ai_score(nl) < bc.ai_score(lab):
            text, lab = new, nl
    first, best = rec["rounds"][0]["score"], min(r["score"] for r in rec["rounds"])
    rec.update(status="done", first_score=first, best_score=best, caught_first=first >= THRESH,
               evaded=best < THRESH, final_text=text, seconds=round(time.time() - rec.pop("t0"), 1))
    return rec


def load_doc(pdf: Path, n_ctx, n_genuine, rng):
    text = bc.parse_reducto(pdf) if bc.os.environ.get("REDUCTO_API_KEY") else bc.parse_local(pdf)
    paras = bc.paragraphs(text)
    source = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", text)).lower()
    picks = rng.sample(paras, min(len(paras), n_ctx + n_genuine))
    return {"name": pdf.stem, "source": source, "paras": paras, "context": picks[:n_ctx], "genuine": picks[n_ctx:]}


JUDGE = "DEEPSEEK"


def judge_json(prompt):
    out = forgers.forge(JUDGE, "You are a careful fact-checker. Return ONLY JSON.", prompt)
    return json.loads(re.search(r"[\[{].*[\]}]", out, re.S).group(0))


def doc_text(doc, limit=60000):
    return "\n\n".join(doc["paras"])[:limit]


def novel_topics(doc, candidates, n):
    """Keep only topics the document does NOT already discuss (judged against the full text)."""
    verdict = judge_json(f"DOCUMENT:\n{doc_text(doc)}\n\nCANDIDATE TOPICS:\n" +
                         "\n".join(f"{i}. {t}" for i, t in enumerate(candidates)) +
                         "\n\nFor each candidate, is it already discussed in the document (even briefly)? "
                         'Return JSON: {"covered": [indexes of topics the document already discusses]}')
    covered = set(verdict.get("covered", []))
    keep = [t for i, t in enumerate(candidates) if i not in covered]
    bc.log("topics", f"{doc['name']}: rejected {len(covered)} already-covered topics, kept {len(keep)}")
    return keep[:n]


def restates_source(doc, text):
    """Meaning-level check: does the forgery restate facts/claims that are actually in the document?"""
    v = judge_json(f"DOCUMENT:\n{doc_text(doc)}\n\nCANDIDATE PARAGRAPH:\n{text}\n\n"
                   "Is the candidate mostly a restatement or paraphrase of specific content in the document "
                   "(its particular findings, facts, tables, examples) rather than new material? "
                   'Return JSON: {"restates": true|false, "reason": "short"}')
    return bool(v.get("restates")), v.get("reason", "")


def topics_for(doc, n):
    prompt = (f"Here are paragraphs from a document:\n\n" + "\n\n".join(doc["paras"][:10]) +
              f"\n\nList {n} short, specific topics that would plausibly belong in THIS document but are NOT discussed "
              f"anywhere in it (a limitation, an aside, a practical note, a related-work remark, a future idea). "
              f"Return ONLY a JSON list of strings.")
    try:
        out = bc.hermes(prompt)
        lst = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
        return [str(t) for t in lst][:n]
    except Exception:
        out = forgers.forge("DEEPSEEK", "Return only JSON.", prompt)
        return json.loads(re.search(r"\[.*\]", out, re.S).group(0))[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdfs", nargs="+", type=Path)
    ap.add_argument("--models", default="DEEPSEEK,GLMFLASH,KIMI,HERMES3")
    ap.add_argument("--per-model", type=int, default=3, help="attacks per model per document")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--genuine", type=int, default=4, help="genuine paragraphs per doc scored for false alarms")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", type=Path, default=Path("runs/latest"))
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    bc.load_env()
    rng = random.Random(a.seed)
    models = [m.strip() for m in a.models.split(",") if m.strip()]
    a.out.mkdir(parents=True, exist_ok=True)
    log = (a.out / "attacks.jsonl").open("w", encoding="utf-8")
    t_start = time.time()

    docs = []
    for pdf in a.pdfs:
        d = load_doc(pdf, 4, a.genuine, rng)
        d["topics"] = novel_topics(d, topics_for(d, a.per_model * 2 + 2), a.per_model)
        bc.log("doc", f"{d['name']}: {len(d['paras'])} paragraphs, topics={d['topics']}")
        docs.append(d)

    jobs = [(m, d, t) for d in docs for m in models for t in d["topics"][:a.per_model]]
    bc.log("attack", f"{len(jobs)} attacks across {len(models)} forgers x {len(docs)} docs, up to {a.rounds} rewrite rounds")
    results = []
    with ThreadPoolExecutor(a.workers) as ex:
        futs = {}
        for m, d, t in jobs:
            words = int(sum(len(p.split()) for p in d["context"]) / len(d["context"]))
            futs[ex.submit(attack, m, d, d["context"], t, words, a.rounds)] = (m, d["name"])
        gen_futs = {ex.submit(bc.pangram, g): (d["name"], g) for d in docs for g in d["genuine"]}
        for f in as_completed(futs):
            m, dn = futs[f]
            try:
                r = f.result()
            except Exception as e:
                r = {"model": m, "model_label": label(m), "doc": dn, "status": "error", "error": str(e)[:300]}
            results.append(r); log.write(json.dumps(r) + "\n"); log.flush()
            path = " -> ".join(str(x["score"]) for x in r.get("rounds", []))
            bc.log(m.lower()[:8], f"{r['status']:8} {path or r.get('reason') or r.get('error','')[:80]}")
        genuine = []
        for f in as_completed(gen_futs):
            dn, g = gen_futs[f]
            try:
                genuine.append({"doc": dn, "score": round(bc.ai_score(f.result()), 3), "text": g})
            except Exception as e:
                genuine.append({"doc": dn, "error": str(e)[:200]})

    (a.out / "genuine.json").write_text(json.dumps(genuine, indent=2), encoding="utf-8")
    summary = summarize(results, genuine, models)
    summary.update(seconds=round(time.time() - t_start, 1), rounds=a.rounds, docs=[d["name"] for d in docs])
    (a.out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def summarize(results, genuine, models):
    board = []
    for m in models:
        rs = [r for r in results if r["model"] == m and r.get("status") == "done"]
        n = len(rs)
        board.append({
            "model": m, "label": label(m), "attacks": n,
            "rejected": sum(1 for r in results if r["model"] == m and r.get("status") == "rejected"),
            "errors": sum(1 for r in results if r["model"] == m and r.get("status") == "error"),
            "caught_first_pct": round(100 * sum(r["caught_first"] for r in rs) / n, 1) if n else None,
            "evaded_after_rewrites_pct": round(100 * sum(r["evaded"] for r in rs) / n, 1) if n else None,
            "avg_first_score": round(sum(r["first_score"] for r in rs) / n, 3) if n else None,
            "avg_best_score": round(sum(r["best_score"] for r in rs) / n, 3) if n else None,
        })
    gs = [g for g in genuine if "score" in g]
    fa = sum(g["score"] >= THRESH for g in gs)
    return {"leaderboard": board, "genuine_scored": len(gs), "false_alarms": fa,
            "false_alarm_pct": round(100 * fa / len(gs), 1) if gs else None}


if __name__ == "__main__":
    main()
