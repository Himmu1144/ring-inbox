"""The web server: serves the page and a few small endpoints.

Run:  .venv/bin/uvicorn server:app --reload   then open http://localhost:8000
"""
import json
import os
import time
import uuid
from collections import OrderedDict, defaultdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import brain
import caller
import inbox

HERE = os.path.dirname(__file__)
app = FastAPI(title="Ring Inbox")

# Call sentences stay on the server. The page only gets an id for each one,
# so the page cannot make the phone call say something the AI did not write.
CALL_LINES: OrderedDict[str, str] = OrderedDict()

# Simple brake so one visitor cannot burn the whole AI quota.
MAX_RUNS_PER_10_MIN = 20
_recent: dict[str, list[float]] = defaultdict(list)


class Email(BaseModel):
    sender: str = Field("", max_length=200)
    subject: str = Field("", max_length=300)
    body: str = Field("", max_length=4000)


class DecideRequest(BaseModel):
    emails: list[Email] = Field(min_length=1, max_length=brain.MAX_EMAILS)
    rules: list[str] = Field(max_length=8)


class CallRequest(BaseModel):
    phone: str = Field(max_length=20)
    decision_ids: list[str] = Field(max_length=10)


@app.get("/api/ping")
def healthz():
    """For the keep-warm ping. No AI, no calls."""
    return {"ok": True}


@app.get("/")
def page():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/start-data")
def start_data():
    with open(os.path.join(HERE, "data", "mock_emails.json")) as f:
        emails = json.load(f)
    return {
        "rules": brain.DEFAULT_RULES,
        "emails": emails,
        "calls_left": caller.calls_left(),
        "real_inbox": inbox.address() if inbox.enabled() else None,
    }


@app.get("/api/inbox/latest")
def inbox_latest():
    """Where to start watching from. Only works where REAL_INBOX=on (never on the public site)."""
    if not inbox.enabled():
        raise HTTPException(404, "The real inbox is not available here.")
    try:
        return {"uid": inbox.latest_uid()}
    except Exception:
        raise HTTPException(502, "Could not reach the inbox.")


@app.get("/api/inbox/new")
def inbox_new(after: int):
    if not inbox.enabled():
        raise HTTPException(404, "The real inbox is not available here.")
    try:
        return {"emails": inbox.new_since(after)}
    except Exception:
        raise HTTPException(502, "Could not reach the inbox.")


@app.post("/api/decide-all")
def decide_all(req: DecideRequest, request: Request):
    """The whole inbox in one AI request. Returns one decision per email, same order."""
    visitor = request.client.host if request.client else "unknown"
    now = time.time()
    _recent[visitor] = [t for t in _recent[visitor] if now - t < 600]
    if len(_recent[visitor]) >= MAX_RUNS_PER_10_MIN:
        raise HTTPException(429, "Too many runs in a short time. Wait a few minutes.")
    _recent[visitor].append(now)

    rules = [r.strip()[:300] for r in req.rules if r.strip()]
    emails = [{"from": e.sender, "subject": e.subject, "body": e.body} for e in req.emails]
    decisions = brain.decide_all(emails, rules)

    for decision in decisions:
        decision["id"] = uuid.uuid4().hex
        if decision["action"] == "call":
            CALL_LINES[decision["id"]] = decision["call_line"]
    while len(CALL_LINES) > 500:
        CALL_LINES.popitem(last=False)
    return {"decisions": decisions}


@app.post("/api/call")
def call(req: CallRequest):
    lines = [CALL_LINES[i] for i in req.decision_ids if i in CALL_LINES]
    try:
        return caller.place_call(req.phone, lines)
    except caller.CallRefused as refused:
        raise HTTPException(400, str(refused))
    except Exception:
        raise HTTPException(502, "The call could not be placed. The decisions above are still correct.")


@app.get("/api/call-status/{call_id}")
def call_status(call_id: str):
    try:
        return {"status": caller.call_status(call_id)}
    except Exception:
        return {"status": "unknown"}
