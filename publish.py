"""Publish a benchmark run to the public Modal app.

  python publish.py runs/full
"""
import subprocess, sys
from pathlib import Path

run = Path(sys.argv[1] if len(sys.argv) > 1 else "runs/full")
modal = str(Path(".venv/Scripts/modal"))
subprocess.run([modal, "volume", "create", "forgery-lab-cases"], capture_output=True)  # ok if it exists
files = [run / "report.html"] + sorted(run.glob("human_*.html"))
for f in files:
    if not f.exists():
        sys.exit(f"missing {f} — run report.py and case_from_run.py first")
    subprocess.run([modal, "volume", "put", "--force", "forgery-lab-cases", str(f), f"/site/{f.name}"], check=True)
    print("uploaded", f.name)
subprocess.run([modal, "deploy", "modal_app.py"], check=True)
