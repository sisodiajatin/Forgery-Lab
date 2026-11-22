# FORGERY LAB 🕵️ — a stress test for AI detectors

**Can an AI detector be trusted on *your* kind of documents?**
Schools, hiring teams and publishers make real decisions with AI detectors: failing a student, rejecting an
applicant, pulling an article. Forgery Lab finds out how well a detector holds up. AI forgers attack it using
real human documents, rewrite their fakes when they get caught, and the results go into a plain-English trust report.

**Live demo:** https://jatinsisodiausa--forgery-lab-web.us-east.modal.run
(report · `/play` human round · `/try` your own PDF)

## Headline results (`runs/combined` = `runs/full` + `runs/big`)
**350 valid attacks** (360 attempted, 10 errors) · 3 human-written documents (science paper, court opinion, government report) ·
4 forger models · up to 3 rewrite rounds · 58 distinct real paragraphs for false alarms. All intervals are 95% Wilson intervals.

| | Rate | 95% CI |
|---|---|---|
| Caught on the first try | **80.9%** (283/350) | 76.4–84.6% |
| Evaded the detector after rewrites | **39.7%** (139/350) | 34.7–44.9% |
| Real human paragraphs wrongly flagged | **5.2%** (3/58) | 1.8–14.1% |

| Forger | Evaded after rewrites | 95% CI | Avg AI score, first → best |
|---|---|---|---|
| GLM 5.3 Flash | **85.0%** (68/80) | 75.6–91.2% | 46% → 20% |
| Kimi K3.1 Pro | **57.8%** (52/90) | 47.5–67.5% | 81% → 43% |
| DeepSeek V4.1 Flash 1017 | 17.8% (16/90) | 11.2–26.9% | 91% → 77% |
| Hermes-3 8B (self-hosted on Modal GPU) | 3.3% (3/90) | 1.1–9.3% | 98% → 92% |

Evasion by document: science paper 25.4% (29/114), court opinion 44.0% (51/116), government report 49.2% (59/120).
The forger differences are statistically clear: the intervals don't overlap. The differences between documents in false
alarms are **not** (3/27, 0/18 and 0/13 overlap).

**What fooled the detector:** this is Hermes Agent's analysis, grounded in style features measured by code.
Forgeries that evaded were shorter (97.8 vs 120.9 words), had more numbers (4.8 vs 2.5 per 100 words) and more
citations (1.3 vs 0.5 per 100 words), and had more varied sentence length (sd 8.9 vs 7.5). Caught forgeries used
flourishes like "we delved into".

## How it works
| Stage | Tool | Role |
|---|---|---|
| Read | **Reducto** | Parses real human PDFs into clean paragraphs (pypdf fallback) |
| Plan | **Hermes Agent** | Proposes topics that fit the document but aren't in it. Writes the final verdict from the measured numbers |
| Judge | DeepSeek V4.1 Flash | Rejects topics the document already covers. Rejects forgeries that paraphrase the source |
| Attack | **Modal** | Hermes-3 8B on our own L40S GPU (vLLM), plus Kimi K3.1 Pro, GLM 5.3 Flash and DeepSeek V4.1 Flash on Modal Model APIs, all attacking in parallel |
| Detect | **Pangram** | Scores every forgery and every genuine paragraph. Caught forgeries get the flagged passages back and rewrite |
| Play | Case-board game | The forgeries that fooled the detector, mixed with real paragraphs, so humans can take on the same test |

**Integrity checks (validated by `check.py`):**
- **Copying:** forgeries that copy more than 10% of the source verbatim (8-word sequences) are discarded.
- **Paraphrasing:** forgeries a judge model finds restating the source are discarded too.
- **Topics:** topics the document already covers are thrown out before any forging.
- **Human baseline:** genuine paragraphs are scored as well, to measure false alarms, with duplicates removed across runs.
- **Calibrated paraphrase judge:** it flags 4/4 real paragraphs as restating the source and passes 4/4 novel forgeries.
- **Agent output is fact-checked by code:** every number Hermes Agent writes in the verdict and analysis is matched against
  the measured data, and anything unmatched is flagged in the report.
- **Famous-document trap:** we learned this the hard way. Models have memorised famous papers ("Attention Is All You Need"), so forgeries of them are recall rather than forgery. Use obscure documents written before 2022.

## Run it
```bash
uv venv .venv -p 3.13 && uv pip install -p .venv modal pypdf requests
cp .env.example .env            # fill in Reducto, Pangram and the Modal Model API endpoints
.venv/Scripts/modal token new
.venv/Scripts/modal secret create forgery-lab-keys REDUCTO_API_KEY=... PANGRAM_API_KEY=...
.venv/Scripts/modal deploy modal_forger.py                      # Hermes-3 GPU forger
python forgers.py                                               # smoke-test every forger endpoint
python attack.py samples/*.pdf --per-model 10 --rounds 3 --genuine 10 --out runs/full
python report.py runs/full                                      # -> runs/full/report.html (Hermes Agent verdict)
python case_from_run.py runs/full                               # -> human-round boards
python report.py runs/full runs/big --out runs/combined        # pool runs, with CIs
python case_from_run.py runs/full runs/big --out runs/combined
python publish.py runs/combined                                 # upload + deploy the public site
python -m pytest -q tests                                       # offline tests (also run in CI)
python check.py                                                 # live smoke test + judge calibration
```

## Files
- `attack.py`: the parallel attack runner (forge → integrity checks → Pangram → rewrite loop)
- `forgers.py`: OpenAI-compatible client for Modal Model APIs
- `modal_forger.py`: Hermes-3 8B on a Modal GPU (vLLM)
- `report.py` + `game/report_template.html`: the trust-report dashboard
- `case_from_run.py` + `game/template.html`: the human-round case boards
- `modal_app.py` + `publish.py`: the public web app on Modal
- `fl_stats.py`: Wilson intervals, integrity checks, style features, number fact-checker (pure, tested)
- `tests/test_offline.py` + `check.py`: offline tests (CI) and live smoke test
- `build_case.py`: single-PDF pipeline (Reducto parse, Hermes director, Pangram), also behind `/try`

Sample documents (all public, written by humans before 2018): Wu, Wang & Evans (2017), arXiv:1709.02445; *State v. Romanko* (Conn. 2014); GAO-14-344 (2014).
