"""The phone call: reads the important emails out loud, one call per run.

Run `python caller.py` to place a test call to MY_PHONE from .env.
"""
import json
import os
import re
from datetime import date
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

MAX_CALLS_PER_DAY = int(os.getenv("MAX_CALLS_PER_DAY", "10"))
COUNT_FILE = os.path.join(os.path.dirname(__file__), "calls_today.json")
VOICE = "Polly.Kajal-Neural"  # Indian English voice built into Twilio
ORDER = ["First", "Second", "Third", "Fourth", "Fifth"]


class CallRefused(Exception):
    """We chose not to place the call (bad number or daily limit)."""


def clean_number(raw: str) -> str:
    """Accepts '98765 43210', '09876543210' or '+919876543210'. Indian mobiles only."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if not re.fullmatch(r"[6-9]\d{9}", digits):
        raise CallRefused("Please enter a 10-digit Indian mobile number.")
    return "+91" + digits


def build_script(call_lines: list[str]) -> str:
    """Turns the call sentences into what the voice says."""
    lines = [l.strip() for l in call_lines if l.strip()][:5]
    count = len(lines)
    parts = [f"Hello. This is your inbox assistant. You have {count} important email{'s' if count != 1 else ''}."]
    for i, line in enumerate(lines):
        parts.append(f"{ORDER[i]}. {line}" if count > 1 else line)
    parts.append("That is all for now. Goodbye.")
    return " ".join(parts)


def _calls_today() -> int:
    try:
        with open(COUNT_FILE) as f:
            data = json.load(f)
        return data["count"] if data["day"] == str(date.today()) else 0
    except (OSError, ValueError, KeyError):
        return 0


def _add_call() -> None:
    try:
        with open(COUNT_FILE, "w") as f:
            json.dump({"day": str(date.today()), "count": _calls_today() + 1}, f)
    except OSError:
        pass


def calls_left() -> int:
    return max(0, MAX_CALLS_PER_DAY - _calls_today())


def place_call(raw_number: str, call_lines: list[str]) -> dict:
    """Calls the number and reads the lines. Returns the script and Twilio's call id."""
    number = clean_number(raw_number)
    if not [l for l in call_lines if l.strip()]:
        raise CallRefused("Nothing important to call about.")
    if calls_left() <= 0:
        raise CallRefused("The demo has used all its calls for today. The decisions above still work.")

    script = build_script(call_lines)
    twiml = (
        f'<Response><Pause length="1"/>'
        f'<Say voice="{VOICE}">{escape(script)}</Say>'
        f'</Response>'
    )
    twilio = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    call = twilio.calls.create(to=number, from_=os.environ["TWILIO_FROM_NUMBER"], twiml=twiml)
    _add_call()
    return {"call_id": call.sid, "script": script, "calls_left": calls_left()}


def call_status(call_id: str) -> str:
    """queued, ringing, in-progress, completed, busy, no-answer or failed."""
    twilio = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    return twilio.calls(call_id).fetch().status


if __name__ == "__main__":
    import time
    result = place_call(os.environ["MY_PHONE"], [
        "The i-SmokeStack hiring team wants to schedule a walkthrough call for the AI Associate role this Thursday at 4 PM.",
        "Rohan Mehta is asking you to resend invoice 204 today because payments close on Friday.",
    ])
    print("Script:", result["script"])
    print("Calls left today:", result["calls_left"])
    for _ in range(20):
        status = call_status(result["call_id"])
        print("status:", status)
        if status in ("completed", "busy", "no-answer", "failed", "canceled"):
            break
        time.sleep(3)
