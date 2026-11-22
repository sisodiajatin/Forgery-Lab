"""Forgery Lab — small, pure helpers shared by the runner, report and tests (no network, no keys)."""
import math
import re

THRESH = 0.5  # AI score >= THRESH counts as "flagged as AI"


def wilson(k: int, n: int, z: float = 1.96):
    """95% Wilson score interval for k successes out of n, as percentages (lo, hi). Robust for small n and 0/n."""
    if n == 0:
        return (None, None)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(100 * max(0.0, centre - half), 1), round(100 * min(1.0, centre + half), 1))


def rate(k: int, n: int) -> dict:
    """A percentage with its count and 95% CI — never report a bare percentage."""
    lo, hi = wilson(k, n)
    return {"k": k, "n": n, "pct": round(100 * k / n, 1) if n else None, "lo": lo, "hi": hi}


def detag(t: str) -> str:
    """Strip HTML-ish tags (Reducto <sup>/<i>, model output) — they are giveaways in the human round."""
    t = re.sub(r"<sup>.*?</sup>", "", t or "")
    t = re.sub(r"</?[a-zA-Z][^>]*>", "", t)
    return re.sub(r"\s+", " ", t).strip()


def overlap(fake: str, source: str, n: int = 8) -> float:
    """Share of the fake's n-word sequences that appear verbatim in the (lower-cased) source."""
    w = re.sub(r"\s+", " ", fake.lower()).split()
    grams = [" ".join(w[i:i + n]) for i in range(len(w) - n + 1)]
    return sum(g in source for g in grams) / max(len(grams), 1)


def style_features(text: str) -> dict:
    """Cheap, measurable style features used to ground the 'what fooled the detector' analysis."""
    t = detag(text)
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if s.split()]
    lens = [len(s.split()) for s in sents] or [0]
    words = t.split()
    nw = max(len(words), 1)
    mean = sum(lens) / len(lens)
    sd = (sum((x - mean) ** 2 for x in lens) / len(lens)) ** 0.5
    return {
        "words": len(words),
        "sentences": len(sents),
        "mean_sentence_len": round(mean, 1),
        "sentence_len_sd": round(sd, 1),                          # "burstiness": humans vary more
        "digits_per_100w": round(100 * len(re.findall(r"\d+", t)) / nw, 1),   # concrete specifics
        "citations_per_100w": round(100 * len(re.findall(r"\[\d+\]|\(\d{4}\)|v\.|§|\d+ [A-Z][a-z]*\.? ?\d", t)) / nw, 1),
        "parens_per_100w": round(100 * t.count("(") / nw, 1),
        "first_person_per_100w": round(100 * len(re.findall(r"\b(we|our|us|I)\b", t)) / nw, 1),
    }


def mean_features(texts):
    fs = [style_features(t) for t in texts]
    if not fs:
        return {}
    return {k: round(sum(f[k] for f in fs) / len(fs), 1) for k in fs[0]}


def numbers_in(text: str):
    return {float(x) for x in re.findall(r"\d+(?:\.\d+)?", text or "")}


def unverified_numbers(claims, facts_text: str, tol: float = 0.06):
    """Numbers quoted in agent-written claims that don't appear in the measured facts (guards against hallucinated stats)."""
    known = numbers_in(facts_text)
    bad = []
    for c in claims:
        for x in numbers_in(c):
            if x in (1, 2, 3, 4, 5, 95, 100) or 1990 <= x <= 2030:
                continue
            if not any(abs(x - y) <= tol for y in known):
                bad.append((c, x))
    return bad
