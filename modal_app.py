"""Forgery Lab — public web app on Modal (detector stress test).

  python publish.py runs/full          # uploads report + human boards to the Modal volume, then deploys

Routes
  /              stress-test report (+ live humans-vs-detector tally)
  /play          pick a human-round board        /play/<doc>  play it
  /human  POST   record a player's result        /human/stats JSON tally
  /try           upload your own PDF -> quick case board (bonus; Hermes-3 on Modal directs + forges)
"""
import modal

app = modal.App("forgery-lab")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi[standard]", "python-multipart", "pypdf", "requests", "modal")
    .env({"FL_LLM": "modal", "FL_FORGER": "api"})
    .add_local_file("build_case.py", "/app/build_case.py")
    .add_local_file("forgers.py", "/app/forgers.py")
    .add_local_dir("game", "/app/game")
)
vol = modal.Volume.from_name("forgery-lab-cases", create_if_missing=True)

STYLE = """<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500&family=IBM+Plex+Mono:wght@400;500&family=Newsreader:opsz,wght@6..72,400&display=swap" rel=stylesheet>
<style>:root{--deep:#12110f;--bg:#161513;--card:#1c1a18;--raised:#262421;--text:#efe9de;--text2:#aaa398;--mute:#8a847a;--line:rgba(239,233,222,.08);--ink:#e5674f;--paper:#f2ece0;--ease:cubic-bezier(.22,1,.36,1)}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:var(--bg);color:var(--text);font:400 15px/22px 'IBM Plex Sans',system-ui,sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--text);text-underline-offset:3px}
nav{height:56px;border-bottom:1px solid var(--line);display:flex;align-items:center}
nav .in{max-width:1200px;margin:0 auto;padding:0 32px;width:100%;display:flex;align-items:center;gap:24px}
nav .logo{font-weight:500;font-size:16px;margin-right:auto;text-decoration:none;display:flex;align-items:center;gap:8px}
nav .logo i{width:8px;height:8px;background:var(--ink);display:inline-block}
nav a{font-size:14px;color:var(--text2);text-decoration:none}nav a:hover,nav a.on{color:var(--text)}
nav .btn{color:var(--deep);background:var(--text);padding:6px 14px;border-radius:8px;font-weight:500}nav .btn:hover{color:var(--deep);background:#fff}
main{max-width:1200px;margin:0 auto;padding:64px 32px 96px}
.eyebrow{font:400 12px/16px 'IBM Plex Mono',monospace;color:var(--mute)}
h1{font:400 48px/1.05 'Newsreader',serif;letter-spacing:-.025em;margin:12px 0 16px;max-width:16em}
.lede{font-size:18px;line-height:28px;color:var(--text2);max-width:36rem;margin:0 0 40px}
.cases{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;max-width:880px}
a.case{display:block;padding:24px;background:var(--paper);color:#1f1b16;text-decoration:none;border-radius:4px;transition:transform .15s var(--ease)}
a.case:hover{transform:translateY(-2px)}
a.case span{font:400 12px/16px 'IBM Plex Mono',monospace;color:#6b6156}
a.case b{display:block;font:400 24px/1.2 'Newsreader',serif;margin:8px 0 4px}
a.case small{color:#5e554a;font-size:14px}
.drop{display:block;max-width:640px;border:1px dashed rgba(239,233,222,.24);border-radius:12px;padding:40px 24px;text-align:center;cursor:pointer;color:var(--text2);transition:border-color .15s var(--ease),background-color .15s var(--ease)}
.drop:hover,.drop.on{border-color:var(--ink);background:rgba(229,103,79,.05)}
.drop b{display:block;color:var(--text);font-weight:500;margin-bottom:4px}
button{font:500 15px 'IBM Plex Sans',sans-serif;background:var(--text);color:var(--deep);border:0;height:44px;padding:0 20px;border-radius:8px;cursor:pointer;margin-top:16px;transition:background-color .15s var(--ease),transform .12s var(--ease)}
button:hover{background:#fff}button:active{transform:scale(.98)}
#st{margin-top:24px;max-width:640px;font:400 13px/22px 'IBM Plex Mono',monospace;color:var(--text2)}
.tips{max-width:640px;margin-top:40px;padding-top:24px;border-top:1px solid var(--line);color:var(--mute);font-size:14px;line-height:22px}
@media(max-width:900px){main{padding:40px 20px 64px}nav .in{padding:0 20px}h1{font-size:36px}.cases{grid-template-columns:1fr}nav .hide{display:none}}</style>"""
def NAV(on=""):
    c = lambda k: " on" if k == on else ""
    return (f'<nav><div class="in"><a class="logo" href="/"><i></i>Forgery Lab</a><a class="hide{c("r")}" href="/">Report</a>'
            f'<a class="hide{c("p")}" href="/play">Human round</a><a class="btn" href="/try">Test your own PDF</a></div></nav>')
