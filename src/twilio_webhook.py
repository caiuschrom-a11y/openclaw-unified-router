"""Twilio inbound-call webhook for voice-agent-smb.

Each subscriber owns ONE Twilio phone number routed to this endpoint.
On inbound call:

1. Twilio POSTs to /twilio/voice with the From, To, CallSid
2. We greet the caller with TwiML <Say> + <Gather speech>
3. Caller's speech transcribes; Twilio POSTs the transcript to /twilio/respond
4. /twilio/respond:
   a. Looks up the subscriber by 'To' number → metadata (business hours,
      services, current conversation history)
   b. Calls our gateway /v1/voice-agent-smb/run with the caller_input
   c. Returns TwiML <Say> with the response
   d. <Gather> again for the caller's next turn
5. Loop until Twilio call ends OR we capture a callback request

Each subscriber's "owned" Twilio number:
- $1/month from Twilio
- Routed via TwiML App config to https://openclawapi.vercel.app/twilio/voice
- Subscriber's `metadata.twilio_to` matches against the To param
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
import xml.sax.saxutils as saxutils
from typing import Any


GATEWAY_URL = os.environ.get("GATEWAY_URL", "https://openclawapi.vercel.app")
GATEWAY_KEY = os.environ.get("GATEWAY_INTERNAL_KEY", "")  # internal token for service-to-service


def twiml_say_gather(speech: str, action_path: str) -> str:
    """Build a TwiML response: speak + gather caller's next utterance."""
    safe_speech = saxutils.escape(speech)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna-Neural">{safe_speech}</Say>
  <Gather input="speech" timeout="5" speechTimeout="auto" action="{action_path}" method="POST">
    <Say voice="Polly.Joanna-Neural">Please go ahead.</Say>
  </Gather>
  <Say voice="Polly.Joanna-Neural">I didn't hear anything. Please call back when you're ready.</Say>
</Response>"""


def twiml_say_hangup(speech: str) -> str:
    safe_speech = saxutils.escape(speech)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna-Neural">{safe_speech}</Say>
  <Hangup/>
</Response>"""


def lookup_subscriber_by_phone(to_number: str) -> dict[str, Any] | None:
    """Lookup the subscriber owning this Twilio number via Stripe Customer
    metadata. Returns None if not found."""
    import stripe
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe.api_key:
        return None
    try:
        results = stripe.Customer.search(
            query=f'metadata["product_slug"]:"voice-agent-smb" AND metadata["twilio_to"]:"{to_number}"',
        )
        for c in (results.auto_paging_iter() if hasattr(results, "auto_paging_iter") else results.data):
            md_obj = c["metadata"] if "metadata" in c else None
            md: dict[str, str] = {}
            if md_obj is not None:
                for k in list(md_obj.keys()):
                    md[k] = md_obj[k] or ""
            return {
                "customer_id": c["id"],
                "api_key": md.get("openclaw_api_key", ""),
                "business_name": md.get("business_name", "this business"),
                "hours": md.get("business_hours", ""),
                "services": md.get("services", ""),
            }
    except Exception as e:  # noqa: BLE001
        print(f"[voice-agent] subscriber lookup failed: {e}")
    return None


def call_gateway(api_key: str, payload: dict) -> str:
    """Hit the SaaS gateway run endpoint. Returns the assistant text."""
    req = urllib.request.Request(
        f"{GATEWAY_URL}/v1/voice-agent-smb/run",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.load(r)
    return d.get("result", "I'm sorry, I couldn't process that. Please try again.")


def handle_voice_inbound(form: dict[str, str]) -> str:
    """Twilio POSTs to /twilio/voice when a call starts. Greet + gather."""
    to_number = form.get("To", "")
    sub = lookup_subscriber_by_phone(to_number)
    if not sub:
        return twiml_say_hangup(
            "Sorry, this number isn't currently configured. Goodbye."
        )
    greeting = (
        f"Hello, you've reached {sub['business_name']}. "
        f"How can I help you today?"
    )
    return twiml_say_gather(greeting, action_path="/twilio/respond")


def handle_voice_respond(form: dict[str, str]) -> str:
    """Twilio POSTs the gathered speech transcript here. Loop the conversation."""
    to_number = form.get("To", "")
    speech = form.get("SpeechResult", "")
    sub = lookup_subscriber_by_phone(to_number)
    if not sub or not sub.get("api_key"):
        return twiml_say_hangup("Sorry, I'm having trouble. Please try again later.")
    if not speech.strip():
        return twiml_say_gather(
            "I didn't catch that. Can you say it again?",
            action_path="/twilio/respond",
        )

    # Hit the gateway with the conversation context
    payload = {
        "business_name": sub["business_name"],
        "hours": sub["hours"],
        "services": sub["services"],
        "caller_input": speech,
        "history": form.get("history", ""),
    }
    try:
        response_text = call_gateway(sub["api_key"], payload)
    except Exception as e:  # noqa: BLE001
        print(f"[voice-agent] gateway failed: {e}")
        return twiml_say_hangup(
            "I'm having trouble at the moment. Please leave a message after the tone, "
            "or call back in a few minutes. Goodbye."
        )

    # Continue the conversation loop unless the response indicates a clear
    # "callback requested" or "goodbye" signal
    lc = response_text.lower()
    if any(x in lc for x in ["goodbye", "we'll call you back", "have a good day"]):
        return twiml_say_hangup(response_text)
    return twiml_say_gather(response_text, action_path="/twilio/respond")
