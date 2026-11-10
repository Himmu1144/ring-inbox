"""Reads the real Gmail inbox over IMAP (app password). Read-only: never marks, moves or deletes."""
import email
import html
import imaplib
import os
import re
from email.header import decode_header, make_header

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def enabled() -> bool:
    """The real inbox only works where REAL_INBOX=on. Off on the public site, for privacy."""
    return os.getenv("REAL_INBOX", "off").lower() == "on" and bool(os.getenv("GMAIL_APP_PASSWORD"))


def address() -> str:
    return os.getenv("GMAIL_ADDRESS", "")


def _connect():
    box = imaplib.IMAP4_SSL("imap.gmail.com", timeout=20)
    box.login(os.environ["GMAIL_ADDRESS"], os.environ["GMAIL_APP_PASSWORD"].replace(" ", ""))
    box.select("INBOX", readonly=True)
    return box


def _text(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def _body(message) -> str:
    """Plain text if the email has it, otherwise the HTML with tags stripped."""
    plain, rich = None, None
    for part in message.walk() if message.is_multipart() else [message]:
        if part.get_content_maintype() == "multipart" or part.get_filename():
            continue
        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and rich is None:
            rich = text
    if plain is None and rich:
        rich = re.sub(r"(?is)<(script|style).*?</\1>", " ", rich)
        plain = html.unescape(re.sub(r"<[^>]+>", " ", rich))
    plain = re.sub(r"[ \t\r\f\v]+", " ", plain or "")
    return re.sub(r"\n\s*\n+", "\n\n", plain).strip()[:3000]


def latest_uid() -> int:
    """The newest email's id right now. Anything after this counts as new."""
    box = _connect()
    try:
        _, data = box.uid("search", None, "ALL")
        uids = data[0].split()
        return int(uids[-1]) if uids else 0
    finally:
        box.logout()


def new_since(after_uid: int, limit: int = 10) -> list[dict]:
    """Emails that arrived after `after_uid`, oldest first."""
    box = _connect()
    try:
        _, data = box.uid("search", None, f"UID {after_uid + 1}:*")
        uids = [int(u) for u in data[0].split() if int(u) > after_uid][-limit:]
        emails = []
        for uid in uids:
            _, parts = box.uid("fetch", str(uid), "(BODY.PEEK[])")  # PEEK: stays unread in Gmail
            raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
            if not raw:
                continue
            message = email.message_from_bytes(raw)
            emails.append({
                "uid": uid,
                "from": _text(message.get("From")),
                "subject": _text(message.get("Subject")),
                "body": _body(message),
            })
        return emails
    finally:
        box.logout()


if __name__ == "__main__":
    top = latest_uid()
    print("newest uid:", top)
    for e in new_since(top - 3):
        print(e["uid"], "|", e["from"], "|", e["subject"], "|", e["body"][:80].replace("\n", " "))
