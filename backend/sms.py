import os, asyncio, logging

log = logging.getLogger("sms")

def sms_configured():
    return all(os.environ.get(k) for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM_NUMBER"))

def to_e164(phone: str):
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10: return f"+91{digits}"
    if len(digits) == 12 and digits.startswith("91"): return f"+{digits}"
    return f"+{digits}"

def _send(to, body):
    from twilio.rest import Client
    client = Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])
    msg = client.messages.create(body=body, from_=os.environ["TWILIO_FROM_NUMBER"], to=to)
    return msg.sid

async def send_sms(phone: str, body: str):
    """Returns (ok, detail). Never raises."""
    if not sms_configured(): return False, "SMS not configured"
    try:
        sid = await asyncio.to_thread(_send, to_e164(phone), body)
        return True, sid
    except Exception as e:
        log.warning("SMS failed: %s", e)
        return False, str(e)[:200]
