# Forgery Lab — a stress test for AI detectors

**Can an AI detector be trusted on *your* kind of documents?**

Schools, hiring teams and publishers already use AI detectors to make real decisions: failing a student, rejecting an
applicant, pulling an article. Almost nobody checks how well the detector works on their own kind of writing.
Forgery Lab does. AI forgers attack the detector with fake paragraphs written in the voice of real human documents,
and they rewrite every time they get caught. The results become a plain-English trust report.

**Live site:** https://jatinsisodiausa--forgery-lab-web.us-east.modal.run

| Page | What it does |
|---|---|
| `/` | The stress-test report: verdict, forger leaderboard, round-by-round chart, what fooled the detector |
| `/play` | The human round: spot the forgeries yourself, then compare your calls with the detector's |
| `/try` | Test your own PDF: three AI forgers plant paragraphs in it, and you get a playable board in about 15 seconds |

## What it solves
A wrong AI-detector verdict can hurt someone either way:
- **A false accusation:** an honest student or applicant is flagged as AI and punished.
- **False confidence:** someone who rewrites AI text slips through, while the institution thinks it's protected.

Forgery Lab measures both risks before you rely on the tool:

| Question | What we measure |
|---|---|
| Will it wrongly accuse honest people? | The false-alarm rate on real human writing |
| Can a determined cheater beat it? | The evasion rate after rewrites |
| Which AI tools get past it? | A forger leaderboard |
| Is it reliable for *our* documents? | Results broken down by document type |
| What does AI text that slips through look like? | An analysis of what fooled the detector |
| Can people spot it themselves? | The human round, comparing people with the detector |

It doesn't decide whether a particular person cheated. It tells you how much weight a detector's verdict deserves.

## Headline results
**427 valid attacks** (440 attempted, 13 errors) on **4 human-written documents** (a science paper, a court opinion,
a government report and a policy speech), by **4 forger models**, each allowed up to 3 rewrites. False alarms were
measured on **every** usable real paragraph (156), not a sample. All intervals are 95% Wilson intervals.

| | Rate | 95% CI |
|---|---|---|
| Caught on the first try | **84.3%** (360/427) | 80.6–87.5% |
| Evaded the detector after rewrites | **32.6%** (139/427) | 28.3–37.1% |
| Real human paragraphs wrongly flagged | **0.0%** (0/156) | 0.0–2.4% |

| Forger | Evaded after rewrites | 95% CI | Avg AI score, first try → best |
|---|---|---|---|
| GLM 5.3 Flash | **70.1%** (68/97) | 60.4–78.3% | 55% → 34% |
| Kimi K3.1 Pro | **47.3%** (52/110) | 38.2–56.5% | 85% → 54% |
| DeepSeek V4.1 Flash 1017 | 14.5% (16/110) | 9.2–22.3% | 93% → 82% |
| Hermes-3 8B (self-hosted on a Modal GPU) | 2.7% (3/110) | 0.9–7.7% | 98% → 94% |

| Document | Evaded | 95% CI | False alarms |
|---|---|---|---|
| Government report | **49.2%** (59/120) | 40.4–58.0% | 0/81 |
| Court opinion | **44.0%** (51/116) | 35.3–53.0% | 0/22 |
| Science paper | 25.4% (29/114) | 18.3–34.1% | 0/33 |
| Policy speech | **0.0%** (0/77) | 0.0–4.8% | 0/20 |

