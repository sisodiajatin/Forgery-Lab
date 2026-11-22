# FORGERY LAB — Pitch Kit

## One line
**We stress-test AI detectors.** AI forgers attack them using real human documents, and you get a report on whether to trust the detector.

## 3-minute demo script

**0:00 — The problem (20s)**
> "AI detectors are already deciding things about people. A student gets a zero, a job applicant gets rejected, an article gets pulled.
> Nobody checks how easily these detectors are fooled on *their* kind of writing. So we built an attacker."

**0:20 — How it works (40s)**
Show the README table, or say it:
> "We start with real human documents written before AI writing tools existed: a science paper, a court opinion and a government report.
> **Reducto** parses them. **Hermes Agent** plans the attack and picks topics the document *doesn't* cover.
> Four AI forgers run on **Modal**, including Hermes-3 on our own GPU. They write fake paragraphs in the author's voice.
> **Pangram** scores every one. When a forgery gets caught, the forger sees the flagged sentences and rewrites, up to three times."

**1:00 — The results (50s)**
Open the live site and scroll the report.
> "112 attacks. Pangram caught **86.6%** on the first try, which is strong. But after rewrites, **33.9%** got through.
> Point at the leaderboard: one forger, GLM Flash, evaded it **82%** of the time. The model we hosted ourselves never got through once.
> Point at the chart: every line is one forgery's AI score, round by round. Watch them fall below the dashed line.
> Point at the document table: government reports were the weakest, with **50%** getting through. The science paper was the strongest, at **12%**.
> It also wrongly flagged **1 real human paragraph out of 30**."

**1:50 — Hand it to the judges (40s)**
> "Your turn. Open `/play` on your phone. These are the exact forgeries that fooled the detector, mixed with real paragraphs. Find them."
Every result feeds the live "Humans vs Detector" banner on the home page.

**2:30 — Why it matters and the verdict (30s)**
> "Hermes Agent turns the numbers into a plain-English verdict: *use with caution*. Treat it as a first filter, never as proof.
> Any school or hiring team can run this on their own documents before trusting a detector. And one more thing: Pangram flagged my own
> cover letter as 100% AI. It was. So it's not useless. You just need to know where it's weak."

## Tool usage (for judges)
| Tool | What it actually does here |
|---|---|
| **Hermes Agent** | Plans the attack (topics not in the document) and writes the verdict from the measured data |
| **Reducto** | Parses messy real PDFs (court opinions, GAO tables) into clean human-written paragraphs |
| **Modal** | Hermes-3 8B on our own L40S GPU with vLLM, plus 3 Model API forgers running in parallel. Also hosts the public web app |
| **Pangram** | The detector under test: scores forgeries and human text, and feeds flagged passages back to the forgers |

## Honesty notes (be ready for these questions)
- **Sample sizes are small.** That's 22–30 attacks per forger, so the percentages are indicative. GLM has 22 valid attacks because Pangram rejected 8 of its texts.
- **Why not famous documents?** Models have memorised them. Our first run on "Attention Is All You Need" looked like a 100% evasion, but the forger was just recalling the paper. So we added topic checks, a verbatim check and a paraphrase check, and we use obscure documents.
- **Is the forger allowed to lie?** Yes, that's the attack. GLM's court "forgeries" invent breath-test results and case citations that aren't in the record.
- **Is this anti-Pangram?** No. It caught 86.6% on the first try with only 3.3% false alarms. The point is knowing where any detector is weak.

## Demo-day checklist
- [ ] 10 min before: open the live site once, so the web app warms up
- [ ] Only for `/try`: warm the GPU with `.venv\Scripts\python -c "import modal;print(modal.Cls.from_name('forgery-lab-forger','Forger')().forge.remote(['x'],['y'],20))"` (~2 min cold start)
- [ ] Have `runs/full/report.html` open locally as a backup if the Wi-Fi fails
- [ ] Clear test plays: `.venv\Scripts\modal volume rm forgery-lab-cases /human.jsonl`
- [ ] Prepare a QR code for the live link so judges can play on their phones
