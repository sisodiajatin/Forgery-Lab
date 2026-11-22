# FORGERY LAB 🕵️ — a stress test for AI detectors

**Can an AI detector be trusted on *your* kind of documents?**
Schools, hiring teams and publishers make real decisions with AI detectors: failing a student, rejecting an
applicant, pulling an article. Forgery Lab finds out how well a detector holds up. AI forgers attack it using
real human documents, rewrite their fakes when they get caught, and the results go into a plain-English trust report.

**Live demo:** https://jatinsisodiausa--forgery-lab-web.us-east.modal.run
(report · `/play` human round · `/try` your own PDF)

## Headline results (run `runs/full`)
112 valid attacks · 3 human-written documents (science paper, court opinion, government report) · 4 forger models · up to 3 rewrite rounds.

| | |
|---|---|
| Caught on the first try | **86.6%** |
| Evaded the detector after rewrites | **33.9%** |
| Real human paragraphs wrongly flagged | **1 / 30 (3.3%)** |

| Forger | Attacks | Evaded after rewrites | Avg AI score, first → best |
|---|---|---|---|
| GLM 5.3 Flash | 22 | 81.8% | 54% → 26% |
| Kimi K3.1 Pro | 30 | 53.3% | 85% → 49% |
| DeepSeek V4.1 Flash 1017 | 30 | 13.3% | 92% → 76% |
| Hermes-3 8B (self-hosted on Modal GPU) | 30 | 0.0% | 98% → 91% |

Evasion by document: science paper 11.8%, court opinion 36.8%, government report 50.0%.
Hermes Agent's verdict: **USE WITH CAUTION.** The samples are small, so treat these numbers as indicative.

## How it works
| Stage | Tool | Role |
|---|---|---|
| Read | **Reducto** | Parses real human PDFs into clean paragraphs (pypdf fallback) |
| Plan | **Hermes Agent** | Proposes topics that fit the document but aren't in it. Writes the final verdict from the measured numbers |
| Judge | DeepSeek V4.1 Flash | Rejects topics the document already covers. Rejects forgeries that paraphrase the source |
| Attack | **Modal** | Hermes-3 8B on our own L40S GPU (vLLM), plus Kimi K3.1 Pro, GLM 5.3 Flash and DeepSeek V4.1 Flash on Modal Model APIs, all attacking in parallel |
| Detect | **Pangram** | Scores every forgery and every genuine paragraph. Caught forgeries get the flagged passages back and rewrite |
| Play | Case-board game | The forgeries that fooled the detector, mixed with real paragraphs, so humans can take on the same test |

**Integrity checks:**
- **Copying:** forgeries that copy more than 10% of the source verbatim (8-word sequences) are discarded.
- **Paraphrasing:** forgeries a judge model finds restating the source are discarded too.
- **Topics:** topics the document already covers are thrown out before any forging.
- **Human baseline:** genuine paragraphs are scored as well, to measure false alarms.
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
python publish.py runs/full                                     # upload + deploy the public site
```

## Files
- `attack.py`: the parallel attack runner (forge → integrity checks → Pangram → rewrite loop)
- `forgers.py`: OpenAI-compatible client for Modal Model APIs
- `modal_forger.py`: Hermes-3 8B on a Modal GPU (vLLM)
- `report.py` + `game/report_template.html`: the trust-report dashboard
- `case_from_run.py` + `game/template.html`: the human-round case boards
- `modal_app.py` + `publish.py`: the public web app on Modal
- `build_case.py`: single-PDF pipeline (Reducto parse, Hermes director, Pangram), also behind `/try`

Sample documents (all public, written by humans before 2018): Wu, Wang & Evans (2017), arXiv:1709.02445; *State v. Romanko* (Conn. 2014); GAO-14-344 (2014).
