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


state = modal.Dict.from_name("forgery-lab-state", create_if_missing=True)  # shared by every container: job progress, uploaded boards, human results
SECRETS = [modal.Secret.from_name("forgery-lab-keys")]


@app.function(image=image, secrets=SECRETS, timeout=600, max_containers=30, retries=0)
def build_job(cid: str, name: str, data: bytes):
    """One upload = one container, so uploads never slow each other or the website down."""
    import sys, tempfile
    from pathlib import Path
    sys.path.insert(0, "/app")
    import build_case as bc
    log = []
    def step(msg):
        log.append(msg); state[f"job:{cid}"] = {"state": "running", "log": log}
    try:
        with tempfile.TemporaryDirectory() as d:
            pth = Path(d) / name
            pth.write_bytes(data)
            case = bc.build_case(pth, 3, 6, None, "normal", 0, progress=step)
        state[f"case:{cid}"] = bc.render(case)
        state[f"job:{cid}"] = {"state": "done", "log": log}
    except ValueError as e:
        state[f"job:{cid}"] = {"state": "error", "msg": str(e), "log": log}
    except Exception as e:
        state[f"job:{cid}"] = {"state": "error", "msg": f"{type(e).__name__}: {str(e)[:200]}", "log": log}


@app.function(image=image, secrets=SECRETS, volumes={"/data": vol}, timeout=900,
              min_containers=1, max_containers=10, scaledown_window=600)  # one always-warm server for showcase traffic; scales out under load
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    import json, time, uuid
    from pathlib import Path
    from fastapi import FastAPI, File, HTTPException, Request, UploadFile
    from fastapi.responses import HTMLResponse, JSONResponse

    api = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)  # no public API explorer

    @api.middleware("http")
    async def security_headers(request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.url.path.startswith(("/case/", "/status/")):
            resp.headers["X-Robots-Tag"] = "noindex"  # visitor uploads aren't indexed by search engines
        return resp
    site = Path("/data/site")
    # Published files only change on redeploy (publish.py), which starts fresh containers, so load them once.
    pages = {f.name: f.read_text(encoding="utf-8") for f in site.glob("*.html")} if site.exists() else {}
    stats_cache = {"t": 0.0, "v": None}

    def page(body):
        return HTMLResponse("<!doctype html><html><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
                            f"<title>Forgery Lab</title>{STYLE}</head><body>{body}</body></html>")

    def human_stats():
        if time.time() - stats_cache["t"] < 2 and stats_cache["v"]:
            return stats_cache["v"]
        rows = [v for k, v in state.items() if k.startswith("human:") and valid(v)]
        forged = [x for r in rows for x in (r.get("forged") or []) if x.get("forged")]
        lab = [r for r in rows if r.get("lab_correct") is not None]
        v = {"players": len(rows),
             "human_caught_pct": round(100 * sum(bool(x.get("accused")) for x in forged) / len(forged), 1) if forged else None,
             "human_accuracy_pct": round(100 * sum(r.get("correct") or 0 for r in rows) / max(sum(r.get("total") or 0 for r in rows), 1), 1) if rows else None,
             "lab_accuracy_pct": round(100 * sum(r["lab_correct"] for r in lab) / max(sum(r.get("total") or 0 for r in lab), 1), 1) if lab else None}
        stats_cache.update(t=time.time(), v=v)
        return v

    @api.get("/", response_class=HTMLResponse)
    def home():
        return pages.get("report.html") or page(NAV("r") + "<main><h1>Forgery Lab</h1><p class=lede>The report hasn't been published yet.</p></main>")

    @api.get("/play", response_class=HTMLResponse)
    def play():
        boards = sorted(n[len("human_"):-len(".html")] for n in pages if n.startswith("human_"))
        links = "".join(f"<a class=case href='/play/{b}'><span>Case {i+1:02d}</span><b>{LABELS.get(b, (b, ''))[0]}</b><small>{LABELS.get(b, ('', ''))[1]}</small></a>"
                        for i, b in enumerate(boards))
        return page(NAV("p") + "<main><div class=eyebrow>Human round</div><h1>Spot the forgeries that fooled the detector</h1>"
                    "<p class=lede>Each board mixes real paragraphs with AI forgeries, mostly ones Pangram scored as human. "
                    "Pick the fakes, then compare your calls with the detector's.</p><div class=cases>"
                    + (links or "<p>No boards published yet.</p>") + "</div></main>")

    @api.get("/play/{doc}", response_class=HTMLResponse)
    def play_doc(doc: str):
        html = pages.get(f"human_{doc}.html")
        if html is None:
            raise HTTPException(404)
        return html

    def valid(r):
        try:
            t, c, l, f = r["total"], r["correct"], r.get("lab_correct"), r.get("forged") or []
            return (type(t) is int and 1 <= t <= 20 and type(c) is int and 0 <= c <= t
                    and (l is None or (type(l) is int and 0 <= l <= t)) and isinstance(f, list) and len(f) <= t
                    and all(isinstance(x, dict) and set(x) <= {"forged", "accused"}
                            and all(isinstance(v, bool) for v in x.values()) for x in f))
        except Exception:
            return False

    @api.post("/human")
    def human(rec: dict):
        rec = {k: rec.get(k) for k in ("total", "correct", "lab_correct", "forged")}
        if not valid(rec):
            raise HTTPException(400, "Invalid result")
        if state.get(f"rl:human:{time.strftime('%Y%m%d%H')}", 0) >= 2000:
            raise HTTPException(429, "Too many results this hour")
        state[f"rl:human:{time.strftime('%Y%m%d%H')}"] = state.get(f"rl:human:{time.strftime('%Y%m%d%H')}", 0) + 1
        rec["at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        state[f"human:{uuid.uuid4().hex}"] = rec
        stats_cache["t"] = 0
        return {"ok": True}

    @api.get("/human/stats")
    def stats():
        return JSONResponse(human_stats())

    @api.get("/try", response_class=HTMLResponse)
    def try_page():
        return page(NAV() + TRY)

    PER_IP_HOUR, PER_DAY = 5, 200  # protects the API credits behind uploads

    def allow_upload(ip: str):
        hour, day = time.strftime("%Y%m%d%H"), time.strftime("%Y%m%d")
        if state.get(f"rl:day:{day}", 0) >= PER_DAY:
            raise HTTPException(429, "The lab has reached today's upload limit. Please come back tomorrow, or play the human round in the meantime.")
        if state.get(f"rl:ip:{ip}:{hour}", 0) >= PER_IP_HOUR:
            raise HTTPException(429, f"You've built {PER_IP_HOUR} boards this hour. Please try again later, or play the human round in the meantime.")
        state[f"rl:ip:{ip}:{hour}"] = state.get(f"rl:ip:{ip}:{hour}", 0) + 1
        state[f"rl:day:{day}"] = state.get(f"rl:day:{day}", 0) + 1

    @api.post("/build")
    def build(request: Request, pdf: UploadFile = File(...)):
        data = pdf.file.read()
        if len(data) > 25_000_000 or not data.startswith(b"%PDF"):
            raise HTTPException(400, "Please upload a PDF under 25 MB.")
        fwd = request.headers.get("x-forwarded-for", "")
        allow_upload(fwd.split(",")[0].strip() or (request.client.host if request.client else "unknown"))
        cid = uuid.uuid4().hex[:10]
        state[f"job:{cid}"] = {"state": "running", "log": ["Upload received"]}
        build_job.spawn(cid, Path(pdf.filename or "document.pdf").name, data)
        return {"id": cid}

    @api.get("/status/{cid}")
    def status(cid: str):
        return JSONResponse(state.get(f"job:{cid}", {"state": "unknown"}))

    @api.get("/case/{cid}", response_class=HTMLResponse)
    def show(cid: str):
        html = state.get(f"case:{cid}") if cid.isalnum() else None
        if html is None:
            raise HTTPException(404, "Case not found")
        return html

    return api