**Main findings:**
- **Pangram never wrongly accused a human.** 0 of 156 real paragraphs were flagged.
- **But it can be beaten by rewriting.** About a third of forgeries got through after up to 3 rewrites. How often depends heavily on the forger model, and the differences between forgers are statistically clear (the intervals don't overlap).
- **The document type matters too.** The detector was weakest on dense institutional prose (government and legal writing). On the policy speech it caught everything, including all 227 rewrite attempts.
- **What fooled it:** Hermes Agent compared the forgeries that got through with the ones that were caught, using style features measured by code. The ones that got through were shorter and had more numbers and citations, and their sentence lengths varied more.

**Verdict: use with caution.** Pangram is a strong first filter and fair to humans, but it isn't proof on its own.

## How an attack works
One **attack** is one forgery's full journey through the loop:
1. A forger writes a paragraph in the document's voice, on a topic Hermes Agent picked that the document doesn't cover.
2. Pangram scores it. **50% AI or more counts as caught.**
3. If caught, the forger is shown **the exact sentences Pangram flagged** and rewrites the paragraph, up to 3 times.
4. If any version scores **under 50%**, the forgery **evaded** the detector.

**Where the 427 come from:** three benchmark batches (`runs/full`, `runs/big`, `runs/speech`) across 4 documents and
4 forgers. 440 attacks were attempted, and 13 failed on technical errors such as empty model replies or API errors.
Forgeries that copied or paraphrased the source were rejected and replaced, so they aren't in the count.

| Forger | Attacks | | Document | Attacks |
|---|---|---|---|---|
| GLM 5.3 Flash | 97 | | Science paper | 114 |
| Kimi K3.1 Pro | 110 | | Court opinion | 116 |
| DeepSeek V4.1 Flash | 110 | | Government report | 120 |
| Hermes-3 8B | 110 | | Policy speech | 77 |

The 156 real paragraphs used to measure false alarms are separate: every usable human paragraph from the 4 documents.

## The human round
Each board on `/play` shows **9 paragraphs, labelled Exhibit A to I**:
- **6 are real paragraphs** taken word for word from the original document.
- **3 are AI forgeries**, chosen from the hardest ones in the benchmark, mostly forgeries that already fooled Pangram.

The exhibits are shuffled, so the letter means nothing. You mark the 3 you suspect and press **Reveal and score**.
Each exhibit then shows:
- whether it was forged or genuine, and whether you called it right
- Pangram's AI score
- for forgeries, which model wrote it and how its AI score fell with each rewrite

Your score is compared with Pangram's on the same 9 exhibits and added to a live "humans vs the detector" count in the report.

## What happens when you upload a PDF (`/try`)
Building a board takes about 17 seconds:
1. **Upload:** any text PDF a person wrote, up to 25 MB.
2. **Parse:** Reducto splits it into clean paragraphs and drops figures, captions and tables.
3. **Plan:** Hermes Agent picks 3 topics that fit the document but aren't in it.
4. **Forge:** three different AI forgers each write one paragraph in the author's voice. Copies are rejected.
5. **Score:** Pangram scores all 9 exhibits (6 real, 3 forged), which are shuffled as A to I into a playable board.

On reveal, the sentences Pangram found most AI-like are highlighted in red.

Uploads use fast forgeries with no rewrite rounds, so Pangram catches them more easily than the benchmark forgeries.
Use documents written before 2022. A recent paper may contain AI-polished "real" paragraphs, which then show up as
false alarms. In our tests, a 2022 paper scored 9/9 for Pangram, and a 2026 paper scored 6/9.

## How it works
| Stage | Tool | Role |
|---|---|---|
| Read | **Reducto** | Parses real human PDFs into clean paragraphs (pypdf fallback) |
| Plan | **Hermes Agent** | Picks topics that fit the document but aren't in it. Analyses what fooled the detector and writes the verdict |
| Judge | DeepSeek V4.1 Flash | Rejects topics the document already covers, and forgeries that paraphrase the source |
| Attack | **Modal** | Hermes-3 8B on our own L40S GPU (vLLM), plus Kimi K3.1 Pro, GLM 5.3 Flash and DeepSeek V4.1 Flash on Modal Model APIs, attacking in parallel. Modal also hosts the web app |
| Detect | **Pangram** | Scores every forgery and every real paragraph. A caught forgery gets the flagged passages back and is rewritten |
| Play | Case-board game | The forgeries that fooled the detector, mixed with real paragraphs, so people can take the same test |

## Integrity checks
- **Copying:** forgeries that copy more than 10% of the source verbatim (8-word sequences) are discarded.
- **Paraphrasing:** forgeries a judge model finds restating the source are discarded too. The judge is calibrated: it flags 4 of 4 real paragraphs and passes 4 of 4 genuinely new forgeries.
- **Topics:** topics the document already covers are thrown out before any forging.
- **False alarms:** every usable real paragraph is scored, with duplicates removed across runs.
- **Agent output is fact-checked by code:** every number Hermes Agent writes is matched against the measured data, and anything unmatched is flagged in the report.
- **The famous-document trap:** models have memorised famous papers like "Attention Is All You Need", so forgeries of them are recall rather than forgery. Use obscure documents written before 2022.
- **The figure-caption trap:** Reducto's `summarize_figures` option is on by default and inserts **AI-written figure descriptions** into the parsed text. In our first runs these were counted as "human" paragraphs, so Pangram's correct flags on them looked like false alarms (3/58). We now turn the option off, drop figure blocks and keep a regression test for it. If you build human-vs-AI datasets from parsed PDFs, check for this.

## Web app architecture (Modal)
- **Web servers:** 1 always-warm container that scales out to 10 under load, so there are no cold starts. Each container handles up to 50 requests at once.
- **Published pages:** the report and the boards are loaded into memory when a container starts. `publish.py` redeploys, so updates appear immediately.
- **Upload limits:** 5 boards per visitor per hour and 200 per day in total, which protects the API credits behind uploads.
- **Uploads:** each upload runs in **its own container** (`build_job`, up to 30 at once), so uploads never slow the site or each other down.
- **Shared state:** upload progress, uploaded boards and human-round results live in a shared `modal.Dict` (`forgery-lab-state`), so every container sees the same data.
- **Load test on the live site:** 200 page requests, 40 at a time, all succeeded with a median of 0.5s and a maximum of 1.1s. Three uploads at the same time each finished in 17–19 seconds.
- **To pause costs completely:** set `min_containers=0` in `modal_app.py` and redeploy. The URL stays the same, but the first visit after a quiet period takes about 20–30 seconds.

## Testing
- `python -m pytest -q tests`: 12 offline tests covering the statistics, the integrity checks, the number fact-checker, report consistency and the figure-caption regression. They run in GitHub Actions on every push.
- `python check.py`: 13 live checks covering every forger endpoint, every page of the site, a real PDF upload and the paraphrase-judge calibration.

## Run it
```bash
uv venv .venv -p 3.13 && uv pip install -p .venv modal pypdf requests pytest
cp .env.example .env            # fill in Reducto, Pangram and the Modal Model API endpoints
.venv/Scripts/modal token new
.venv/Scripts/modal secret create forgery-lab-keys REDUCTO_API_KEY=... PANGRAM_API_KEY=...
.venv/Scripts/modal deploy modal_forger.py                      # Hermes-3 GPU forger
python forgers.py                                               # smoke-test every forger endpoint
python attack.py samples/*.pdf --per-model 10 --rounds 3 --genuine 10 --out runs/full
python genuine_all.py samples/*.pdf --out runs/genuine_all     # score EVERY real paragraph (false alarms)
python report.py runs/full runs/big runs/speech --genuine runs/genuine_all --out runs/combined
python case_from_run.py runs/full runs/big runs/speech --genuine runs/genuine_all --out runs/combined
python publish.py runs/combined                                 # upload + deploy the public site
python -m pytest -q tests                                       # offline tests (also run in CI)
python check.py                                                 # live smoke test + judge calibration
python reset_counter.py                                         # clear the live humans-vs-detector count before a demo
```

## Files
- `attack.py`: the parallel attack runner (forge → integrity checks → Pangram → rewrite loop)
- `forgers.py`: OpenAI-compatible client for Modal Model APIs
- `modal_forger.py`: Hermes-3 8B on a Modal GPU (vLLM)
- `genuine_all.py`: scores every real paragraph to measure false alarms
- `report.py` + `game/report_template.html`: the trust-report dashboard
- `case_from_run.py` + `game/template.html`: the human-round case boards
- `modal_app.py` + `publish.py`: the public web app on Modal (autoscaling web containers, one container per upload, live progress)
- `reset_counter.py`: clears the live humans-vs-detector results
- `fl_stats.py`: Wilson intervals, integrity checks, style features and the number fact-checker (pure, tested)
- `build_case.py`: the single-PDF pipeline (Reducto parse, Hermes director, Pangram) behind `/try`
- `tests/` + `check.py`: offline tests and the live smoke test

## Sources and credits
**Sample documents** (all public, written by people before 2018):
- Wu, Wang & Evans (2017), arXiv:1709.02445
- *State v. Romanko* (Connecticut, 2014)
- GAO-14-344 (2014)
- Lael Brainard, "The Federal Reserve's Financial Stability Agenda" (December 2014)

**Design:** the site's design pass used [unslop](https://github.com/heydamir/unslop) by Damir Sokolovsky
([@heydamir](https://x.com/heydamir)), CC BY 4.0.

**Built with:** Hermes Agent (Nous Research), Reducto, Pangram and Modal.
