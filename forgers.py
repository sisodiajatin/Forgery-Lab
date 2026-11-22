"""Forgery Lab — forger models served by Modal Model APIs (OpenAI-compatible, pay per token).

Each forger is configured from .env as <NAME>_BASE_URL, <NAME>_MODEL, <NAME>_AUTH
(AUTH = whatever follows "Authorization:" in the endpoint's Quickstart, e.g. "Bearer abc...").
Optional <NAME>_MODAL_KEY / <NAME>_MODAL_SECRET are sent as Modal-Key / Modal-Secret headers.

  python forgers.py            # tests every configured forger with one tiny call
"""
import os, re, time

import requests

FORGERS = {  # name -> human label, Modal model id (the id can be overridden in .env)
    "DEEPSEEK": ("DeepSeek V4.1 Flash 1017", "deepseek-ai/DeepSeek-V4.1-Flash-1017"),
    "GLMFLASH": ("GLM 5.3 Flash", "zai-org/GLM-5.3-Flash"),
    "KIMI": ("Kimi K3.1 Pro", "moonshotai/Kimi-K3.1-Pro"),
}


# Per-model settings that skip hidden "thinking" (measured: GLM 18.7s->3.5s, Kimi 10.0s->1.8s, DeepSeek 2.6s->1.3s).
FAST = {"GLMFLASH": {"reasoning_effort": "low"},
        "KIMI": {"chat_template_kwargs": {"thinking": False, "enable_thinking": False}},
        "DEEPSEEK": {"chat_template_kwargs": {"thinking": False, "enable_thinking": False}}}


def configured() -> list[str]:
    return [n for n in FORGERS if os.environ.get(f"{n}_BASE_URL") and os.environ.get(f"{n}_AUTH")]


def chat(name: str, messages: list[dict], max_tokens=1500, temperature=0.85, retries=3, fast=False) -> dict:
    base = os.environ[f"{name}_BASE_URL"].rstrip("/")
    if not base.endswith("/v1") and "/v1/" not in base:
        base += "/v1"
    auth = os.environ[f"{name}_AUTH"].strip()
    if not auth.lower().startswith(("bearer ", "basic ")):
        auth = "Bearer " + auth
    headers = {"Authorization": auth, "Content-Type": "application/json"}
    if os.environ.get(f"{name}_MODAL_KEY"):
        headers["Modal-Key"] = os.environ[f"{name}_MODAL_KEY"]
        headers["Modal-Secret"] = os.environ.get(f"{name}_MODAL_SECRET", "")
    body = {"model": os.environ.get(f"{name}_MODEL") or FORGERS[name][1], "messages": messages,
            "max_tokens": max_tokens, "temperature": temperature, **(FAST.get(name, {}) if fast else {})}
    for attempt in range(retries):
        t0 = time.time()
        r = requests.post(f"{base}/chat/completions", headers=headers, json=body, timeout=180)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
            time.sleep(2 * (attempt + 1)); continue
        if r.status_code >= 400:
            raise RuntimeError(f"{name} HTTP {r.status_code}: {r.text[:300]}")
        j = r.json()
        msg = j["choices"][0]["message"]
        text = (msg.get("content") or "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()   # drop reasoning if inlined
        return {"text": text, "usage": j.get("usage", {}), "seconds": round(time.time() - t0, 1),
                "model": j.get("model", body["model"])}


def forge(name: str, system: str, prompt: str, max_tokens=4000, fast=False) -> str:
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    for budget in (max_tokens, max_tokens * 2):      # reasoning models can spend the whole budget thinking
        text = chat(name, msgs, budget, fast=fast)["text"]
        if len(text.split()) >= 20:
            return text
    return text


if __name__ == "__main__":
    import build_case
    build_case.load_env()
    names = configured()
    if not names:
        print("No forger configured. Fill DEEPSEEK_BASE_URL and DEEPSEEK_AUTH in .env.")
    for n in names:
        try:
            r = chat(n, [{"role": "user", "content": "Reply with exactly: forger online"}], max_tokens=400, temperature=0)
            print(f"{FORGERS[n][0]}: OK in {r['seconds']}s -> {r['text']!r} | model={r['model']} | usage={r['usage']}")
        except Exception as e:
            print(f"{FORGERS[n][0]}: FAILED -> {e}")
