"""
Count the surface features that separate two sets of descriptions.

    python tells.py A.json B.json     # each a list of {"text": ...}

Counts only. What a blind reader notices beyond these is in the benchmark
write-up, and punctuation turned out not to be it: no em dashes in either set.
"""
import json
import re
import statistics
import sys

FEATURES = {
    "em dash": r"—", "en dash": r"–", "semicolon": r";", "colon": r":",
    "parentheses": r"\(", "we/our": r"\b(we|our|us)\b", "IDEMS": r"\bIDEMS\b",
    "digits": r"\d", "newline": r"\n",
}


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def report(label, texts):
    words = sum(len(t.split()) for t in texts)
    print(f"{label}: n={len(texts)} median words "
          f"{statistics.median(len(t.split()) for t in texts)} median sentences "
          f"{statistics.median(len(sentences(t)) for t in texts)}")
    for name, pattern in FEATURES.items():
        counts = [len(re.findall(pattern, t, flags=re.I)) for t in texts]
        print(f"  {name:12s} texts with {sum(1 for c in counts if c)}/{len(texts)}"
              f"  per 100 words {100 * sum(counts) / words:.2f}")


if __name__ == "__main__":
    for path in sys.argv[1:3]:
        report(path, [r["text"] for r in json.load(open(path, encoding="utf-8"))])
