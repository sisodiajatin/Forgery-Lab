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
    .env({"FL_LLM": "modal"})
    .add_local_file("build_case.py", "/app/build_case.py")
    .add_local_dir("game", "/app/game")
)
vol = modal.Volume.from_name("forgery-lab-cases", create_if_missing=True)

STYLE = """<link href="https://fonts.googleapis.com/css2?family=Special+Elite&family=Playfair+Display:wght@700&display=swap" rel=stylesheet>
<style>body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 50% -10%,#3a2f22,#14110d 60%);color:#efe6d2;font-family:'Special Elite',monospace}
main{max-width:760px;margin:0 auto;padding:40px 24px}h1{font-family:'Playfair Display';font-size:48px;margin:0}h1 em{color:#c9a24f;font-style:normal}
a.case{display:block;margin:16px 0;padding:20px 22px;background:#efe6d2;color:#1b1712;text-decoration:none;font-size:19px;box-shadow:0 10px 24px rgba(0,0,0,.5)}
a.case small{display:block;font-size:13px;color:#6b5c40;margin-top:4px}a{color:#c9a24f}.nav{margin-bottom:20px;font-size:14px}
.drop{margin:22px 0;border:2px dashed #c9a24f;padding:36px;text-align:center;cursor:pointer;display:block}
button{font-family:inherit;font-size:16px;background:#c9a24f;color:#14110d;border:0;padding:12px 22px;cursor:pointer}#st{margin-top:16px;color:#a89a7d}</style>"""
NAV = '<div class=nav><a href="/">Report</a> · <a href="/play">Play the human round</a> · <a href="/try">Try your own PDF</a></div>'
LABELS = {"1709.02445v2": ("Science paper", "Wu, Wang & Evans (2017) — team size & disruption"),
          "court_romanko_2014": ("Court opinion", "State of Connecticut v. Romanko (2014)"),
          "gov_report": ("Government report", "GAO-14-344, information security at small agencies (2014)")}

TRY = """<main>""" + NAV + """<h1>TRY <em>YOUR PDF</em></h1>
<p>Upload a document written by a human. A forger will slip AI paragraphs into it; you try to find them.</p>
<label class=drop id=drop><input type=file id=f accept=application/pdf hidden><span id=fn>Drop a PDF here, or click to choose</span></label>
<button id=go>OPEN THE CASE ▸</button><div id=st></div></main><script>
const f=document.getElementById('f'),st=document.getElementById('st');f.onchange=()=>document.getElementById('fn').textContent=f.files[0]?.name||'';
const d=document.getElementById('drop');d.ondragover=e=>e.preventDefault();d.ondrop=e=>{e.preventDefault();f.files=e.dataTransfer.files;f.onchange()};
document.getElementById('go').onclick=async()=>{if(!f.files[0])return st.textContent='Choose a PDF first.';const fd=new FormData();fd.append('pdf',f.files[0]);
st.textContent='Reading the document, briefing the forger... about a minute (longer if the GPU is cold).';const r=await fetch('/build',{method:'POST',body:fd});const j=await r.json();
if(!r.ok)return st.textContent='Case failed: '+(j.detail||r.status);location.href='/case/'+j.id};</script>"""


@app.function(image=image, secrets=[modal.Secret.from_name("forgery-lab-keys")], volumes={"/data": vol},
              timeout=900, max_containers=10)
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
            return page("<main>" + NAV + "<h1>FORGERY <em>LAB</em></h1><p>Report not published yet.</p></main>")
        banner = ("<div id=hv style='position:sticky;top:0;z-index:9;background:#c9a24f;color:#14110d;padding:10px 18px;"
                  "font-family:Special Elite,monospace;text-align:center'>Loading humans vs detector…</div>"
                  "<script>fetch('/human/stats').then(r=>r.json()).then(s=>{document.getElementById('hv').innerHTML=s.players?"
                  "`HUMANS vs DETECTOR (live): ${s.players} rounds played · humans caught ${s.human_caught_pct}% of forgeries · accuracy humans ${s.human_accuracy_pct}% vs Pangram ${s.lab_accuracy_pct}% · <a href=/play style='color:#14110d'>play ▸</a>`"
                  ":`No players yet — <a href=/play style='color:#14110d'>be the first to take on the forgers ▸</a>`})</script>")
        return f.read_text(encoding="utf-8").replace("<body>", "<body>" + banner, 1)

    @api.get("/play", response_class=HTMLResponse)
    def play():
        vol.reload()
        boards = sorted(p.stem.removeprefix("human_") for p in site.glob("human_*.html")) if site.exists() else []
        links = "".join(f"<a class=case href='/play/{b}'>{LABELS.get(b, (b, ''))[0]}<small>{LABELS.get(b, ('', ''))[1]}</small></a>" for b in boards)
        return page("<main>" + NAV + "<h1>THE <em>HUMAN ROUND</em></h1><p>Each board hides AI forgeries among real human paragraphs — "
                    "the same forgeries that fooled the detector. Can you beat it?</p>" + (links or "<p>No boards published yet.</p>") + "</main>")

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
        return page(TRY)

    @api.post("/build")
    async def build(pdf: UploadFile = File(...)):
        data = await pdf.read()
        if len(data) > 25_000_000 or not data.startswith(b"%PDF"):
            raise HTTPException(400, "Please upload a PDF under 25 MB.")
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / Path(pdf.filename or "document.pdf").name
            p.write_bytes(data)
            try:
                case = await run_in_threadpool(bc.build_case, p, 3, 6, None, "normal", 0)
            except ValueError as e:
                raise HTTPException(422, str(e))
        cid = uuid.uuid4().hex[:10]
        Path("/data/cases").mkdir(parents=True, exist_ok=True)
        Path(f"/data/cases/{cid}.html").write_text(bc.render(case), encoding="utf-8")
        vol.commit()
        return {"id": cid}

    @api.get("/case/{cid}", response_class=HTMLResponse)
    def show(cid: str):
        vol.reload()
        f = Path(f"/data/cases/{cid}.html")
        if not cid.isalnum() or not f.exists():
            raise HTTPException(404, "Case not found")
        return f.read_text(encoding="utf-8")

    return api
