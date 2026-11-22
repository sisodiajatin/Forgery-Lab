"""Forgery Lab — build a playable case from any PDF.

  python build_case.py samples/attention.pdf --fakes 3

Pipeline
  1. Reducto  /upload + /parse  -> clean paragraphs     (fallback: pypdf, clearly labelled)
  2. Hermes Agent (CLI, headless) -> case story + forgery topics
  3. Modal  Hermes-3 on L40S      -> forged paragraphs  (fallback: Hermes Agent writes them)
  4. Pangram /task               -> forensic AI score for every exhibit (fallback: "lab offline")
  5. Writes cases/<slug>.json and a self-contained game/<slug>.html
"""
import argparse, json, os, random, re, subprocess, sys, time, unicodedata
from pathlib import Path

import requests

ROOT = Path(__file__).parent
ENV_FILE = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / ".env"


def load_env():
    """Project .env (D:\\forgery-lab\\.env) wins; Hermes's .env is the fallback."""
    for env_file in (ROOT / ".env", ENV_FILE):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*=\s*(.+)", line)
            if m and not os.environ.get(m.group(1)):
                os.environ[m.group(1)] = m.group(2).strip().strip('"').strip("'")


def log(stage, msg):
    print(f"[{stage:>8}] {msg}", flush=True)


# ---------------------------------------------------------------- 1. parse
def parse_reducto(pdf: Path) -> str:
    key = os.environ["REDUCTO_API_KEY"]
    h = {"Authorization": f"Bearer {key}"}
    with pdf.open("rb") as f:
        up = requests.post("https://platform.reducto.ai/upload", headers=h, files={"file": (pdf.name, f)}, timeout=120)
    up.raise_for_status()
    file_id = up.json()["file_id"]
    r = requests.post("https://platform.reducto.ai/parse", headers=h, json={"input": file_id}, timeout=600)
    r.raise_for_status()
    res = r.json()["result"]
    if res.get("type") == "url":
        res = requests.get(res["url"], timeout=120).json()
    return "\n\n".join(c["content"] for c in res["chunks"])


def parse_local(pdf: Path) -> str:
    from pypdf import PdfReader
    return "\n\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)


def paragraphs(text: str, lo=60, hi=170) -> list[str]:
    import unicodedata
    text = unicodedata.normalize("NFKC", text)        # kill ligatures (a dead giveaway)
    text = re.sub(r"<sup>.*?</sup>", "", text)          # footnote markers from Reducto's HTML-ish output
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)       # other tags (<i>, <b>...) would also be giveaways
    text = re.sub(r"-\n(\w)", r"\1", text)           # de-hyphenate
    blocks = re.split(r"\n\s*\n|(?<=[.!?])\n(?=[A-Z])", text)
    out = []
    for b in blocks:
        b = re.sub(r"\s+", " ", b).strip()
        b = re.sub(r"^#+\s*", "", b)
        n = len(b.split())
        alpha = sum(ch.isalpha() for ch in b) / max(len(b), 1)
        if lo <= n <= hi and alpha > 0.72 and b[-1:] in ".)" and "|" not in b and "http" not in b:
            out.append(b)
    if len(out) < 6 and lo == 60:                       # pypdf gives long blocks; split them
        sents = re.split(r"(?<=[.!?])\s+(?=[A-Z])", re.sub(r"\s+", " ", text))
        buf, out2 = [], []
        for s in sents:
            buf.append(s)
            if len(" ".join(buf).split()) >= 90:
                p = " ".join(buf); buf = []
                if sum(ch.isalpha() for ch in p) / len(p) > 0.72:
                    out2.append(p)
        out = out + out2
    return out


