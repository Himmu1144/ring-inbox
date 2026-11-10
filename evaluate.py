"""Scores the brain against hand-labelled test emails.

    python evaluate.py                       # the normal model chain
    python evaluate.py openai/gpt-oss-20b    # one Groq model only
    python evaluate.py gemini-2.5-flash      # one Gemini model only
"""
import json
import os
import sys

import brain

HERE = os.path.dirname(__file__)
brain.LOG_FILE = os.path.join(HERE, "tests", "eval_log.jsonl")  # keep test runs out of the real log

if len(sys.argv) > 1:
    model = sys.argv[1]
    brain.GROQ_MODELS = [] if model.startswith("gemini") else [model]
    brain.GEMINI_MODELS = [model] if model.startswith("gemini") else []

with open(os.path.join(HERE, "tests", "emails.json")) as f:
    cases = json.load(f)

decisions = brain.decide_all(cases, brain.DEFAULT_RULES)
right = 0
print(f"model: {decisions[0]['model'] or 'none answered'}  ({decisions[0]['seconds']}s)\n")
for case, d in zip(cases, decisions):
    ok = d["action"] in case["expect"]
    right += ok
    mark = "ok  " if ok else "MISS"
    print(f"{mark} #{case['id']:<2} got {d['action']:<6} ({d['confidence']:.2f}) want {'/'.join(case['expect']):<11} {case['subject'][:48]}")
    if not ok:
        print(f"        tricky because: {case['why_tricky']}")
        print(f"        AI said: {d['reason']}")
print(f"\nscore: {right} / {len(cases)}")
