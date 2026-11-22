# FORGERY LAB 🕵️ — a stress test for AI detectors

**Can an AI detector be trusted on *your* kind of documents?**
Schools, hiring teams and publishers make real decisions with AI detectors: failing a student, rejecting an
applicant, pulling an article. Forgery Lab finds out how well a detector holds up. AI forgers attack it using
real human documents, rewrite their fakes when they get caught, and the results go into a plain-English trust report.

**Live demo:** https://jatinsisodiausa--forgery-lab-web.us-east.modal.run
(report · `/play` human round · `/try` your own PDF)

## Headline results (`runs/combined` = `full` + `big` + `speech`, false alarms from `genuine_all`)
**427 valid attacks** (440 attempted, 13 errors) · **4 human-written documents** (science paper, court opinion,
government report, policy speech) · 4 forger models · up to 3 rewrite rounds. False alarms were measured on
**every** usable real paragraph (156), not a sample. All intervals are 95% Wilson intervals.

| | Rate | 95% CI |
|---|---|---|
| Caught on the first try | **84.3%** (360/427) | 80.6–87.5% |
| Evaded the detector after rewrites | **32.6%** (139/427) | 28.3–37.1% |
| Real human paragraphs wrongly flagged | **0.0%** (0/156) | 0.0–2.4% |

| Forger | Evaded after rewrites | 95% CI | Avg AI score, first → best |
|---|---|---|---|
| GLM 5.3 Flash | **70.1%** (68/97) | 60.4–78.3% | 55% → 34% |
| Kimi K3.1 Pro | **47.3%** (52/110) | 38.2–56.5% | 85% → 54% |
| DeepSeek V4.1 Flash 1017 | 14.5% (16/110) | 9.2–22.3% | 93% → 82% |
| Hermes-3 8B (self-hosted on Modal GPU) | 2.7% (3/110) | 0.9–7.7% | 98% → 94% |

| Document | Evaded | 95% CI | False alarms |
|---|---|---|---|
| Government report | **49.2%** (59/120) | 40.4–58.0% | 0/81 |
| Court opinion | **44.0%** (51/116) | 35.3–53.0% | 0/22 |
| Science paper | 25.4% (29/114) | 18.3–34.1% | 0/33 |
| Policy speech | **0.0%** (0/77) | 0.0–4.8% | 0/20 |

**Main findings:**
- **Pangram never wrongly accused a human.** 0 of 156 real paragraphs were flagged.
- **But it can be beaten by rewriting.** A third of forgeries got through after up to 3 rewrites, and how often depends heavily on the forger model and the document type.
- **It held completely on the policy speech:** 227 rewrite attempts were all caught. It was weakest on dense institutional prose (government and legal writing).

**A methodology catch worth knowing.** Reducto's `summarize_figures` option is on by default and inserts
**AI-written figure descriptions** into the parsed text. In our first runs these were counted as "human" paragraphs,
so Pangram's correct AI flags on them looked like false alarms (3/58). We now turn the option off, drop figure blocks,
and keep a regression test for it. If you build human-vs-AI datasets from parsed PDFs, check for this.

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
python genuine_all.py samples/*.pdf --out runs/genuine_all     # score EVERY real paragraph (false alarms)
python report.py runs/full runs/big runs/speech --genuine runs/genuine_all --out runs/combined
python case_from_run.py runs/full runs/big runs/speech --genuine runs/genuine_all --out runs/combined
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

Sample documents (all public, written by humans before 2018): Wu, Wang & Evans (2017), arXiv:1709.02445; *State v. Romanko* (Conn. 2014); GAO-14-344 (2014); Lael Brainard, "The Federal Reserve's Financial Stability Agenda" (Dec 2014).