# ---------------------------------------------------------------- 2. Hermes Agent director
def hermes(prompt: str, timeout=300) -> str:
    """Hermes Agent CLI locally; in the cloud (no CLI) fall back to Hermes-3 on Modal."""
    import shutil
    if not shutil.which("hermes") or os.environ.get("FL_LLM") == "modal":
        if os.environ.get("DEEPSEEK_BASE_URL"):           # cloud: fast Modal Model API instead of a cold GPU
            import forgers
            return forgers.forge("DEEPSEEK", "Follow the instructions exactly.", prompt)
        import modal
        return modal.Cls.from_name("forgery-lab-forger", "Forger")().chat.remote([prompt])[0]
    qf = ROOT / ".hermes_prompt.txt"
    qf.write_text(prompt, encoding="utf-8")
    r = subprocess.run(["hermes", "chat", "-Q", "--query-file", str(qf), "--max-turns", "1", "--ignore-rules"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    return re.sub(r"\s*session_id:.*$", "", r.stdout.strip()).strip()


def json_from(s: str):
    m = re.search(r"\{.*\}", s, re.S)
    return json.loads(m.group(0))


def direct_case(title_hint: str, paras: list[str], n_fakes: int, n_total: int) -> dict:
    sample = "\n\n".join(f"[{i}] {p}" for i, p in enumerate(paras[:12]))
    prompt = f"""You are the Case Director of a detective game called FORGERY LAB.
A forger has slipped {n_fakes} AI-written paragraphs into a real document. Below are genuine paragraphs.
Return ONLY JSON, no prose, no code fences:
{{"case_title": "noir-style case name", "document_name": "short real name of the document",
 "briefing": "2-3 sentence hard-boiled detective briefing for the player (there are exactly {n_total} exhibits; do not state any other number)",
 "topics": [{n_fakes + 2} short, specific topics the forger should write about. Each must plausibly belong in THIS document but must NOT be discussed anywhere in it (no restating its methods, results, or definitions) — e.g. a limitation, an anecdote, a related-work aside, a future-work idea, a practical note]}}

Document file: {title_hint}
{sample}"""
    for _ in range(2):
        try:
            d = json_from(hermes(prompt))
            assert len(d["topics"]) >= n_fakes
            return d
        except Exception as e:
            log("hermes", f"retry ({e})")
    return {"case_title": "The Case of the Uninvited Paragraphs", "document_name": title_hint,
            "briefing": "Somebody's been writing in a dead author's voice. Find the forgeries before the lab does.",
            "topics": [f"a further detail of the methods ({i+1})" for i in range(n_fakes)]}


# ---------------------------------------------------------------- 3. forge
def forge_api(context, topics, words):
    """One forgery per topic, rotating across the Modal Model API forgers (fast, no cold start)."""
    import forgers
    from concurrent.futures import ThreadPoolExecutor
    names = [n for n in ("GLMFLASH", "KIMI", "DEEPSEEK") if n in forgers.configured()]
    excerpt = "\n\n".join(context[:5])
    system = ("You are a master literary forger. Write a NEW paragraph that could be slipped into this document unnoticed: "
              "same voice, terminology, rhythm, citation habits. Never copy or paraphrase its sentences. Plain text only. "
              "Output only the paragraph.")
    jobs = [(names[i % len(names)], t) for i, t in enumerate(topics)]
    with ThreadPoolExecutor(len(jobs)) as ex:
        outs = list(ex.map(lambda j: forgers.forge(j[0], system, f"Real paragraphs:\n\n{excerpt}\n\nWrite one new paragraph (~{words} words) about: {j[1]}"), jobs))
    return outs, [forgers.FORGERS[n][0] for n, _ in jobs]


def forge_modal(context, topics, words):
    import modal
    Forger = modal.Cls.from_name("forgery-lab-forger", "Forger")
    return Forger().forge.remote(context, topics, words)


def overlap(fake: str, source: str) -> float:
    """Share of the fake's 8-word sequences that appear verbatim in the source document."""
    w = re.sub(r"\s+", " ", fake.lower()).split()
    grams = [" ".join(w[i:i + 8]) for i in range(len(w) - 7)]
    return sum(g in source for g in grams) / max(len(grams), 1)


def forge_hermes(context, topics, words):
    excerpt = "\n\n".join(context[:5])
    out = []
    for t in topics:
        p = hermes(f"""You are a master literary forger. Study these REAL paragraphs and write ONE new paragraph
(~{words} words) that could be slipped into the same document unnoticed — same voice, terminology, rhythm,
citation style. Topic: {t}.
Rules: write ENTIRELY NEW sentences — never reuse or paraphrase a sentence from the excerpts. Plain text only,
no LaTeX or markdown. Output ONLY the paragraph, nothing else.

{excerpt}""")
        out.append(unicodedata.normalize("NFKC", re.sub(r"\s+", " ", p)).strip().strip('"'))
    return out


# ---------------------------------------------------------------- 4. Pangram
def pangram(text: str) -> dict:
    h = {"x-api-key": os.environ["PANGRAM_API_KEY"], "Content-Type": "application/json"}
    tid = requests.post("https://text.external-api.pangram.com/task", headers=h, json={"text": text}, timeout=60)
    tid.raise_for_status()
    tid = tid.json()["task_id"]
    for _ in range(60):
        r = requests.get(f"https://text.external-api.pangram.com/task/{tid}", headers=h, timeout=60).json()
        if r.get("stage") == "STAGE_SUCCESS":
            out = {k: r.get(k) for k in ("headline", "prediction_short", "fraction_ai", "fraction_ai_assisted", "fraction_human")}
            out["windows"] = [{"start": w.get("start_index"), "end": w.get("end_index"), "label": w.get("label"),
                               "score": w.get("ai_assistance_score")} for w in (r.get("windows") or [])]
            return out
        if r.get("stage") == "STAGE_FAILED":
            raise RuntimeError("pangram task failed")
        time.sleep(2)
    raise TimeoutError("pangram")


def ai_score(lab):
    return (lab or {}).get("fraction_ai", 0) + 0.5 * (lab or {}).get("fraction_ai_assisted", 0)


def evade(text, lab, context, topic, words, rounds):
    """Hard mode: the forger sees the detector's verdict and rewrites until it slips past (or runs out of rounds)."""
    history = [round(ai_score(lab), 2)]
    best, best_lab = text, lab
    for i in range(rounds):
        if ai_score(best_lab) < 0.5:
            break
        flagged = [best[w["start"]:w["end"]] for w in best_lab.get("windows", []) if (w.get("score") or 0) > 0.5][:3]
        new = hermes(f"""A forensic detector flagged your forged paragraph as {round(100*ai_score(best_lab))}% AI-written.
Flagged passages: {json.dumps(flagged)}
Rewrite it to read like the human author of the real paragraphs below: vary sentence length, use the author's
concrete specifics and quirks, avoid smooth generic transitions. Same topic ({topic}), ~{words} words.
Output ONLY the paragraph.

REAL PARAGRAPHS:
{chr(10).join(context[:4])}

YOUR FLAGGED FORGERY:
{best}""")
        new = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", new)).strip().strip('"')
        new_lab = pangram(new)
        history.append(round(ai_score(new_lab), 2))
        log("evade", f"round {i+1}: AI score {history[-2]} -> {history[-1]}")
        if ai_score(new_lab) < ai_score(best_lab):
            best, best_lab = new, new_lab
    return best, best_lab, history


# ---------------------------------------------------------------- main
def build_case(pdf: Path, fakes=3, n_real=6, seed=None, difficulty="normal", rounds=3) -> dict:
    """Whole pipeline. Returns the case dict. Used by the CLI and by the Modal web app."""
    rng = random.Random(seed)
    provenance = {}
    # 1 parse
    if os.environ.get("REDUCTO_API_KEY"):
        try:
            text = parse_reducto(pdf); provenance["parser"] = "Reducto /parse"
        except Exception as e:
            log("reducto", f"FAILED ({e}); falling back to pypdf"); text = parse_local(pdf); provenance["parser"] = "pypdf (Reducto failed)"
    else:
        text = parse_local(pdf); provenance["parser"] = "pypdf (no REDUCTO_API_KEY)"
    paras = paragraphs(text)
    log("parse", f"{provenance['parser']}: {len(paras)} usable paragraphs")
    if len(paras) < n_real:
        raise ValueError(f"Only {len(paras)} prose paragraphs found; need {n_real}. Try a text-heavy PDF.")
    pool = paras[1:] if len(paras) > n_real + 2 else paras
    real = [pool[i] for i in sorted(rng.sample(range(len(pool)), n_real))]
    # 2 direct
    import shutil
    case = direct_case(pdf.stem, paras, fakes, n_real + fakes)
    provenance["director"] = ("Hermes Agent (hermes chat -Q)" if shutil.which("hermes") and os.environ.get("FL_LLM") != "modal"
                              else "DeepSeek V4.1 Flash on Modal" if os.environ.get("DEEPSEEK_BASE_URL") else "Hermes-3 on Modal")
    log("hermes", f"case: {case['case_title']} | topics: {case['topics'][:fakes]}")
    # 3 forge
    words = int(sum(len(p.split()) for p in real) / len(real))
    topics = case["topics"][:fakes]
    forger_names = None
    try:
        if os.environ.get("FL_FORGER") == "api":
            forged, forger_names = forge_api(real, topics, words)
            provenance["forger"] = "Modal Model APIs: " + ", ".join(sorted(set(forger_names)))
        else:
            forged = forge_modal(real, topics, words); provenance["forger"] = "Hermes-3-Llama-3.1-8B on Modal L40S (vLLM)"
    except Exception as e:
        log("modal", f"unavailable ({type(e).__name__}: {str(e)[:120]}); Hermes Agent forges instead")
        forged = forge_hermes(real, topics, words); provenance["forger"] = "Hermes Agent (Modal app not deployed)"
    clean = lambda f: re.sub(r"\\\(|\\\)|\\([a-zA-Z]+)", r"\1", unicodedata.normalize("NFKC", re.sub(r"\s+", " ", f)).strip().strip('"'))
    source = unicodedata.normalize("NFKC", re.sub(r"\s+", " ", text)).lower()
    forged = [clean(f) for f in forged]
    # A forgery that copies the original isn't a forgery: re-forge on spare topics, then drop it.
    spare = list(case["topics"][fakes:])
    kept = []
    who = dict(zip(topics, forger_names or []))
    for f, tp in zip(forged, topics):
        for attempt in range(3):
            ov = overlap(f, source)
            if ov <= 0.10:
                kept.append((f, tp)); break
            log("forge", f"'{tp[:40]}' copies {ov:.0%} of the source; re-forging")
            if spare and attempt >= 1:
                tp = spare.pop(0)
            f = clean(forge_hermes(real, [tp + " (completely original wording; do not restate the document)"], words)[0])
        else:
            log("forge", f"dropped '{tp[:40]}' — still copied {overlap(f, source):.0%}")
    if not kept:
        raise ValueError("Every forgery copied the source; try another document.")
    forged, topics = [k[0] for k in kept], [k[1] for k in kept]
    log("forge", "verbatim overlap: " + ", ".join(f"{overlap(f, source):.0%}" for f in forged))
    log("forge", f"{len(forged)} forgeries via {provenance['forger']}")
    exhibits = [{"text": t, "forged": False} for t in real] + [{"text": t, "forged": True, "topic": (f"{who[tp]} — {tp}" if tp in who else tp)} for t, tp in zip(forged, topics)]
    rng.shuffle(exhibits)
    # 4 forensics (parallel)
    if os.environ.get("PANGRAM_API_KEY"):
        from concurrent.futures import ThreadPoolExecutor
        provenance["lab"] = "Pangram /task"
        def score(ex):
            try:
                return pangram(ex["text"])
            except Exception as e:
                log("pangram", f"failed: {e}"); return None
        with ThreadPoolExecutor(8) as pool_:
            for ex, lab in zip(exhibits, pool_.map(score, exhibits)):
                ex["lab"] = lab
        log("pangram", "scores: " + ", ".join(f"{ai_score(e['lab']):.2f}{'*' if e['forged'] else ''}" for e in exhibits if e.get("lab")))
        if difficulty == "hard":
            todo = [ex for ex in exhibits if ex["forged"] and ex.get("lab")]
            with ThreadPoolExecutor(4) as pool_:
                res = list(pool_.map(lambda ex: evade(ex["text"], ex["lab"], real, ex["topic"], words, rounds), todo))
            for ex, (t, lab, hist) in zip(todo, res):
                ex["text"], ex["lab"], ex["evasion"] = t, lab, hist
            provenance["mode"] = f"HARD: forger vs detector, up to {rounds} rewrite rounds"
    else:
        provenance["lab"] = "offline (no PANGRAM_API_KEY)"
        if difficulty == "hard":
            log("evade", "hard mode needs PANGRAM_API_KEY; building a normal case")
    case.update(exhibits=exhibits, provenance=provenance, source=pdf.name, built=time.strftime("%Y-%m-%d %H:%M"))
    return case


def render(case: dict) -> str:
    tpl = (ROOT / "game" / "template.html").read_text(encoding="utf-8")
    return tpl.replace("/*__CASE__*/null", json.dumps(case).replace("</", "<\\/"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--fakes", type=int, default=3)
    ap.add_argument("--real", type=int, default=6)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--difficulty", choices=["normal", "hard"], default="normal",
                    help="hard: forgeries are rewritten against Pangram until they evade it")
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    load_env()
    try:
        case = build_case(a.pdf, a.fakes, a.real, a.seed, a.difficulty, a.rounds)
    except ValueError as e:
        sys.exit(str(e))
    slug = re.sub(r"\W+", "-", a.pdf.stem.lower()).strip("-")
    (ROOT / "cases").mkdir(exist_ok=True)
    (ROOT / "cases" / f"{slug}.json").write_text(json.dumps(case, indent=2), encoding="utf-8")
    out = ROOT / "game" / f"{slug}.html"
    out.write_text(render(case), encoding="utf-8")
    log("done", f"{out}")


if __name__ == "__main__":
    main()