LABELS = {"1709.02445v2": ("Science paper", "Wu, Wang & Evans (2017) — team size & disruption"),
          "court_romanko_2014": ("Court opinion", "State of Connecticut v. Romanko (2014)"),
          "gov_report": ("Government report", "GAO-14-344, information security at small agencies (2014)"),
          "speech_2015": ("Policy speech", "Lael Brainard, Federal Reserve, financial stability (Dec 2014)")}

TRY = """<main><div class=eyebrow>Your own document</div><h1>Plant forgeries in a PDF you trust</h1>
<p class=lede>Upload something a person wrote. Three AI forgers each write a paragraph in its voice, Pangram scores every exhibit, and you get a board to play in about 15 seconds.</p>
<label class=drop id=drop><input type=file id=f accept=application/pdf hidden><b id=fn>Choose a PDF</b>or drop it here · text PDFs up to 25 MB</label>
<button id=go>Build the case board</button><div id=st></div>
<div class=tips>Works best with human-written text from before 2022, at least two pages of paragraphs. Scanned images have no text to read. Uploaded boards don't change the stress-test report.</div></main><script>
const f=document.getElementById('f'),st=document.getElementById('st');f.onchange=()=>document.getElementById('fn').textContent=f.files[0]?.name||'Choose a PDF';
const d=document.getElementById('drop');d.ondragover=e=>{e.preventDefault();d.classList.add('on')};d.ondragleave=()=>d.classList.remove('on');d.ondrop=e=>{e.preventDefault();d.classList.remove('on');f.files=e.dataTransfer.files;f.onchange()};
document.getElementById('go').onclick=async()=>{if(!f.files[0])return st.textContent='Choose a PDF first';const fd=new FormData();fd.append('pdf',f.files[0]);
st.textContent='Uploading';const t0=Date.now();const r=await fetch('/build',{method:'POST',body:fd});const j=await r.json();
if(!r.ok)return st.textContent='Could not build the case: '+(j.detail||r.status);
const tick=async()=>{const s=await (await fetch('/status/'+j.id)).json();const secs=Math.round((Date.now()-t0)/1000);
 if(s.state==='done')return location.href='/case/'+j.id; if(s.state==='error')return st.innerHTML='Could not build the case: '+s.msg;
 st.innerHTML=(s.log||[]).map(x=>'— '+x.replace(/…$/,'')).join('<br>')+`<br><span style="color:var(--mute)">${secs}s</span>`;setTimeout(tick,700)};tick()};</script>"""


@app.function(image=image, secrets=[modal.Secret.from_name("forgery-lab-keys")], volumes={"/data": vol},
              timeout=900, max_containers=1, scaledown_window=900)
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def web():
    import json, sys, tempfile, time, uuid
    from pathlib import Path
    from fastapi import FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.concurrency import run_in_threadpool
    from fastapi.responses import HTMLResponse, JSONResponse
    sys.path.insert(0, "/app")
    import build_case as bc

    api = FastAPI()
    site = Path("/data/site")

    def page(body):
        return HTMLResponse("<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                            f"<title>FORGERY LAB</title>{STYLE}</head><body>{body}</body></html>")

    def human_stats():
        vol.reload()
        f = Path("/data/human.jsonl")
        rows = [json.loads(l) for l in f.read_text().splitlines() if l.strip()] if f.exists() else []
        forged = [x for r in rows for x in (r.get("forged") or []) if x.get("forged")]
        lab = [r for r in rows if r.get("lab_correct") is not None]
        return {"players": len(rows),
                "human_caught_pct": round(100 * sum(bool(x.get("accused")) for x in forged) / len(forged), 1) if forged else None,
                "human_accuracy_pct": round(100 * sum(r.get("correct") or 0 for r in rows) / max(sum(r.get("total") or 0 for r in rows), 1), 1) if rows else None,
                "lab_accuracy_pct": round(100 * sum(r["lab_correct"] for r in lab) / max(sum(r.get("total") or 0 for r in lab), 1), 1) if lab else None}

    @api.get("/", response_class=HTMLResponse)
    def home():
        vol.reload()
        f = site / "report.html"
        if not f.exists():
            return page(NAV("r") + "<main><h1>Forgery Lab</h1><p class=lede>The report hasn't been published yet.</p></main>")
        return f.read_text(encoding="utf-8")

    @api.get("/play", response_class=HTMLResponse)
    def play():
        vol.reload()
        boards = sorted(p.stem.removeprefix("human_") for p in site.glob("human_*.html")) if site.exists() else []
        links = "".join(f"<a class=case href='/play/{b}'><span>Case {i+1:02d}</span><b>{LABELS.get(b, (b, ''))[0]}</b><small>{LABELS.get(b, ('', ''))[1]}</small></a>"
                        for i, b in enumerate(boards))
        return page(NAV("p") + "<main><div class=eyebrow>Human round</div><h1>Spot the forgeries that fooled the detector</h1>"
                    "<p class=lede>Each board mixes real paragraphs with AI forgeries, mostly ones Pangram scored as human. "
                    "Pick the fakes, then compare your calls with the detector's.</p><div class=cases>"
                    + (links or "<p>No boards published yet.</p>") + "</div></main>")

    @api.get("/play/{doc}", response_class=HTMLResponse)
    def play_doc(doc: str):
        vol.reload()
        f = site / f"human_{doc}.html"
        if not doc.replace("_", "").replace(".", "").isalnum() or not f.exists():
            raise HTTPException(404)
        return f.read_text(encoding="utf-8")

    @api.post("/human")
    async def human(req: Request):
        rec = await req.json()
        rec = {k: rec.get(k) for k in ("source", "total", "correct", "lab_correct", "forged")}
        rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        with open("/data/human.jsonl", "a") as fh:
            fh.write(json.dumps(rec) + "\n")
        vol.commit()
        return {"ok": True}

    @api.get("/human/stats")
    def stats():
        return JSONResponse(human_stats())

    @api.get("/try", response_class=HTMLResponse)
    def try_page():
        return page(NAV() + TRY)

    import threading
    jobs = {}  # in-memory job status; one container (max_containers=1) serves all requests concurrently

    def run_job(cid, name, data):
        log = []
        def step(msg):
            log.append(msg); jobs[cid] = {"state": "running", "log": log}
        try:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / name
                p.write_bytes(data)
                case = bc.build_case(p, 3, 6, None, "normal", 0, progress=step)
            Path("/data/cases").mkdir(parents=True, exist_ok=True)
            Path(f"/data/cases/{cid}.html").write_text(bc.render(case), encoding="utf-8")
            vol.commit()
            jobs[cid] = {"state": "done", "log": log}
        except ValueError as e:
            jobs[cid] = {"state": "error", "msg": str(e), "log": log}
        except Exception as e:
            jobs[cid] = {"state": "error", "msg": f"{type(e).__name__}: {str(e)[:200]}", "log": log}

    @api.post("/build")
    def build(pdf: UploadFile = File(...)):
        data = pdf.file.read()
        if len(data) > 25_000_000 or not data.startswith(b"%PDF"):
            raise HTTPException(400, "Please upload a PDF under 25 MB.")
        cid = uuid.uuid4().hex[:10]
        jobs[cid] = {"state": "running", "log": ["Upload received"]}
        threading.Thread(target=run_job, args=(cid, Path(pdf.filename or "document.pdf").name, data), daemon=True).start()
        return {"id": cid}

    @api.get("/status/{cid}")
    def status(cid: str):
        return JSONResponse(jobs.get(cid, {"state": "unknown"}))

    @api.get("/case/{cid}", response_class=HTMLResponse)
    def show(cid: str):
        vol.reload()
        if not Path(f"/data/cases/{cid}.html").exists():
            import time as _t; _t.sleep(1.5); vol.reload()
        f = Path(f"/data/cases/{cid}.html")
        if not cid.isalnum() or not f.exists():
            raise HTTPException(404, "Case not found")
        return f.read_text(encoding="utf-8")

    return api
